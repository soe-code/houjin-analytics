"""インボイスの法人公表データにダミー費用 cost_jpy を追加し、5分割して出力する。"""

from __future__ import annotations

import argparse
import glob
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from houjin_analytics.pipeline import REPO_ROOT, SQL_DIR, export_parquet

DEFAULT_INVOICE_CONFIG = REPO_ROOT / "config" / "invoice_sources.toml"
INVOICE_COLUMNS = (
    "sequence_number", "registrated_number", "process", "correct", "kind", "country",
    "latest", "registration_date", "update_date", "disposal_date", "expire_date", "address",
    "address_prefecture_code", "address_city_code", "address_request",
    "address_request_prefecture_code", "address_request_city_code", "kana", "name",
    "address_inside", "address_inside_prefecture_code", "address_inside_city_code",
    "trade_name", "popular_name_previous_name",
)


@dataclass(frozen=True)
class InvoiceSources:
    csv_glob: str
    source_file_created_date: date
    houjin_parquet_glob: str
    duckdb_path: Path
    parquet_path: Path


def load_invoice_sources(
    config_path: Path = DEFAULT_INVOICE_CONFIG, root: Path = REPO_ROOT
) -> InvoiceSources:
    cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))

    def resolve(value: str) -> Path:
        return (root / value).resolve() if not Path(value).is_absolute() else Path(value)

    return InvoiceSources(
        csv_glob=str(resolve(cfg["invoice"]["csv_glob"])),
        source_file_created_date=date.fromisoformat(cfg["invoice"]["source_file_created_date"]),
        houjin_parquet_glob=str(resolve(cfg["houjin"]["parquet_glob"])),
        duckdb_path=resolve(cfg["output"]["duckdb"]),
        parquet_path=resolve(cfg["output"]["parquet"]),
    )


def build_invoice(con: duckdb.DuckDBPyConnection, sources: InvoiceSources) -> None:
    """法人用ファイルを取り込み、最新行を基準に結合する。登録の有効性は判定しない。"""
    files = sorted(glob.glob(sources.csv_glob))
    if not files:
        raise FileNotFoundError(sources.csv_glob)
    if any(not Path(path).name.startswith("h_all_") for path in files):
        raise ValueError("法人用の h_all_* CSV のみ指定できます")
    columns_sql = ", ".join(f"'{column}': 'VARCHAR'" for column in INVOICE_COLUMNS)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE stg_invoice_registry AS
        SELECT * FROM read_csv(
            ?, header = false, delim = ',', columns = {{{columns_sql}}}, filename = true
        )
        """,
        [files],
    )
    invalid = con.execute(
        """
        SELECT count(*) FROM stg_invoice_registry
        WHERE latest = '1' AND (
            NOT coalesce(regexp_full_match(registrated_number, 'T[0-9]{13}'), false)
            OR kind IS DISTINCT FROM '2'
            OR try_cast(registration_date AS DATE) IS NULL
            OR try_cast(update_date AS DATE) IS NULL
            OR (disposal_date IS NOT NULL AND try_cast(disposal_date AS DATE) IS NULL)
            OR (expire_date IS NOT NULL AND try_cast(expire_date AS DATE) IS NULL)
        )
        """
    ).fetchone()
    if invalid != (0,):
        raise ValueError(f"インボイス最新行の番号・人格区分・日付が不正です: {invalid}")
    duplicates = con.execute(
        """
        SELECT count(*) FROM (
            SELECT registrated_number FROM stg_invoice_registry WHERE latest = '1'
            GROUP BY registrated_number HAVING count(*) > 1
        )
        """
    ).fetchone()
    if duplicates != (0,):
        raise ValueError(f"インボイス最新行の登録番号が重複しています: {duplicates}")
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _invoice_houjin AS
        SELECT corporate_number, kind_label, prefecture_name, city_name
        FROM read_parquet(?)
        """,
        [sources.houjin_parquet_glob],
    )
    houjin_count = con.execute(
        "SELECT count(*), count(DISTINCT corporate_number) FROM _invoice_houjin"
    ).fetchone()
    assert houjin_count is not None
    if houjin_count[0] != houjin_count[1]:
        raise ValueError("結合先の法人番号が欠損または重複しています")
    con.execute("SET VARIABLE invoice_source_file_created_date = ?", [
        sources.source_file_created_date,
    ])
    con.execute((SQL_DIR / "invoice" / "invoice_enriched.sql").read_text(encoding="utf-8"))
    con.execute("DROP TABLE _invoice_houjin")


def main() -> None:
    parser = argparse.ArgumentParser(description="インボイス法人データにダミー費用を付けて5分割")
    parser.add_argument("--config", type=Path, default=DEFAULT_INVOICE_CONFIG)
    args = parser.parse_args()
    sources = load_invoice_sources(args.config)
    sources.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(sources.duckdb_path)) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            build_invoice(con, sources)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        parts = export_parquet(
            con, sources.parquet_path,
            table_name="invoice_enriched", order_by="invoice_registration_number",
        )
        counts = con.execute(
            "SELECT count(*), count(cost_jpy), count(*) FILTER (WHERE has_houjin_match) "
            "FROM invoice_enriched"
        ).fetchone()
    print(f"DuckDB : {sources.duckdb_path}")
    for part in parts:
        print(f"Parquet: {part}")
    print(f"rows / cost_jpyあり / 法人結合あり: {counts}")


if __name__ == "__main__":
    main()
