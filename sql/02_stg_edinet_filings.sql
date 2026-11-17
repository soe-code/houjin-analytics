-- EDINET 書類一覧から docID と提出者法人番号（JCN）・対象期間を取り出す。
-- 同じ日付の一覧を複数回取得していることがあるため docID で重複除去する。
CREATE OR REPLACE TABLE stg_edinet_filings AS
WITH rows AS (
    SELECT unnest(results) AS r
    FROM read_json(
        getvariable('edinet_lists_glob'),
        columns = {
            'results': 'STRUCT(
                docID VARCHAR,
                edinetCode VARCHAR,
                JCN VARCHAR,
                filerName VARCHAR,
                docTypeCode VARCHAR,
                periodStart VARCHAR,
                periodEnd VARCHAR,
                submitDateTime VARCHAR,
                withdrawalStatus VARCHAR
            )[]'
        }
    )
)
SELECT
    r.docID AS doc_id,
    r.edinetCode AS edinet_code,
    r.JCN AS corporate_number,
    r.filerName AS filer_name,
    r.docTypeCode AS doc_type_code,
    TRY_CAST(r.periodStart AS DATE) AS period_start,
    TRY_CAST(r.periodEnd AS DATE) AS period_end,
    TRY_CAST(r.submitDateTime AS TIMESTAMP) AS submitted_at,
    r.withdrawalStatus AS withdrawal_status
FROM rows
QUALIFY row_number() OVER (PARTITION BY r.docID ORDER BY r.submitDateTime DESC NULLS LAST) = 1;
