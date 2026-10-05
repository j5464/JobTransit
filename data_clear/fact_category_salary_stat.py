import os
import sys
from dotenv import load_dotenv

from pymysql import connect

# 載入 .env 檔案中的環境變數，讓資料庫設定可被外部配置
load_dotenv()


# 建立與 MySQL 的連線，並回傳連線物件
# 若有參數傳入，會覆蓋環境變數；否則會使用預設值
# 例如：MYSQL_DB、MYSQL_USER、MYSQL_PASSWORD、MYSQL_HOST、MYSQL_PORT

def conn_to_mysql(
    db_name: str | None = None,
    # user: str | None = None,
    # password: str | None = None,
    # conn_ip: str | None = None,
    # port: int | None = None,
):
  
    
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
    
def clean_fact_category_salary_stat():
    load_dotenv()
    gold_db = os.getenv("MYSQL_GOLD_DATABASE", "gold_db")
    gold_conn = conn_to_mysql(db_name=gold_db)

    if not gold_conn:
        print("無法取得 Gold DB 資料庫連線。")
        return

    print("開始執行 fact_category_salary_stat.py 清洗修復...")
    try:
        with gold_conn.cursor() as g_cur:
            sql_clean = f"""
                WITH ParsedJobs AS (
                    SELECT 
                        c.job_id,
                        r.category_code,
                        r.category_name,
                        c.salary_type_code,
                        c.region_group,
                        CASE 
                            WHEN c.exp_edu_text REGEXP '10年|11年|12年|13年|14年|15年|20年|10以上' THEN '10年以上'
                            WHEN c.exp_edu_text REGEXP '7年|8年|9年|7~9|7-9' THEN '7~9年'
                            WHEN c.exp_edu_text REGEXP '4年|5年|6年|4~6|4-6|5年以上' THEN '4~6年'
                            WHEN c.exp_edu_text REGEXP '1年|2年|3年|1~3|1-3' THEN '1~3年'
                            ELSE '不拘'
                        END AS exp_level,
                        
                        -- 解析薪資下限 (Min)
                        CASE 
                            WHEN c.salary_text REGEXP '[0-9]+萬' THEN CAST(REGEXP_SUBSTR(c.salary_text, '[0-9]+(\\.[0-9]+)?') AS DECIMAL(10,2)) * 10000
                            WHEN c.salary_text REGEXP '[0-9,]+' THEN CAST(REPLACE(REGEXP_SUBSTR(c.salary_text, '[0-9,]+', 1, 1), ',', '') AS UNSIGNED)
                            ELSE NULL
                        END AS sal_min,

                        -- 解析薪資上限 (Max)
                        CASE 
                            WHEN c.salary_text REGEXP '~|-' AND c.salary_text REGEXP '[0-9,]+' THEN 
                                CAST(REPLACE(REGEXP_SUBSTR(c.salary_text, '[0-9,]+', 1, 2), ',', '') AS UNSIGNED)
                            WHEN c.salary_text REGEXP '[0-9]+萬' THEN 
                                CAST(REGEXP_SUBSTR(c.salary_text, '[0-9]+(\\.[0-9]+)?') AS DECIMAL(10,2)) * 10000
                            ELSE 
                                CAST(REPLACE(REGEXP_SUBSTR(c.salary_text, '[0-9,]+', 1, 1), ',', '') AS UNSIGNED)
                        END AS sal_max
                    FROM gold_db.fact_job_cards c
                    LEFT JOIN gold_db.bridge_job_category r ON c.job_id = r.job_id
                ),
                UniqueJobCategory AS (
                    SELECT 
                        job_id,
                        category_code,
                        MAX(category_name) AS category_name,
                        salary_type_code,
                        region_group,
                        exp_level,
                        AVG(sal_min) AS job_sal_min,
                        AVG(sal_max) AS job_sal_max
                    FROM ParsedJobs
                    GROUP BY job_id, category_code, salary_type_code, region_group, exp_level
                )
                SELECT 
                    category_code,
                    COALESCE(MAX(category_name), category_code) AS category_name,
                    salary_type_code,
                    region_group,
                    exp_level,
                    COUNT(DISTINCT job_id) AS job_count,
                    -- 取該組別中的最小下限與最大上限
                    ROUND(MIN(job_sal_min), 2) AS avg_salary_min,
                    ROUND(MAX(job_sal_max), 2) AS avg_salary_max,
                    ROUND(AVG((job_sal_min + job_sal_max) / 2), 2) AS avg_salary_mid,
                    ROUND(AVG((job_sal_min + job_sal_max) / 2), 2) AS median_salary
                FROM UniqueJobCategory
                GROUP BY category_code, salary_type_code, region_group, exp_level;
            """
            
            g_cur.execute(sql_clean)
            columns = [col[0] for col in g_cur.description]
            results = [dict(zip(columns, row)) for row in g_cur.fetchall()]

            if not results:
                print("警告：未清洗出任何數據！")
                return

            # 清空舊數據並重新寫入
            g_cur.execute(f"TRUNCATE TABLE {gold_db}.fact_category_salary_stat;")
            sql_insert = f"""
                INSERT INTO {gold_db}.fact_category_salary_stat (
                    category_code, category_name, salary_type_code, region_group, exp_level,
                    job_count, avg_salary_min, avg_salary_max, avg_salary_mid, median_salary
                ) VALUES (
                    %(category_code)s, %(category_name)s, %(salary_type_code)s, %(region_group)s, %(exp_level)s,
                    %(job_count)s, %(avg_salary_min)s, %(avg_salary_max)s, %(avg_salary_mid)s, %(median_salary)s
                );
            """
            g_cur.executemany(sql_insert, results)

        gold_conn.commit()
        print(f"清洗修復完成！共寫入 {len(results)} 筆真實數據！")

    except Exception as e:
        if gold_conn: gold_conn.rollback()
        print(f"執行過程中發生錯誤: {e}")
    finally:
        if gold_conn: gold_conn.close()

if __name__ == "__main__":
    clean_fact_category_salary_stat()