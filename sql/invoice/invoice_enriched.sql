-- インボイス法人データの最新情報を1登録番号1行にする。失効・取消・将来登録も保持する。
-- cost_jpy は表示・集計の動作確認用で、実際の費用や売上とは関係しない。
CREATE OR REPLACE TABLE invoice_enriched AS
SELECT
    i.registrated_number AS invoice_registration_number,
    substring(i.registrated_number, 2) AS corporate_number,
    CAST(i.sequence_number AS BIGINT) AS sequence_number,
    i.process,
    i.correct,
    i.kind,
    i.country,
    i.latest = '1' AS is_latest,
    CAST(i.registration_date AS DATE) AS registration_date,
    CAST(i.update_date AS DATE) AS update_date,
    CAST(i.disposal_date AS DATE) AS disposal_date,
    CAST(i.expire_date AS DATE) AS expire_date,
    i.address,
    i.address_prefecture_code,
    i.address_city_code,
    i.address_request,
    i.address_request_prefecture_code,
    i.address_request_city_code,
    i.kana,
    i.name,
    i.address_inside,
    i.address_inside_prefecture_code,
    i.address_inside_city_code,
    i.trade_name,
    i.popular_name_previous_name,
    CAST(
        (md5_number_lower('expense:' || i.registrated_number) % 10000 + 1) * 1000000
        AS BIGINT
    ) AS cost_jpy,
    true AS is_dummy_cost,
    h.corporate_number IS NOT NULL AS has_houjin_match,
    h.kind_label AS houjin_kind_label,
    h.prefecture_name AS houjin_prefecture_name,
    h.city_name AS houjin_city_name,
    parse_filename(i.filename) AS source_file,
    CAST(getvariable('invoice_source_file_created_date') AS DATE) AS source_file_created_date
FROM stg_invoice_registry AS i
LEFT JOIN _invoice_houjin AS h ON i.registrated_number = 'T' || h.corporate_number
WHERE i.latest = '1';
