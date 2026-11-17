-- 分析用テーブル: 法人番号データ 1 法人 1 行に、型変換・コードのラベル・財務値を列として付ける。
CREATE OR REPLACE TABLE houjin_enriched AS
WITH kind_labels(kind, kind_label) AS (
    VALUES
        ('101', '国の機関'),
        ('201', '地方公共団体'),
        ('301', '株式会社'),
        ('302', '有限会社'),
        ('303', '合名会社'),
        ('304', '合資会社'),
        ('305', '合同会社'),
        ('399', 'その他の設立登記法人'),
        ('401', '外国会社等'),
        ('499', 'その他')
)
SELECT
    h.corporate_number,
    h.name,
    h.furigana,
    h.en_name,
    h.kind,
    k.kind_label,
    h.prefecture_code,
    h.prefecture_name,
    h.city_code,
    h.city_name,
    h.street_number,
    h.post_code,
    TRY_CAST(h.assignment_date AS DATE) AS assignment_date,
    TRY_CAST(h.change_date AS DATE) AS change_date,
    TRY_CAST(h.update_date AS DATE) AS update_date,
    TRY_CAST(h.close_date AS DATE) AS close_date,
    h.close_cause,
    h.successor_corporate_number,
    h.close_date IS NULL AS is_active,
    fc.fin_doc_id IS NOT NULL AS has_financials,
    fc.revenue_jpy,
    -- 分析・表示確認用のダミー売上（100万円〜100億円）。法人番号ごとに固定。
    CAST((md5_number_lower(h.corporate_number) % 10000 + 1) * 1000000 AS BIGINT)
        AS revenue_dummy_jpy,
    fc.operating_income_jpy,
    fc.ordinary_income_jpy,
    fc.net_income_owners_jpy,
    fc.total_assets_jpy,
    fc.net_assets_jpy,
    fc.fin_period_start,
    fc.fin_period_end,
    fc.fin_accounting_standard,
    fc.fin_scope,
    fc.fin_industry,
    fc.fin_edinet_code,
    fc.fin_doc_id,
    fc.fin_candidate_docs,
    h.source_file
FROM stg_houjin AS h
LEFT JOIN kind_labels AS k USING (kind)
LEFT JOIN financials_by_corp AS fc USING (corporate_number);
