import os
import sys
import pymysql
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_tables.conn_to_gold import conn_to_gold

def init_gold_database():
    load_dotenv()
    gold_db = os.getenv("MYSQL_GOLD_DATABASE", "gold_db")

    # 1. 先確認資料庫存在
    sys_conn = conn_to_gold("mysql")
    if sys_conn:
        try:
            with sys_conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {gold_db} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print(f"已確認/建立資料庫: {gold_db}")
        finally:
            sys_conn.close()

    # 2. 建立資料表與補齊欄位
    gold_conn = conn_to_gold(gold_db)
    if not gold_conn:
        print("無法連線至 gold_db")
        return

    try:
        with gold_conn.cursor() as cursor:
            # # 建立 0. ref_skill_synonym_map
            # cursor.execute("""
            #     CREATE TABLE IF NOT EXISTS ref_skill_synonym_map (
            #         raw_skill_name VARCHAR(100) NOT NULL PRIMARY KEY,
            #         std_skill_name VARCHAR(100) NULL,
            #         skill_category VARCHAR(50) NULL,
            #         create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            #         update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            # """)

            # # 建立 1. dim_skill_option
            # cursor.execute("""
            #     CREATE TABLE IF NOT EXISTS dim_skill_option (
            #         skill_code VARCHAR(50) PRIMARY KEY,
            #         raw_skill_name VARCHAR(100) NULL,
            #         std_skill_name VARCHAR(100) NULL,
            #         skill_category VARCHAR(50) NULL,
            #         source_type VARCHAR(20) NULL,
            #         is_core_skill BOOLEAN DEFAULT FALSE,
            #         create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            #         update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            # """)

            # # 檢查並補齊 dim_skill_option.is_core_skill 欄位
            # cursor.execute("""
            #     SELECT COUNT(*) FROM information_schema.COLUMNS 
            #     WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'dim_skill_option' AND COLUMN_NAME = 'is_core_skill';
            # """, (gold_db,))
            # if cursor.fetchone()[0] == 0:
            #     cursor.execute("ALTER TABLE dim_skill_option ADD COLUMN is_core_skill BOOLEAN DEFAULT FALSE AFTER source_type;")

            # # 建立 2. fact_category_skill_weight
            # cursor.execute("""
            #     CREATE TABLE IF NOT EXISTS fact_category_skill_weight (
            #         category_code VARCHAR(50) NOT NULL,
            #         category_name VARCHAR(100) NOT NULL,
            #         skill_code VARCHAR(50) NOT NULL,
            #         std_skill_name VARCHAR(100) NOT NULL,
            #         raw_skill_name VARCHAR(100) NULL,
            #         weight DECIMAL(7,4) NOT NULL,
            #         PRIMARY KEY (category_code, skill_code)
            #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            # """)

            # # 建立 3. fact_job_ratio
            # cursor.execute("""
            #     CREATE TABLE IF NOT EXISTS fact_job_ratio (
            #         category_code VARCHAR(50) PRIMARY KEY,
            #         category_name VARCHAR(100) NOT NULL,
            #         job_count INT NOT NULL,
            #         category_job_ratio DECIMAL(7,4) NOT NULL
            #     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            # """)

            # 建立 4. fact_category_salary_stat (整合所有欄位與 UNIQUE KEY 複合索引)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fact_category_salary_stat (
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
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

        #     # 建立 5. fact_job_cards
        #     cursor.execute("""
        #         CREATE TABLE IF NOT EXISTS fact_job_cards (
        #             job_id VARCHAR(50) NOT NULL,
        #             bridge_job_category VARCHAR(150) NOT NULL,
        #             category_code VARCHAR(50) NOT NULL,
        #             salary_type_code VARCHAR(20) NOT NULL,
        #             region_group VARCHAR(20) NOT NULL,
        #             job_title VARCHAR(150) NOT NULL,
        #             exp_level VARCHAR(50) NOT NULL,
        #             company_name VARCHAR(150) NOT NULL,
        #             industry_name VARCHAR(100) NULL,
        #             location_text VARCHAR(100) NULL,
        #             salary_text VARCHAR(100) NULL,
        #             exp_edu_text VARCHAR(100) NULL,
        #             work_mode VARCHAR(50) NULL,
        #             skills_json JSON NULL,
        #             job_desc_short VARCHAR(255) NULL,
        #             job_url VARCHAR(500) NOT NULL,
        #             create_time DATETIME NOT NULL,
        #             PRIMARY KEY (bridge_job_category)
        #         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        #     """)

        # print("六張金表與 Mapping 對照表已全數建置/檢查更新完成！")
    finally:
        gold_conn.close()

if __name__ == "__main__":
    init_gold_database()



# import json
# import os
# from google import genai
# from google.genai import types
# from dotenv import load_dotenv
# from pymysql import connect

# # ==========================================
# # 1. 設定與連線資訊
# # ==========================================
# # 載入 .env 檔案中的環境變數
# load_dotenv()

# # 初始化 Gemini API Client
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
# client = genai.Client(api_key=GEMINI_API_KEY)


# def conn_to_mysql():
#     """建立與 MySQL 的連線，並回傳連線物件"""
#     # 載入 .env (已在全域載入，此處確保安全性)
#     load_dotenv()
    
#     # 這裡將 MYSQL_DATABASE 改為 MYSQL_GOLD_DATABASE，對應您 .env 內的 gold_db
#     db_name = os.getenv("MYSQL_GOLD_DATABASE")
#     user = os.getenv("MYSQL_USER")
#     password = os.getenv("MYSQL_ROOT_PASSWORD")
    
#     # 處理 Windows VSCode 無法解析 host.docker.internal 的問題
#     raw_host = os.getenv("MYSQL_HOST")
#     conn_ip = "127.0.0.1" if raw_host == "host.docker.internal" else raw_host
    
#     raw_port = os.getenv("MYSQL_PORT")
#     port = int(raw_port) if raw_port else 3307

#     try:
#         # 建立 MySQL 連線
#         return connect(
#             host=conn_ip,
#             port=port,
#             user=user,
#             password=password,
#             database=db_name,
#             connect_timeout=10,  # 10秒連不上自動拋出例外
#             read_timeout=30,     # 讀寫超過30秒自動中斷，避免無效卡死
#             write_timeout=30,    # 寫入超過30秒自動中斷，避免無效卡死
#             autocommit=False,
#             charset="utf8mb4"    # 確保中文寫入無亂碼
#         )
#     except Exception as exc:
#         print(f"連線失敗，請確認 MySQL 伺服器是否有啟動。錯誤訊息: {exc}")
#         return None


# # ==========================================
# # 2. 核心功能函式
# # ==========================================
# def get_existing_std_skills():
#     """從對照表/金表撈出目前『已經存在』的 std_skill_name 標準清單"""
#     conn = conn_to_mysql()
#     if not conn:
#         return []
        
#     try:
#         with conn.cursor() as cursor:
#             sql = "SELECT DISTINCT std_skill_name FROM ref_skill_synonym_map WHERE std_skill_name IS NOT NULL AND TRIM(std_skill_name) != ''"
#             cursor.execute(sql)
#             results = cursor.fetchall()
#             return [row[0] for row in results]
#     except Exception as e:
#         print(f"撈取既有標準技能清單失敗: {e}")
#         return []
#     finally:
#         conn.close()


# def get_unmapped_raw_skills():
#     """撈出金表中尚未填入 std_skill_name 的原始技能資料"""
#     conn = conn_to_mysql()
#     if not conn:
#         return []
        
#     try:
#         with conn.cursor() as cursor:
#             sql = """
#             SELECT skill_code, raw_skill_name 
#             FROM dim_skill_option 
#             WHERE std_skill_name IS NULL OR TRIM(std_skill_name) = '';
#             """
#             cursor.execute(sql)
#             results = cursor.fetchall()
#             return [
#                 {"skill_code": row[0], "raw_skill_name": row[1]}
#                 for row in results
#             ]
#     except Exception as e:
#         print(f"撈取未對照技能失敗: {e}")
#         return []
#     finally:
#         conn.close()


# def ask_ai_for_std_skill_name(new_skills, existing_std_names):
#     """呼叫 AI 產生或匹配 std_skill_name 與分配 skill_category"""
#     if not new_skills:
#         return []

#     prompt = f"""
# 你是一個專業的 IT 與資料工程職涯技能分析專家。
# 我們的系統需要在 UI 第一頁提供具體、明確的 Checkbox 勾選項 (std_skill_name)。

# 【現有的 Checkbox 標準技能清單 (優先對照與選擇以下項目)】:
# {json.dumps(existing_std_names, ensure_ascii=False)}

# 【大分類可選列表 (skill_category)】:
# - 程式語言與開發工具
# - 資料庫與數據處理
# - 資料處理與數據工程
# - 雲端與數據架構
# - 系統與維運管理
# - 軟體工程與品質
# - AI與機器學習
# - 商業智慧與視覺化

# 【嚴格執行規則】:
# 1. **絕不可混淆分類與選項**: `std_skill_name` 是卡片內具體的 Checkbox 點擊選項（如 "MySQL"、"Python"、"ETL"），絕不可直接填寫與 `skill_category` 大分類完全相同的籠統名稱。
# 2. **優先對照**: 分析傳入的 `raw_skill_name`，若語意可歸類到【現有的 Checkbox 標準技能清單】，請直接沿用該標準名稱。
#    - 範例: 若 raw_skill_name 為 "DB2" 或 "SYSBASE"，優先歸類至現有的 "SQL / 關係型資料庫"。
# 3. **新增標準**: 若傳入的技能屬於全新項目且現有清單無合適對應，請新增一個具體、精簡的 Checkbox 標準名稱。
# 4. 為每個項目挑選一個最合適的 `skill_category`（注意: 分類字串切勿包含任何圖釘或 Emoji 符號）。

# 待處理技能資料:
# {json.dumps(new_skills, ensure_ascii=False)}

# 請嚴格回傳 JSON Array 格式，保留原始的 skill_code 與 raw_skill_name。
# """

#     try:
#         response = client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=prompt,
#             config=types.GenerateContentConfig(
#                 response_mime_type="application/json"
#             ),
#         )
#         return json.loads(response.text)
#     except Exception as e:
#         print(f"AI 判斷失敗: {e}")
#         return []


# def save_to_mapping_and_gold(processed_data):
#     """更新至對照紀錄表 (ref_skill_synonym_map) 與第一頁金表 (dim_skill_option)"""
#     if not processed_data:
#         return

#     conn = conn_to_mysql()
#     if not conn:
#         return

#     try:
#         with conn.cursor() as cursor:
#             # 1. 寫入 / 更新對照表
#             sql_map = """
#             INSERT INTO ref_skill_synonym_map (raw_skill_name, std_skill_name, skill_category)
#             VALUES (%(raw_skill_name)s, %(std_skill_name)s, %(skill_category)s)
#             ON DUPLICATE KEY UPDATE
#                 std_skill_name = VALUES(std_skill_name),
#                 skill_category = VALUES(skill_category);
#             """
#             cursor.executemany(sql_map, processed_data)

#             # 2. 更新金表
#             sql_gold = """
#             INSERT INTO dim_skill_option (skill_code, raw_skill_name, std_skill_name, skill_category)
#             VALUES (%(skill_code)s, %(raw_skill_name)s, %(std_skill_name)s, %(skill_category)s)
#             AS new
#             ON DUPLICATE KEY UPDATE
#                 std_skill_name = new.std_skill_name,
#                 skill_category = new.skill_category;
#             """
#             cursor.executemany(sql_gold, processed_data)

#             # 記得 Commit
#             conn.commit()
#             print(f"成功更新 {len(processed_data)} 筆技能資料至 MySQL 金表與對照表！")
#     except Exception as e:
#         print(f"資料庫更新失敗: {e}")
#         conn.rollback()
#     finally:
#         conn.close()


# # ==========================================
# # 3. 主執行流程
# # ==========================================
# def run_pipeline():
#     print("Step 1. 載入既有 std_skill_name 勾選項清單...")
#     existing_std_names = get_existing_std_skills()
#     print(f"目前已有 {len(existing_std_names)} 個已對齊的 Checkbox 選項。")

#     print("\nStep 2. 撈取尚未更新 std_skill_name 的原始資料...")
#     unmapped_skills = get_unmapped_raw_skills()

#     if not unmapped_skills:
#         print("所有人資/爬蟲原始技能均已完成對照與標準化！")
#         return

#     print(f"共找到 {len(unmapped_skills)} 筆待處理項目，開始執行 AI 標準化對齊...")

#     BATCH_SIZE = 30
#     for i in range(0, len(unmapped_skills), BATCH_SIZE):
#         batch = unmapped_skills[i : i + BATCH_SIZE]
#         print(f"\n處理解第 {i + 1} ~ {i + len(batch)} 筆技能中...")

#         ai_results = ask_ai_for_std_skill_name(batch, existing_std_names)

#         if ai_results:
#             save_to_mapping_and_gold(ai_results)

#             for res in ai_results:
#                 new_std = res.get("std_skill_name")
#                 if new_std and new_std not in existing_std_names:
#                     existing_std_names.append(new_std)
#                     print(f" 發現全新領域技能，已新增 Checkbox 選項: {new_std}")

#     print("\n所有 std_skill_name 處理完成！")


# if __name__ == "__main__":
#     run_pipeline()