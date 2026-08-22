-- 在 MySQL Workbench 以 Local instance MySQL80 / root 手動執行。
-- 本檔只在不存在時建立 database/table，不會 DROP 或清除既有資料。

SELECT
    USER() AS connection_identity,
    CURRENT_USER() AS authenticated_account,
    VERSION() AS server_version,
    @@port AS server_port;

CREATE DATABASE IF NOT EXISTS `job_crawler_104`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE `job_crawler_104`;

CREATE TABLE IF NOT EXISTS `jobs` (
    `job_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `schema_version` VARCHAR(16) NOT NULL,
    `latest_run_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `source_name` VARCHAR(64) NOT NULL,
    `query_jobcat_code` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `query_jobcat_name` VARCHAR(255) NOT NULL,
    `query_employment_type` VARCHAR(64) NOT NULL,
    `query_area` VARCHAR(64) NOT NULL,
    `search_page_number` INT UNSIGNED NOT NULL,
    `job_url` VARCHAR(1024) NOT NULL,
    `display_date_raw` VARCHAR(64) NULL,
    `job_title` VARCHAR(512) NOT NULL,
    `company_id` VARCHAR(64) NULL,
    `company_name` VARCHAR(512) NOT NULL,
    `employment_type_raw` VARCHAR(64) NULL,
    `job_categories` JSON NOT NULL,
    `location_raw` VARCHAR(1024) NULL,
    `address_raw` VARCHAR(1024) NULL,
    `salary_raw` VARCHAR(512) NULL,
    `job_description` LONGTEXT NOT NULL,
    `requirements_text` LONGTEXT NULL,
    `experience_raw` VARCHAR(255) NULL,
    `education_raw` VARCHAR(255) NULL,
    `majors` JSON NOT NULL,
    `languages` JSON NOT NULL,
    `tools` JSON NOT NULL,
    `skills` JSON NOT NULL,
    `other_requirements` LONGTEXT NULL,
    `quality_status` VARCHAR(32) NOT NULL,
    `quality_warnings` JSON NOT NULL,
    `raw_payload_path` VARCHAR(1024) NULL,
    `raw_sha256` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    `content_sha256` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `canonical_json` JSON NOT NULL,
    `first_seen_at` DATETIME(6) NOT NULL COMMENT '首次成功擷取時間，UTC',
    `last_seen_at` DATETIME(6) NOT NULL COMMENT '最近成功擷取時間，UTC',
    `db_created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `db_updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (`job_id`),
    KEY `idx_jobs_company_id` (`company_id`),
    KEY `idx_jobs_last_seen_at` (`last_seen_at`),
    KEY `idx_jobs_quality_status` (`quality_status`),
    CONSTRAINT `chk_jobs_seen_order`
        CHECK (`first_seen_at` <= `last_seen_at`)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  COMMENT='104 職缺目前最新版本；Raw 歷史快照另存檔案系統';

SHOW CREATE TABLE `jobs`;
