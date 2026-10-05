from __future__ import annotations

import os
from dotenv import load_dotenv
from utils.conn_to_mysql import conn_to_mysql


def create_gold_tables():
    """具體執行 SQL CREATE TABLE 建表的實體邏輯，與 silver_all.py 使用同一套 MySQL 連線方式。"""
    ddl = [
        # 1. 第一頁：技能選項與分類維度表 (dim_skill_option)
        """
        CREATE TABLE IF NOT EXISTS gold_db.dim_skill_option (
            skill_code VARCHAR(50) NOT NULL COMMENT '標準技能代碼 (PK)',
            std_skill_name VARCHAR(100) DEFAULT NULL COMMENT '畫面上的 Checkbox 文字，AI 處理:同義詞/異體字歸一化',
            raw_skill_name VARCHAR(100) NOT NULL COMMENT '原始名稱備註/代表名稱 (如: MySQL)',
            skill_category VARCHAR(50) DEFAULT NULL COMMENT 'AI 處理:畫面卡片的大標題 (例: 程式語言與開發工具)',
            source_type VARCHAR(20) NOT NULL COMMENT '來源類型 (tool / specialty)',
            PRIMARY KEY (skill_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第一頁專用：渲染 Checkbox 技能選單，已將同義詞與異體字收攏統一呈現';

        """,

        # 2. 第一頁：AI 中間對照維度表 (ref_skill_synonym_map)
        """
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

        """,

        # 3. 第二頁之一：職業類別與技能匹配加權事實表 (fact_category_skill_weight)
        """
        CREATE TABLE IF NOT EXISTS gold_db.fact_category_skill_weight (
            category_code VARCHAR(50) NOT NULL COMMENT '職業類別代碼',
            category_name VARCHAR(100) NOT NULL COMMENT '職業類別名稱',
            std_skill_name VARCHAR(100) NOT NULL COMMENT '畫面上的 Checkbox 文字',
            weight DECIMAL(7,4) NOT NULL COMMENT '出現頻率/權重 (0.00 ~ 1.00)',
            is_core_skill TINYINT(1) NOT NULL DEFAULT 0 COMMENT '核心技能標籤 (出現率 >= 50%)',
            PRIMARY KEY (category_code, std_skill_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第二頁專用：帶入第一頁勾選的 skill_code，計算各職業類別匹配分數 (Match %)';
        """,

        # 4. 第二頁之二：職業類別職缺占比事實表 (fact_job_ratio)
        """
        CREATE TABLE IF NOT EXISTS gold_db.fact_job_ratio (
            category_code VARCHAR(50) NOT NULL COMMENT '職業類別代碼',
            category_name VARCHAR(100) NOT NULL COMMENT '職業類別名稱',
            job_count INT NOT NULL DEFAULT 0 COMMENT '依職業類別統計職缺數量',
            category_job_ratio DECIMAL(7,4) NOT NULL DEFAULT 0.0000 COMMENT '職缺市占比 (0.0000 ~ 1.00)',
            category_desc VARCHAR(255) DEFAULT NULL COMMENT '職業類別簡短描述',
            PRIMARY KEY (category_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第二頁專用：計算整體職缺占比與市占比';
        """,

        # 5. 第三頁：薪資統計事實表 (fact_category_salary_stat)
        """
        CREATE TABLE IF NOT EXISTS gold_db.fact_category_salary_stat (
            stat_id INT AUTO_INCREMENT PRIMARY KEY,
            category_code VARCHAR(50) NOT NULL,
            category_name VARCHAR(100) NULL,
            salary_type_code VARCHAR(20) NOT NULL,
            region_group VARCHAR(20) NOT NULL,
            exp_level VARCHAR(50) NOT NULL DEFAULT '不限',
            job_count INT NOT NULL,
            avg_salary_min DECIMAL(10,2) NULL,
            avg_salary_max DECIMAL(10,2) NULL,
            avg_salary_mid DECIMAL(10,2) NULL,
            median_salary DECIMAL(10,2) NULL,
            UNIQUE KEY uk_stat_dim (category_code, salary_type_code, region_group, exp_level)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"""

        # 6. 第四頁之一：職缺搜尋卡片事實表 (單表反正規化，提供零 JOIN 極速查詢)
        """
        CREATE TABLE IF NOT EXISTS gold_db.fact_job_search_card (
            job_id VARCHAR(50) NOT NULL COMMENT '104 職缺原始 ID (PK)',
            region_group VARCHAR(20) NOT NULL COMMENT '五大區域代碼 (N/E/S/W/OI/OS)',
            salary_type_code VARCHAR(20) NOT NULL COMMENT '薪資類型代碼 (供多重篩選使用)',
            
            -- 反正規化預先拼接之顯示欄位
            job_title VARCHAR(150) NOT NULL COMMENT '職缺名稱',
            company_name VARCHAR(150) NOT NULL COMMENT '公司名稱',
            industry_name VARCHAR(100) DEFAULT NULL COMMENT '產業別',
            location_text VARCHAR(100) DEFAULT NULL COMMENT '工作地點 (例: 台北市 信義區)',
            salary_text VARCHAR(100) DEFAULT NULL COMMENT '格式化薪資文字 (例: 月薪 50,000 ~ 70,000 元)',
            exp_edu_text VARCHAR(100) DEFAULT NULL COMMENT '門檻標籤 (例: 經歷 1-3年 ｜ 大學以上)',
            work_mode VARCHAR(255) DEFAULT NULL COMMENT '工作模式 (例: 可部分遠距)',
            
            -- 陣列與摘要欄位
            skills_json TEXT DEFAULT NULL COMMENT "技能標籤陣列 (JSON: ['Python', 'SQL'])",
            job_desc_short VARCHAR(255) DEFAULT NULL COMMENT '工作簡述 (ETL 已完成 80 字截斷)',
            job_url VARCHAR(500) NOT NULL COMMENT '104 直達 URL',
            
            PRIMARY KEY (job_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第四頁職缺卡片搜尋金表';
        """,

        # 7. 第四頁之二：職缺與職業類別多對多關聯表 (Bridge Table)
        """
        CREATE TABLE IF NOT EXISTS gold_db.bridge_job_category (
        job_id varchar(50) NOT NULL COMMENT "104 職缺原始 ID",
        category_code varchar(50) NOT NULL COMMENT "職業類別代碼",
        category_name varchar(50) NOT NULL COMMENT "職業類別名稱",
        PRIMARY KEY (job_id,category_code),
        INDEX idx_page4_category_code (category_code)
        )
        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第四頁專用：解決一職缺屬於多職業類別 (一職多類) 的篩選關聯';
        """,
    ]
    
    #載入.env 到環境變數
    load_dotenv()
    db_name = os.getenv("MYSQL_GOLD_DATABASE")
    
    mysql_conn = conn_to_mysql(db_name=db_name)
    if mysql_conn is None:
        raise RuntimeError("無法連線到 MySQL，請檢查伺服器狀態。")

    try:
        with mysql_conn.cursor() as cursor:
            for sql in ddl:
                cursor.execute(sql)
        mysql_conn.commit()
        return True
    finally:
        mysql_conn.close()
        print("gold table已順利建立")


if __name__ == "__main__":
    create_gold_tables()
    print("gold tables initialized")
