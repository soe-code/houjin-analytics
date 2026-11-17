-- edinet-accruals の concept_values（1書類1行・円単位）から、分析で使う主要科目を取り出す。
-- 空欄は「統一マッピングで検証済みの値がない」ことを意味するので 0 で埋めない。
CREATE OR REPLACE TABLE stg_edinet_financials AS
SELECT
    doc_id,
    edinet_code,
    name AS edinet_name,
    industry,
    accounting_standard,
    scope,
    TRY_CAST("income.revenue" AS BIGINT) AS revenue_jpy,
    TRY_CAST("income.operating" AS BIGINT) AS operating_income_jpy,
    TRY_CAST("income.ordinary" AS BIGINT) AS ordinary_income_jpy,
    TRY_CAST("income.net_owners" AS BIGINT) AS net_income_owners_jpy,
    TRY_CAST("assets.total" AS BIGINT) AS total_assets_jpy,
    TRY_CAST("equity.net_assets" AS BIGINT) AS net_assets_jpy
FROM read_csv(getvariable('edinet_financials_csv'), header = true, all_varchar = true);
