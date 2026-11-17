# houjin-analytics

法人番号公表サイトの全件データ（1法人1行）に、売上などの財務値を列として付け、分析用データを作る。

## 同梱サンプル

`data/processed/` に分析用Parquetを同梱する。クローン後、入力の再取得なしで利用できる。

| データ | ファイル | 合計行数 | ダミー列（円） |
|---|---|---:|---|
| 東京都の法人番号 | `houjin_enriched_part01.parquet` 〜 `part05.parquet` | 1,362,626 | `revenue_dummy_jpy` |
| 東京都のインボイス法人 | `invoice_enriched_part01.parquet` 〜 `part05.parquet` | 565,153 | `cost_jpy` |

ダミー値は全件に付与され、実際の売上・費用を表さない。法人版の `revenue_jpy` は別の実売上列。
インボイス版は失効・取消・将来登録も含む最新履歴であり、有効な登録だけを集めたものではない。
各ファイルの行数・サイズ・SHA-256は `data/processed/manifest.json` に記録する。
生CSV・入力データ・作業用DuckDB・仮想環境は同梱しない。

DuckDBでの読み取り例：

```sql
SELECT corporate_number, name, revenue_dummy_jpy
FROM read_parquet('data/processed/houjin_enriched_part*.parquet') LIMIT 5;

SELECT invoice_registration_number, name, cost_jpy
FROM read_parquet('data/processed/invoice_enriched_part*.parquet') LIMIT 5;
```

## 使い方

```bash
make setup   # uv sync
make build   # DuckDB と5分割したParquetを作り直す
make check   # ruff + mypy + pytest
```

## 入力（`config/sources.toml`）

他プロジェクトの取得済みデータを読み取り専用で参照する。コピー・再配布はしない。

| 入力 | 提供元 | 用途 |
|---|---|---|
| 法人番号 全件CSV | jp-invoice-entity-resolution の `data/raw/houjin_bangou/` | ベースの1法人1行 |
| EDINET 書類一覧 JSON | edinet-accruals の `data/raw/edinet/lists/` | `docID` → `JCN`（法人番号）の対応 |
| `concept_values_v1/values_wide.csv` | edinet-accruals | 書類ごとの財務値（統一マッピング適用済み） |

## 処理（`sql/` をファイル名順に実行）

1. `01_stg_houjin.sql`: 法人番号CSVに列名を付けてロード（原文のまま）
2. `02_stg_edinet_filings.sql`: 書類一覧から docID・法人番号・対象期間を取り出す
3. `03_stg_edinet_financials.sql`: 売上・営業利益・経常利益・純利益・総資産・純資産を取り出す
4. `04_financials_by_corp.sql`: 法人番号ごとに、対象期間末が最新の書類を1件選ぶ
5. `05_houjin_enriched.sql`: 法人番号データに LEFT JOIN し、法人種別のラベルなどを付ける

## 出力 `houjin_enriched`

- 法人の属性: `corporate_number`, `name`, `kind_label`, `prefecture_name`, `city_name`, `is_active` など
- 財務値（円）: `revenue_jpy`, `operating_income_jpy`, `ordinary_income_jpy`, `net_income_owners_jpy`, `total_assets_jpy`, `net_assets_jpy`
- ダミー売上（円）: `revenue_dummy_jpy`。全法人に100万円〜100億円（100万円刻み）を付与。
  法人番号のMD5に基づく再現可能な値で、実売上・法人規模とは関係しない。実売上 `revenue_jpy` は保持する。
- 出どころ: `fin_period_end`, `fin_accounting_standard`, `fin_scope`（連結/単体）, `fin_doc_id`, `fin_candidate_docs`

出力は `data/processed/houjin_enriched_part01.parquet` 〜 `houjin_enriched_part05.parquet`。
法人番号順で5分割し、ファイル間の行数差は最大1行。生成完了後に旧 `houjin_enriched.parquet` を削除する。
`config/sources.toml` の `output.parquet` は分割ファイル名の基準として使用する。

## インボイス版（ダミー費用）

```bash
make build-invoice  # 取得済みの法人CSVから再生成
```

入力は `config/invoice_sources.toml` で指定する国税庁の法人用全件CSV（`h_all_*`、
ヘッダなし24列）と、上記の法人Parquet。元CSVは `data/raw/invoice_registry/` に保管する。
取得元は [国税庁の全件ダウンロード](https://www.invoice-kohyo.nta.go.jp/download/zenken)。

- 最新履歴を1登録番号1行で保持し、法人情報をLEFT JOINする。未結合・失効・取消・将来登録も保持する。
- **`cost_jpy`（費用）**：BIGINT型、円単位。全件に100万円〜100億円（100万円刻み）のダミー値を付与する。
  登録番号と用途文字列 `expense:` のMD5に基づく再現可能な値。実際の費用とは関係しない。
  `is_dummy_cost = true` を付け、インボイス版には売上列を追加しない。
- 登録日・更新日・取消日・失効日はDATE型、地域コードは先頭の0を維持する文字列。
- `is_latest` は最新履歴であり、登録が現在有効であることを意味しない。
  登録状態を分析する場合は基準日と履歴を別途考慮する。
- 出所は `source_file`・`source_file_created_date`、法人情報との結合有無は `has_houjin_match`。

出力は `data/work/invoice.duckdb` と、登録番号順で均等に5分割した
`data/processed/invoice_enriched_part01.parquet` 〜 `invoice_enriched_part05.parquet`。

## 注意

- 財務値が付くのは EDINET で有報を出している会社だけで、法人全体のごく一部。
  財務値が空欄なのは「データがない」という意味で、0 ではない。
- `fin_scope` が `consolidated` の場合、売上はグループ全体の値。単体の値と混ぜて比べない。
- 法人番号データは現在、東京都分だけ。他の道府県の会社の財務値は付かない（実行ログの `financials_unmatched`）。
