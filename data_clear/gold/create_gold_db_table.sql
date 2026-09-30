-- --------------------------------------------------
-- 1. 第一頁：技能選項與分類維度表 (dim_skill_option)
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS gold_db.dim_skill_option (
    skill_code VARCHAR(50) NOT NULL COMMENT '標準技能代碼 (PK)',
    std_skill_name VARCHAR(100) DEFAULT NULL COMMENT '畫面上的 Checkbox 文字，AI 處理:同義詞/異體字歸一化',
    raw_skill_name VARCHAR(100) NOT NULL COMMENT '原始名稱備註/代表名稱 (如: MySQL)',
    skill_category VARCHAR(50) DEFAULT NULL COMMENT 'AI 處理:畫面卡片的大標題 (例: 程式語言與開發工具)',
    source_type VARCHAR(20) NOT NULL COMMENT '來源類型 (tool / specialty)',
    PRIMARY KEY (skill_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第一頁專用：渲染 Checkbox 技能選單，已將同義詞與異體字收攏統一呈現';

-- --------------------------------------------------
-- 2. 第一頁：AI 中間對照維度表 (ref_skill_synonym_map)
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS gold_db.ref_skill_synonym_map (
    raw_skill_name VARCHAR(100) NOT NULL COMMENT '原始技能名稱 (PK, 例: MySQL, My SQL, DB2)',
    std_skill_name VARCHAR(100) DEFAULT NULL COMMENT '標準技能名稱 (畫面上的 Checkbox 文字，不包含大分類)',
    skill_category VARCHAR(50) DEFAULT NULL COMMENT 'UI 卡片大標題 (純文字，不含 Emoji/圖釘符號)',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最後更新時間',
    PRIMARY KEY (raw_skill_name),
    INDEX idx_std_skill_name (std_skill_name),
    INDEX idx_skill_category (skill_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同義詞/異體字歸一化對照表：記錄原始技能名稱對應至 UI Checkbox 標準選項與大分類的關係';

-- --------------------------------------------------
-- 3. 第二頁之一：職業類別與技能匹配加權事實表 (fact_category_skill_weight)
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS gold_db.fact_category_skill_weight (
    category_code VARCHAR(50) NOT NULL COMMENT '職業類別代碼',
    category_name VARCHAR(100) NOT NULL COMMENT '職業類別名稱',
    std_skill_name VARCHAR(100) NOT NULL COMMENT '畫面上的 Checkbox 文字',
    weight DECIMAL(7,4) NOT NULL COMMENT '出現頻率/權重 (0.00 ~ 1.00)',
    is_core_skill TINYINT(1) NOT NULL DEFAULT 0 COMMENT '核心技能標籤 (出現率 >= 50%)',
    PRIMARY KEY (category_code, skill_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第二頁專用：帶入第一頁勾選的 skill_code，計算各職業類別匹配分數 (Match %)';

-- --------------------------------------------------
-- 4. 第二頁之二：職業類別職缺占比事實表 (fact_job_ratio)
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS gold_db.fact_job_ratio (
    category_code VARCHAR(50) NOT NULL COMMENT '職業類別代碼',
    category_name VARCHAR(100) NOT NULL COMMENT '職業類別名稱',
    job_count INT NOT NULL DEFAULT 0 COMMENT '依職業類別統計職缺數量',
    category_job_ratio DECIMAL(7,4) NOT NULL DEFAULT 0.0000 COMMENT '職缺市占比 (0.0000 ~ 1.00)',
    category_desc VARCHAR(255) DEFAULT NULL COMMENT '職業類別簡短描述',
    PRIMARY KEY (category_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第二頁專用：計算整體職缺占比與市占比';
-- --------------------------------------------------
-- 3. 第三頁：fact_category_salary_stat
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS gold_db.fact_category_salary_stat (
    -- 1. 複合業務主鍵
    stat_id VARCHAR(150) NOT NULL COMMENT '複合業務主鍵 (category_code_salary_type_code_region_group_exp_level)',
    
    -- 2. 維度欄位 (與 GROUP BY 欄位完全對應)
    category_code VARCHAR(50) NOT NULL COMMENT '職業類別代碼',
    salary_type_code VARCHAR(20) NOT NULL COMMENT '薪資類型代碼 (10:面議, 20:論件, 30:時薪, 60:年薪, 70:部份時薪等)',
    region_group VARCHAR(20) NOT NULL COMMENT '五大區域 (N:北部, E:中部, S:南部, W:東部, OI:離島, OS:其他)',
    exp_level VARCHAR(50) NOT NULL COMMENT '年資區間標籤 (not_requir, 1to3, 4to6, 7to9, over10, not_apply)',
    salary_raw_text VARCHAR(100) NOT NULL COMMENT '薪資顯示文字/標籤 (如: 待遇面議, 時薪, 月薪...)',
    
    -- 3. 統計指標欄位 (對應最終 SELECT 聚合計算結果)
    job_count INT NOT NULL DEFAULT 0 COMMENT '統計職缺數量',
    salary_min DECIMAL(10, 2) DEFAULT NULL COMMENT '全群組最低薪資最小值 (MIN)',
    salary_max DECIMAL(10, 2) DEFAULT NULL COMMENT '全群組最高薪資最大值 (MAX，若為 NULL 則抓 salary_min 最大值)',
    avg_salary_mid DECIMAL(10, 2) DEFAULT NULL COMMENT '平均中位薪資 (若無 max 則自動撈取 salary_min 之真實中位數)',
    
    -- 4. 系統寫入時間
    create_time DATETIME NOT NULL COMMENT '資料產出與寫入時間',
    
    -- 主鍵與索引設定
    PRIMARY KEY (stat_id),
    UNIQUE KEY uk_salary_stats (category_code, salary_type_code, region_group, exp_level, salary_raw_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='職業類別薪資區域綜合統計金表';