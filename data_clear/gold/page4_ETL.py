from __future__ import annotations

import os

from dotenv import load_dotenv
from pymysql import connect

# 建立與 MySQL 的連線，並回傳連線物件
# 若有參數傳入，會覆蓋環境變數；否則會使用預設值
# 例如：MYSQL_DB、MYSQL_USER、MYSQL_PASSWORD、MYSQL_HOST、MYSQL_PORT

def conn_to_mysql(
    db_name: str | None = None):
  
    #載入.env 到環境變數
    load_dotenv()
    # 若參數未傳入，則從環境變數取得；若環境變數未設定，再使用預設值
    db_name = db_name or os.getenv("MYSQL_DATABASE")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_ROOT_PASSWORD")
    conn_ip = os.getenv("MYSQL_HOST")
    # port 轉整數防呆
    raw_port = os.getenv("MYSQL_PORT")
    port = int(raw_port) if raw_port else 3307

    print(f"Connecting to: host={conn_ip}, port={port}, user={user}, db={db_name}")
    try:
        # 建立 MySQL 連線
        return connect(
            host=conn_ip,
            port=port,
            user=user,
            password=password,
            database=db_name,
            connect_timeout=10,  # 10秒連不上自動拋出例外
            read_timeout=30,     # 讀寫超過30秒自動中斷，避免無效卡死
            write_timeout=30,    # 寫入超過30秒自動中斷，避免無效卡死
            autocommit=False
        )
    except Exception as exc:
        print(f"連線失敗，請確認 MySQL 伺服器是否有啟動。錯誤訊息: {exc}")
        return None

def insert_into_page4(conn):
    """第四頁金表寫入"""
    try:
        with conn.cursor() as cursor:
            sql_truncate = [
                "TRUNCATE TABLE gold_db.fact_job_cards;",
                "TRUNCATE TABLE gold_db.bridge_job_category;"
            ]

            sql_insert_card = """
            INSERT INTO gold_db.fact_job_cards (
                job_id,
                region_group,
                salary_type_code,
                job_title,
                company_name,
                industry_name,
                location_text,
                salary_text,
                exp_edu_text,
                work_mode,
                skills_json,
                job_desc_short,
                job_url
            )
                WITH job_skills_aggregated AS (
                    -- 1. 先把技能與專長依照 job_id 進行合併，並打包成 JSON 陣列
                    SELECT 
                        combined.job_id,
                        JSON_ARRAYAGG(combined.skill_name) AS skills_json
                    FROM (
                        SELECT job_id, skill_description AS skill_name 
                        FROM silver_db.job_skill
                        
                        UNION ALL
                        
                        SELECT job_id, specialty_name AS skill_name 
                        FROM silver_db.job_specialty
                    ) combined
                    GROUP BY combined.job_id
                )
                SELECT 
                    j.job_id,
                    
                    -- region_group
                    CASE 
                        WHEN j.address_region REGEXP '台北|新北|桃園|基隆|新竹|宜蘭' THEN 'N'
                        WHEN j.address_region REGEXP '台中|彰化|苗栗|南投|雲林' THEN 'E'
                        WHEN j.address_region REGEXP '台南|高雄|屏東|嘉義' THEN 'S'
                        WHEN j.address_region REGEXP '花蓮|台東' THEN 'W'
                        WHEN j.address_region REGEXP '澎湖|金門|連江|馬祖' THEN 'OI'
                        ELSE 'OS'
                    END AS region_group,

                    j.salary_type_code,
                    j.job_name AS job_title,
                    c.cust_name AS company_name,
                    c.industry_name,
                    j.address_region AS location_text,
                    j.salary_raw_text AS salary_text,
                    CONCAT(j.work_exp_requirement, ' | ', j.edu_requirement) AS exp_edu_text,
                    
                    -- work_mode
                    CASE 
                        WHEN j.remote_work_description IS NULL THEN '公司未提供此資訊'
                        ELSE j.remote_work_description
                    END AS work_mode,
                    
                    -- skills_json
                    COALESCE(sa.skills_json, JSON_ARRAY()) AS skills_json,
                    
                    -- job_desc_short
                    LEFT(j.job_description, 80) AS job_desc_short,
                    
                    CONCAT('https://www.104.com.tw/job/', j.job_id) AS job_url
                FROM silver_db.job j
                JOIN silver_db.company c 
                    ON j.cust_no = c.cust_no
                LEFT JOIN job_skills_aggregated sa 
                    ON j.job_id = sa.job_id
                    WHERE j.url_status = 'on';
            """

            sql_insert_category = """
            INSERT INTO gold_db.bridge_job_category (
                job_id,
                category_code
            )
            SELECT j.job_id, ca.category_code FROM
                (SELECT job_id, category_code FROM silver_db.job_category) ca
            join
                (SELECT job_id, url_status FROM silver_db.job
                where url_status = 'on') j
            on ca.job_id = j.job_id;
            """
            # 執行 SQL 指令
            print("開始清空舊資料...")
            for sql in sql_truncate:
                cursor.execute(sql)
            print("開始第四頁寫入最新資料...")
            cursor.execute(sql_insert_card)
            print(f"fact_job_cards 寫入完成！")
            cursor.execute(sql_insert_category)
            print(f"bridge_job_category 寫入完成！")
            
        # 提交事務 (Transaction Commit)
        conn.commit()
        print("第四頁寫入成功！")
        return True

    except Exception as e:
        # 發生例外時回滾，確保資料一致性
        if conn:
            conn.rollback()
        print(f"執行 insert_into_page4 時發生錯誤: {e}")
        raise e

if __name__ == "__main__":
    conn = conn_to_mysql(db_name="gold_db")
    if conn:
        try:
            insert_into_page4(conn)
        finally:
            conn.close()
