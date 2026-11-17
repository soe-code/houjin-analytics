from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import duckdb
import pytest

from houjin_analytics.invoice import INVOICE_COLUMNS, InvoiceSources, build_invoice
from houjin_analytics.pipeline import export_parquet


def _sources(tmp_path: Path) -> InvoiceSources:
    rows = [
        # 同じ登録番号の過去行には名称・人格区分などが入っていない。
        {"registrated_number": "T1111111111111", "latest": "0"},
        {"registrated_number": "T1111111111111", "latest": "1", "name": "甲株式会社"},
        # 法人データと未結合で、失効済みの行も残す。
        {"registrated_number": "T2222222222222", "latest": "1", "name": "乙株式会社",
         "process": "03", "expire_date": "2025-01-01"},
        # 将来の登録も除外しない。
        {"registrated_number": "T3333333333333", "latest": "1", "name": "丙株式会社",
         "registration_date": "2027-01-01"},
    ]
    path = tmp_path / "h_all_test.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=INVOICE_COLUMNS)
        for number, row in enumerate(rows, start=1):
            writer.writerow({
                "sequence_number": str(number), "kind": "2", "country": "1",
                "correct": "0", "process": "01", "registration_date": "2023-10-01",
                "update_date": "2026-10-30", "address_prefecture_code": "13",
                "address_city_code": "001", **row,
            })
    houjin = tmp_path / "houjin.parquet"
    with duckdb.connect() as con:
        con.execute(
            """
            COPY (SELECT '1111111111111' AS corporate_number, '株式会社' AS kind_label,
                         '東京都' AS prefecture_name, '千代田区' AS city_name)
            TO ? (FORMAT parquet)
            """,
            [str(houjin)],
        )
    return InvoiceSources(
        csv_glob=str(path), source_file_created_date=date(2026, 10, 30),
        houjin_parquet_glob=str(houjin), duckdb_path=tmp_path / "invoice.duckdb",
        parquet_path=tmp_path / "invoice.parquet",
    )


def test_invoice_cost_preserves_latest_unmatched_and_inactive_rows(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    with duckdb.connect() as con:
        build_invoice(con, sources)
        rows = con.execute(
            """
            SELECT corporate_number, name, address_city_code, has_houjin_match,
                   expire_date, registration_date FROM invoice_enriched
            ORDER BY corporate_number
            """
        ).fetchall()
        assert rows == [
            ("1111111111111", "甲株式会社", "001", True, None, date(2023, 10, 1)),
            ("2222222222222", "乙株式会社", "001", False, date(2025, 1, 1), date(2023, 10, 1)),
            ("3333333333333", "丙株式会社", "001", False, None, date(2027, 1, 1)),
        ]
        query = "SELECT invoice_registration_number, cost_jpy FROM invoice_enriched ORDER BY 1"
        first = con.execute(query).fetchall()
        assert all(1_000_000 <= cost <= 10_000_000_000 for _, cost in first)
        assert all(cost % 1_000_000 == 0 for _, cost in first)
        assert con.execute("SELECT bool_and(is_dummy_cost) FROM invoice_enriched").fetchone() == (
            True,
        )
        columns = con.execute("DESCRIBE invoice_enriched").fetchall()
        assert next(col[1] for col in columns if col[0] == "cost_jpy") == "BIGINT"
        assert not any("revenue" in col[0] for col in columns)
        build_invoice(con, sources)
        assert con.execute(query).fetchall() == first
        parts = export_parquet(
            con, sources.parquet_path,
            table_name="invoice_enriched", order_by="invoice_registration_number",
        )
        assert len(parts) == 5
        con.read_parquet([str(part) for part in parts]).create_view("exported")
        assert con.execute(query.replace("invoice_enriched", "exported")).fetchall() == first
        assert con.execute("SELECT count(*), count(cost_jpy) FROM exported").fetchone() == (3, 3)


def test_invoice_rejects_duplicate_latest_registrations(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    path = Path(sources.csv_glob)
    with path.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.reader(input_file))
    with path.open("a", encoding="utf-8", newline="") as output:
        csv.writer(output).writerow(rows[1])
    with duckdb.connect() as con, pytest.raises(ValueError, match="重複"):
        build_invoice(con, sources)


def test_invoice_rejects_invalid_date_instead_of_treating_as_unexpired(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    path = Path(sources.csv_glob)
    path.write_text(path.read_text().replace("2025-01-01", "invalid"), encoding="utf-8")
    with duckdb.connect() as con, pytest.raises(ValueError, match="不正"):
        build_invoice(con, sources)
