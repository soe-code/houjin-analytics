-- 法人番号ごとに 1 行の財務値へ集約する。
-- 複数の書類がある場合は対象期間末が最新のもの、同じなら提出が新しいもの（訂正後）を採る。
CREATE OR REPLACE TABLE financials_by_corp AS
SELECT
    f.corporate_number,
    f.doc_id AS fin_doc_id,
    f.edinet_code AS fin_edinet_code,
    f.period_start AS fin_period_start,
    f.period_end AS fin_period_end,
    v.industry AS fin_industry,
    v.accounting_standard AS fin_accounting_standard,
    v.scope AS fin_scope,
    v.revenue_jpy,
    v.operating_income_jpy,
    v.ordinary_income_jpy,
    v.net_income_owners_jpy,
    v.total_assets_jpy,
    v.net_assets_jpy,
    count(*) OVER (PARTITION BY f.corporate_number) AS fin_candidate_docs
FROM stg_edinet_financials AS v
JOIN stg_edinet_filings AS f USING (doc_id)
WHERE f.corporate_number IS NOT NULL
QUALIFY row_number() OVER (
    PARTITION BY f.corporate_number
    ORDER BY f.period_end DESC NULLS LAST, f.submitted_at DESC NULLS LAST, f.doc_id DESC
) = 1;
