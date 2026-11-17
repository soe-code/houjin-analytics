-- 法人番号公表サイト 全件データ（CSV・Unicode形式、ヘッダなし30列）をそのまま列名付けしてロードする。
-- 原文は加工しない。型変換・ラベル付けは後段のビューで行う。
CREATE OR REPLACE TABLE stg_houjin AS
SELECT
    column00 AS sequence_number,
    column01 AS corporate_number,
    column02 AS process,
    column03 AS correct,
    column04 AS update_date,
    column05 AS change_date,
    column06 AS name,
    column07 AS name_image_id,
    column08 AS kind,
    column09 AS prefecture_name,
    column10 AS city_name,
    column11 AS street_number,
    column12 AS address_image_id,
    column13 AS prefecture_code,
    column14 AS city_code,
    column15 AS post_code,
    column16 AS address_outside,
    column17 AS address_outside_image_id,
    column18 AS close_date,
    column19 AS close_cause,
    column20 AS successor_corporate_number,
    column21 AS change_cause,
    column22 AS assignment_date,
    column23 AS latest,
    column24 AS en_name,
    column25 AS en_prefecture_name,
    column26 AS en_city_name,
    column27 AS en_address_outside,
    column28 AS furigana,
    column29 AS hihyoji,
    filename AS source_file
FROM read_csv(
    getvariable('houjin_csv_glob'),
    header = false,
    all_varchar = true,
    filename = true
);
