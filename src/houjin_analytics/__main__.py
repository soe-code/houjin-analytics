"""`uv run python -m houjin_analytics` で分析用テーブルを作り直す。"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from houjin_analytics.pipeline import DEFAULT_CONFIG, build, export_parquet, load_sources, summarize


def main() -> None:
    parser = argparse.ArgumentParser(description="法人番号データに財務値を付けた分析用データを作る")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    sources = load_sources(args.config)
    sources.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(sources.duckdb_path)) as con:
        build(con, sources)
        parts = export_parquet(con, sources.parquet_path)
        stats = summarize(con)

    print(f"DuckDB : {sources.duckdb_path}")
    for part in parts:
        print(f"Parquet: {part}")
    for key, value in stats.items():
        print(f"  {key:>24}: {value:,}")
    # 法人番号データ側に存在しない（他県所在など）財務値は付かない
    unmatched = stats["financials_corps_total"] - stats["has_financials"]
    print(f"  {'financials_unmatched':>24}: {unmatched:,}")


if __name__ == "__main__":
    main()
