from __future__ import annotations

import json
from pathlib import Path

import duckdb

from houjin_analytics.pipeline import Sources, build, export_parquet


def _houjin_row(corp: str, name: str, kind: str, close_date: str = "") -> str:
    cols = [""] * 30
    cols[0], cols[1], cols[6], cols[8] = "1", corp, name, kind
    cols[9], cols[13], cols[18], cols[23] = "東京都", "13", close_date, "1"
    return ",".join(cols)


def _make_sources(tmp_path: Path) -> Sources:
    (tmp_path / "houjin.csv").write_text(
        "\n".join(
            [
                _houjin_row("1111111111111", "甲株式会社", "301"),
                _houjin_row("2222222222222", "乙合同会社", "305", close_date="2024-01-01"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    lists = tmp_path / "lists"
    lists.mkdir()
    results = [
        # 甲: 2期分の書類。新しい期 (2025-03-31) が採られるべき
        {"docID": "D_OLD", "JCN": "1111111111111", "periodEnd": "2024-03-31",
         "submitDateTime": "2024-06-20 09:00"},
        {"docID": "D_NEW", "JCN": "1111111111111", "periodEnd": "2025-03-31",
         "submitDateTime": "2025-06-20 09:00"},
        # 法人番号データに存在しない法人
        {"docID": "D_OTHER", "JCN": "9999999999999", "periodEnd": "2025-03-31",
         "submitDateTime": "2025-06-20 09:00"},
    ]
    (lists / "a.json").write_text(json.dumps({"results": results}), encoding="utf-8")
    (tmp_path / "fin.csv").write_text(
        "doc_id,edinet_code,name,industry,accounting_standard,scope,income.revenue,"
        "income.operating,income.ordinary,income.net_owners,assets.total,equity.net_assets\n"
        "D_OLD,E1,甲,機械,JGAAP,consolidated,100,,,,,\n"
        "D_NEW,E1,甲,機械,JGAAP,consolidated,200,20,,,,\n"
        "D_OTHER,E9,丙,機械,JGAAP,consolidated,300,,,,,\n",
        encoding="utf-8",
    )
    return Sources(
        houjin_csv_glob=str(tmp_path / "houjin.csv"),
        edinet_lists_glob=str(lists / "*.json"),
        edinet_financials_csv=str(tmp_path / "fin.csv"),
        duckdb_path=tmp_path / "x.duckdb",
        parquet_path=tmp_path / "x.parquet",
    )


def test_enriched_attaches_latest_period_financials(tmp_path: Path) -> None:
    con = duckdb.connect()
    build(con, _make_sources(tmp_path))
    rows = con.execute(
        """
        SELECT corporate_number, kind_label, is_active, has_financials,
               revenue_jpy, operating_income_jpy, fin_doc_id, fin_candidate_docs
        FROM houjin_enriched ORDER BY corporate_number
        """
    ).fetchall()
    assert rows == [
        ("1111111111111", "株式会社", True, True, 200, 20, "D_NEW", 2),
        ("2222222222222", "合同会社", False, False, None, None, None, None),
    ]


def test_enriched_keeps_one_row_per_corporate_number(tmp_path: Path) -> None:
    con = duckdb.connect()
    build(con, _make_sources(tmp_path))
    total, distinct = con.execute(
        "SELECT count(*), count(DISTINCT corporate_number) FROM houjin_enriched"
    ).fetchone() or (0, 0)
    assert total == distinct == 2


def test_dummy_revenue_covers_all_corps_and_is_reproducible(tmp_path: Path) -> None:
    with duckdb.connect() as con:
        sources = _make_sources(tmp_path)
        build(con, sources)
        query = """
            SELECT corporate_number, revenue_dummy_jpy
            FROM houjin_enriched ORDER BY corporate_number
        """
        first = con.execute(query).fetchall()
        assert len(first) == 2
        assert all(1_000_000 <= value <= 10_000_000_000 for _, value in first)
        assert all(value % 1_000_000 == 0 for _, value in first)
        build(con, sources)
        assert con.execute(query).fetchall() == first


def test_export_splits_without_losing_or_duplicating_rows(tmp_path: Path) -> None:
    # 引用符を含むパスでも正しく出力し、再実行時に既存出力を更新する。
    path = tmp_path / "sample's.parquet"
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE houjin_enriched AS SELECT range AS corporate_number FROM range(7)"
        )
        con.execute("COPY houjin_enriched TO ? (FORMAT parquet)", [str(path)])
        for _ in range(2):
            parts = export_parquet(con, path)
            assert len(parts) == 5
            assert not path.exists()
            counts = []
            for part in parts:
                count = con.read_parquet(str(part)).count("*").fetchone()
                assert count is not None
                counts.append(count[0])
            assert counts == [2, 2, 1, 1, 1]
            rows = con.read_parquet([str(part) for part in parts])
            assert rows.columns == ["corporate_number"]
            assert rows.order("corporate_number").fetchall() == [(i,) for i in range(7)]


def test_export_writes_five_files_for_empty_input(tmp_path: Path) -> None:
    with duckdb.connect() as con:
        con.execute("CREATE TABLE houjin_enriched (corporate_number VARCHAR)")
        parts = export_parquet(con, tmp_path / "empty.parquet")
        assert len(parts) == 5
        assert all(part.exists() for part in parts)
        assert con.read_parquet([str(part) for part in parts]).fetchall() == []
