"""法人番号データに財務値を付けた分析用テーブルを DuckDB 上で組み立てる。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SQL_DIR: Path = REPO_ROOT / "sql"
DEFAULT_CONFIG: Path = REPO_ROOT / "config" / "sources.toml"


@dataclass(frozen=True)
class Sources:
    houjin_csv_glob: str
    edinet_lists_glob: str
    edinet_financials_csv: str
    duckdb_path: Path
    parquet_path: Path


def load_sources(config_path: Path = DEFAULT_CONFIG, root: Path = REPO_ROOT) -> Sources:
    """設定ファイルを読み、相対パスを root 基準で解決する。"""
    cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))

    def resolve(p: str) -> Path:
        return (root / p).resolve() if not Path(p).is_absolute() else Path(p)

    return Sources(
        houjin_csv_glob=str(resolve(cfg["houjin_bangou"]["csv_glob"])),
        edinet_lists_glob=str(resolve(cfg["edinet"]["lists_glob"])),
        edinet_financials_csv=str(resolve(cfg["edinet"]["financials_csv"])),
        duckdb_path=resolve(cfg["output"]["duckdb"]),
        parquet_path=resolve(cfg["output"]["parquet"]),
    )


def build(con: duckdb.DuckDBPyConnection, sources: Sources) -> None:
    """sql/ 配下の SQL をファイル名順に実行する。"""
    con.execute("SET VARIABLE houjin_csv_glob = ?", [sources.houjin_csv_glob])
    con.execute("SET VARIABLE edinet_lists_glob = ?", [sources.edinet_lists_glob])
    con.execute("SET VARIABLE edinet_financials_csv = ?", [sources.edinet_financials_csv])
    for sql_path in sorted(SQL_DIR.glob("*.sql")):
        con.execute(sql_path.read_text(encoding="utf-8"))


def export_parquet(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    *,
    table_name: str = "houjin_enriched",
    order_by: str = "corporate_number",
) -> list[Path]:
    """指定キー順で行数を均等に5分割し、旧単一ファイルを置き換える。"""
    table_sql = '"' + table_name.replace('"', '""') + '"'
    order_sql = '"' + order_by.replace('"', '""') + '"'
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [path.with_name(f"{path.stem}_part{i:02d}{path.suffix}") for i in range(1, 6)]
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _houjin_export_ranked AS
        SELECT *, ntile(5) OVER (ORDER BY {order_sql}) AS _export_part
        FROM {table_sql}
        """
    )
    try:
        with TemporaryDirectory(prefix=".houjin-export-", dir=path.parent) as staging:
            for i, part in enumerate(parts, start=1):
                con.execute(
                    f"""
                    COPY (
                        SELECT * EXCLUDE (_export_part) FROM _houjin_export_ranked
                        WHERE _export_part = {i} ORDER BY {order_sql}
                    ) TO ? (FORMAT parquet, COMPRESSION zstd)
                    """,
                    [str(Path(staging) / part.name)],
                )
            for part in parts:
                (Path(staging) / part.name).replace(part)
        path.unlink(missing_ok=True)
    finally:
        con.execute("DROP TABLE _houjin_export_ranked")
    return parts


def summarize(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    row = con.execute(
        """
        SELECT
            count(*),
            count(*) FILTER (WHERE is_active),
            count(*) FILTER (WHERE has_financials),
            count(revenue_jpy),
            (SELECT count(*) FROM financials_by_corp)
        FROM houjin_enriched
        """
    ).fetchone()
    assert row is not None
    keys = ("rows", "active", "has_financials", "has_revenue", "financials_corps_total")
    return dict(zip(keys, (int(v) for v in row), strict=True))
