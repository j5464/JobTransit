import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_tables.conn_to_gold import conn_to_gold

def clean_fact_category_salary_stat():
    load_dotenv()
    silver_db = os.getenv("MYSQL_DATABASE", "tkr102")
    gold_db = os.getenv("MYSQL_GOLD_DATABASE", "gold_db")

    gold_conn = conn_to_gold(gold_db)
    silver_conn = conn_to_gold(silver_db)

    if not gold_conn or not silver_conn:
        print("無法取得資料庫連線。")
        return

    print("開始執行 fact_category_salary_stat.py 清洗...")
    try:
        sql_stat = f"""
            WITH RawSalary AS (
                SELECT 
                    j.job_id,
                    jc.category_code,
                    -- 分類名稱防呆修復：若 category_description 為空，優先使用 category_code 替代
                    COALESCE(NULLIF(jc.category_description, ''), jc.category_code, '未定義類別') AS category_name,
                    j.salary_type_code,
                    
                    -- 串接所有可能包含地區資訊的欄位（縣市、鄉鎮市區、詳細地址、職缺標題）
                    CONCAT(
                        IFNULL(j.address_region, ''), 
                        IFNULL(j.address_area, ''), 
                        IFNULL(j.address_detail, ''), 
                        IFNULL(j.job_name, '')
                    ) AS full_location_text,
                    
                    -- 薪資防呆過濾
                    CASE WHEN j.salary_min > 0 THEN j.salary_min ELSE NULL END AS raw_min,
                    CASE WHEN j.salary_max > 0 AND j.salary_max < 999999 THEN j.salary_max ELSE NULL END AS raw_max
                FROM {silver_db}.job j
                LEFT JOIN {silver_db}.job_category jc ON j.job_id = jc.job_id
                WHERE j.url_status = 'on'
            ),
            NormalizedJobSalary AS (
                SELECT 
                    job_id,
                    category_code,
                    category_name,
                    salary_type_code,
                    
                    -- 地區比對邏輯 (涵蓋縣市、舊稱、簡稱、園區、主要行政區)
                    CASE 
                        -- 1. 北部地區
                        WHEN full_location_text REGEXP '台北|臺北|北市|新北|基隆|桃園|桃市|新竹|竹市|竹縣|竹科|宜蘭|板橋|新莊|三重|中和|永和|新店|汐止|土城|蘆洲|樹林|淡水|三峽|內湖|南港|信義|大安|中山|中正|松山|士林|北投|文山|萬華|大同|中壢|平鎮|八德|楊梅|蘆竹|龜山|龍潭|大溪|竹北|竹東' THEN '北部地區'
                        
                        -- 2. 中部地區
                        WHEN full_location_text REGEXP '台中|臺中|中市|苗栗|彰化|彰市|南投|雲林|中科|西屯|北屯|南屯|豐原|大里|太平|烏日|潭子|沙鹿|員林|和美|鹿港|斗六|虎尾|麥寮' THEN '中部地區'
                        
                        -- 3. 南部地區
                        WHEN full_location_text REGEXP '高雄|高市|台南|臺南|南市|嘉義|嘉市|屏東|南科|左營|楠梓|前鎮|苓雅|三民|鳳山|小港|鼓山|安平|永康|歸仁|新市|善化|仁德' THEN '南部地區'
                        
                        -- 4. 東部地區
                        WHEN full_location_text REGEXP '花蓮|台東|臺東|羅東' THEN '東部地區'
                        
                        -- 5. 離島地區（加入綠島）
                        WHEN full_location_text REGEXP '澎湖|金門|連江|馬祖|綠島' THEN '離島地區'
                        
                        -- 6. 海外地區（未命中前述台灣各區者直接歸類為海外地區）
                        ELSE '海外地區'
                    END AS region_group,

                    -- 薪資雙向互補修復：若只有單邊薪資，強制讓 min 與 max 相等
                    COALESCE(raw_min, raw_max) AS norm_salary_min,
                    COALESCE(raw_max, raw_min) AS norm_salary_max
                FROM RawSalary
            ),
            JobWithMid AS (
                SELECT 
                    *,
                    CASE 
                        WHEN norm_salary_min IS NOT NULL AND norm_salary_max IS NOT NULL 
                        THEN (norm_salary_min + norm_salary_max) / 2.0 
                        ELSE NULL 
                    END AS norm_salary_mid
                FROM NormalizedJobSalary
            ),
            -- 嚴謹計算分組中位數 (Median) - 僅針對有有效薪資的資料進行排序與計算
            RankedSalary AS (
                SELECT 
                    category_code,
                    category_name,
                    salary_type_code,
                    region_group,
                    norm_salary_mid,
                    ROW_NUMBER() OVER (
                        PARTITION BY category_code, salary_type_code, region_group 
                        ORDER BY norm_salary_mid
                    ) AS row_num,
                    COUNT(norm_salary_mid) OVER (
                        PARTITION BY category_code, salary_type_code, region_group
                    ) AS total_count
                FROM JobWithMid
                WHERE norm_salary_mid IS NOT NULL
            ),
            MedianCalc AS (
                SELECT 
                    category_code,
                    salary_type_code,
                    region_group,
                    ROUND(AVG(norm_salary_mid), 2) AS median_salary
                FROM RankedSalary
                WHERE row_num IN (FLOOR((total_count + 1) / 2.0), CEIL((total_count + 1) / 2.0))
                GROUP BY category_code, salary_type_code, region_group
            )
            SELECT 
                j.category_code,
                j.category_name,
                j.salary_type_code,
                j.region_group,
                COUNT(DISTINCT j.job_id) AS job_count,
                ROUND(AVG(j.norm_salary_min), 2) AS avg_salary_min,
                ROUND(AVG(j.norm_salary_max), 2) AS avg_salary_max,
                ROUND(AVG(j.norm_salary_mid), 2) AS avg_salary_mid,
                m.median_salary
            FROM JobWithMid j
            LEFT JOIN MedianCalc m 
                   ON j.category_code = m.category_code 
                  AND j.salary_type_code = m.salary_type_code 
                  AND j.region_group = m.region_group
            GROUP BY 
                j.category_code, 
                j.category_name,
                j.salary_type_code, 
                j.region_group,
                m.median_salary;
        """
        
        with silver_conn.cursor() as s_cur:
            s_cur.execute(sql_stat)
            columns = [col[0] for col in s_cur.description]
            results = [dict(zip(columns, row)) for row in s_cur.fetchall()]

        if not results:
            print("警告：未清洗出任何統計數據，請檢查銀表資料庫與 .env 設定。")
            return

        with gold_conn.cursor() as g_cur:
            # 安全寫入：改為 ON DUPLICATE KEY UPDATE 避免資料被清空
            sql_insert = f"""
                INSERT INTO {gold_db}.fact_category_salary_stat (
                    category_code, category_name, salary_type_code, region_group, job_count, avg_salary_min, avg_salary_max, avg_salary_mid, median_salary
                ) VALUES (
                    %(category_code)s, %(category_name)s, %(salary_type_code)s, %(region_group)s, %(job_count)s, %(avg_salary_min)s, %(avg_salary_max)s, %(avg_salary_mid)s, %(median_salary)s
                ) ON DUPLICATE KEY UPDATE
                    category_name = VALUES(category_name),
                    job_count = VALUES(job_count),
                    avg_salary_min = VALUES(avg_salary_min),
                    avg_salary_max = VALUES(avg_salary_max),
                    avg_salary_mid = VALUES(avg_salary_mid),
                    median_salary = VALUES(median_salary);
            """
            g_cur.executemany(sql_insert, results)

        gold_conn.commit()
        print(f"fact_category_salary_stat 處理與修正完成，共寫入/更新 {len(results)} 筆資料！")

    except Exception as e:
        if gold_conn:
            gold_conn.rollback()
        print(f"執行過程中發生錯誤: {e}")

    finally:
        gold_conn.close()
        silver_conn.close()

if __name__ == "__main__":
    clean_fact_category_salary_stat()