import os
from dotenv import load_dotenv
from pymysql import connect
import pymysql
import json
import re
from openai import OpenAI

def conn_to_mysql_gold():
    #載入.env 到環境變數
    load_dotenv()
    # 若參數未傳入，則從環境變數取得；若環境變數未設定，再使用預設值
    db_name = os.getenv("MYSQL_GOLD_DATABASE")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_ROOT_PASSWORD")
    conn_ip = os.getenv("MYSQL_HOST")
    # port 轉整數防呆
    raw_port = os.getenv("MYSQL_PORT")
    port = int(raw_port) if raw_port else 3307
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

def query_raw_skill_name(conn):
    """撈出金表中尚未填入 std_skill_name 的原始技能資料"""
    try:
        with conn.cursor() as cursor:
            sql = """
                select raw_skill_name 
                from gold_db.ref_skill_synonym_map
                where std_skill_name is null or trim(std_skill_name) = ''
                group by raw_skill_name
                order by raw_skill_name asc;
            """
            cursor.execute(sql)
            raw_results = cursor.fetchall()
            list = [row[0] for row in raw_results]
            print(f"{list}")
            return list
    except Exception as e:
        print(f"撈取未對照技能失敗: {e}")
        return []

def first_phase_insert_into(conn):
    """第一頁金表第一階段寫入"""
    try:
        with conn.cursor() as cursor:
            sql_dim_skill_option = """
                INSERT INTO gold_db.dim_skill_option (
                skill_code,
                raw_skill_name,
                source_type
                )
                -- 1. 撈取並去重 job_skill (工具類)
                select * from (
                SELECT 
                    skill_code,
                    skill_description AS raw_skill_name,
                    'skill' AS source_type
                FROM silver_db.job_skill
                GROUP BY skill_code, skill_description

                UNION ALL

                -- 2. 撈取並去重 job_specialty (專長類)
                SELECT 
                    specialty_code AS skill_code,
                    specialty_name AS raw_skill_name,
                    'specialty' AS source_type
                FROM silver_db.job_specialty
                GROUP BY specialty_code, specialty_name
                )
                AS new_data
                ON DUPLICATE KEY UPDATE
                raw_skill_name = new_data.raw_skill_name,
                source_type = new_data.source_type;
            """
            
            sql_ref_skill_synonym_map="""
                INSERT IGNORE INTO gold_db.ref_skill_synonym_map (
                    raw_skill_name
                )
                SELECT skill_description AS raw_skill_name
                FROM silver_db.job_skill
                GROUP BY skill_description

                UNION

                SELECT specialty_name AS raw_skill_name
                FROM silver_db.job_specialty
                GROUP BY specialty_name;
            """
            # 執行 SQL 指令
            print("正在寫入 gold_db.dim_skill_option...")
            cursor.execute(sql_dim_skill_option)
            
            print("正在寫入 gold_db.ref_skill_synonym_map...")
            cursor.execute(sql_ref_skill_synonym_map)
            
        # 提交事務 (Transaction Commit)
        conn.commit()
        print("第一階段寫入成功！")
        return True

    except Exception as e:
        # 發生例外時回滾，確保資料一致性
        if conn:
            conn.rollback()
        print(f"執行 first_phase_insert_into 時發生錯誤: {e}")
        raise e

def check_box_and_category_refer(conn):
    """撈出金表 ref_skill_synonym_map 中提供給 AI 的現有參考資料"""
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql_std_and_category = """
            select std_skill_name,skill_category from gold_db.ref_skill_synonym_map
            group by std_skill_name,skill_category;
            """
            cursor.execute(sql_std_and_category)
            raw_results = cursor.fetchall()
            return raw_results
            # print(f"{raw_results}")
    except Exception as e:
        print(f"撈取AI參考失敗: {e}")
        return []

def requir_AI_process_raw_skill_name(
    new_skills,
    check_box_and_category_list,):
    """呼叫 AI 產生或匹配 std_skill_name 與分配 skill_category"""
    if not new_skills:
        return []

    load_dotenv()
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")

    if not nvidia_api_key:
        print("❌ 錯誤：未讀取到 NVIDIA_API_KEY 環境變數！")
        return []

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nvidia_api_key,
    )

    # 💡 將 Dict List 壓縮為極簡的 {"std_skill_name": "skill_category"} 映射字串，大幅省下 Token
    compact_mapping = {
        item["std_skill_name"]: item["skill_category"]
        for item in check_box_and_category_list
        if item.get("std_skill_name") and item.get("skill_category")
    }

    prompt = f"""
        你是一個專業的 IT 與資料工程職涯技能分析專家。
        我們的系統需要在 UI 第一頁提供具體、明確且符合良好的 UX (使用者體驗) 膠囊勾選項 (std_skill_name)。

        【現有的 Checkbox 標準技能及其對應分類】：
        (若選擇現有的 Checkbox，skill_category 必須嚴格等於對應的分類)
        {json.dumps(compact_mapping, ensure_ascii=False) if compact_mapping else "目前尚無既有選單，請建立精簡之標準名稱。"}

        【可選的大分類列表 (skill_category)】：
            "行政與後勤支援",
            "專案與流程管理",
            "ESG與永續發展",
            "財務與會計審計",
            "行銷與品牌營運",
            "產品設計與營運",
            "數據分析與商業情報",
            "業務銷售與客戶服務",
            "軟體工程與系統開發",
            "程式語言與開發工具",
            "Web與前端開發技術",
            "人工智慧與前沿技術",
            "資料庫與數據工程",
            "雲端架構與DevOps",
            "系統與維運管理",
            "網路與資訊安全",
            "電子與硬體工程",
            "生產品管與自動化",
            "視覺設計與多媒體",
            "工業與建築設計",
            "企業管理軟體 (ERP/CRM)",
            "辦公室軟體與工具",
            "通訊與電信工程",
            "生化與醫療衛生",

        【嚴格執行規則】：

        一、 大分類 (skill_category) 選擇規範：
        1. **優先選用既有分類**：處理全新技能時，請從【可選的大分類列表】中挑選最合適的 `skill_category`，請勿自行創立。
        2. 若現有選擇沒有相符的 skill_category，就寫入"未有合適的分類"
        二、 標準技能名稱 (std_skill_name) 介面與收攏規範：
        1. **最高原則 (優先對照既有選單)**：分析傳入的 `raw_skill_name`，若語意可對應到【現有的 Checkbox 標準技能】，請**務必完全採用該清單中的標準文字** (文字需完全一致)；且 `skill_category` 必須為清單中該技能指定的分類。
        
        2. **關鍵硬規則 (絕不可與大分類同名)**：
           - `std_skill_name` 是前端供使用者點擊的膠囊按鈕，**絕對不可以**與 `skill_category` 大分類名稱完全相同（例如：當分類為「商業智慧與數據分析」時，技能名稱決不能只寫「數據分析」）。
           - 長度強制控制在 15 字以內，適合 UI 膠囊按鈕展示。

        3. **通用領域強收攏規則 (優先執行)**：
           - **SQL與資料庫方言**：凡屬於 SQL 語法方言、資料庫產品變體（如：ANSI SQL、PL/SQL、MSSQL、MySQL、PostgreSQL），一律統一標準化收攏為 `SQL`。
           - **語言與平台環境**：若技能包含核心程式語言 + 平台/環境/後綴（如：C++.Net），請直接收攏為核心語言名稱（如：C++）。
           - **系統與版本細節**：去除無意義的版本號與速度細節。如 Windows 10/11 統一為 `Windows OS`；Windows Server 2012/2019 統一為 `Windows Server`。

        4. **近義詞與工具鏈合併風格 (UX 兜底原則)**：
           - 若非上述特定領域，但遇到極度相似、同屬性的工具鏈或軟體變體（如 Git/GitHub、Looker Studio/Data Studio、AutoCAD 2D/3D），請使用斜線 `/` 收攏為單一標準選項（例如：`Git / GitHub`、`Looker Studio / Data Studio`），避免前端產生過於細碎、重複感強烈的按鈕。

        待處理技能資料:
        {json.dumps(new_skills, ensure_ascii=False)}

        【輸出格式極度嚴格要求】：
        你必須**僅回傳純 JSON 陣列**，絕對不要包含任何開場白、結語或說明文字！
        不要加任何 Markdown 文字，直接從 [ 開始，以 ] 結束。

        格式範例：
        [
          {{
            "raw_skill_name": "Python3",
            "std_skill_name": "Python",
            "skill_category": "程式語言與開發工具"
          }}
        ]
        """

    try:
            response = client.chat.completions.create(
                model="nvidia/nemotron-3.5-lightning-30b-a3b",  # 請確認 model 名稱無誤 
                messages=[
                    {
                        "role": "system",
                        "content": "You are a JSON generator. Do not show thinking process. Output pure JSON array only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,  # 保持極低隨機性
                max_tokens=2048,
                timeout=60.0,
                extra_body={
                "chat_template_args": {
                    "enable_thinking": False
                }  # 關閉思考模式，防止贅字
            },
            )
            res_text = response.choices[0].message.content.strip()

            # 💡 正則表達式：自動搜尋第一個 [ 到最後一個 ] 裡面的內容 (確保抓到 JSON Array)
            match = re.search(r"\[.*\]", res_text, re.DOTALL)
            if match:
                clean_json_str = match.group(0)
                results = json.loads(clean_json_str)
                return results
            else:
                # 備用方案：若沒抓到中括號，嘗試做基礎字串清理後解析
                clean_text = re.sub(r"^```json|^```|```$", "", res_text, flags=re.MULTILINE).strip()
                return json.loads(clean_text)

    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失敗！AI 回傳內容不符 JSON 格式。錯誤: {e}", flush=True)
        print(f"⚠️ 原始 AI 回傳字串為:\n{res_text}", flush=True)
        return []
    except Exception as e:
        print(f"❌ NVIDIA AI 判斷失敗: {e}", flush=True)
        return []

def save_to_mapping_and_gold(processed_data,conn):
    """更新至對照紀錄表 (ref_skill_synonym_map) 與第一頁金表 (dim_skill_option)"""
    if not processed_data:
        return

    try:
        with conn.cursor() as cursor:
            # 1. 寫入/更新對照表 (紀錄 raw_skill_name -> std_skill_name 對應)
            sql_map = """
                INSERT INTO gold_db.ref_skill_synonym_map (raw_skill_name, std_skill_name, skill_category)
                VALUES (%(raw_skill_name)s, %(std_skill_name)s, %(skill_category)s)
                ON DUPLICATE KEY UPDATE
                    std_skill_name = VALUES(std_skill_name),
                    skill_category = VALUES(skill_category);
            """
            cursor.executemany(sql_map, processed_data)

            # 2. 直接針對該批次的 raw_skill_name 更新金表
            sql_gold = """
                UPDATE gold_db.dim_skill_option
                SET std_skill_name = %(std_skill_name)s,
                    skill_category = %(skill_category)s
                WHERE raw_skill_name = %(raw_skill_name)s;
            """
            cursor.executemany(sql_gold, processed_data)
        #gold_db.raw_skills
        conn.commit()
        print(f"成功更新 {len(processed_data)} 筆技能資料至 MySQL 金表與對照表！")
    except Exception as e:
        print(f"資料庫更新失敗: {e}")
        conn.rollback()

def run_pipeline():
    conn = conn_to_mysql_gold()
    try:
        first_phase_insert_into(conn)
        print("\n撈取尚未更新 std_skill_name 的原始資料...")
        loop_count = 1
        while True:
            print(f"\n--- [第 {loop_count} 次檢查未處理資料] ---", flush=True)
            unmapped_skills = query_raw_skill_name(conn)
            # 沒有空白資料即跳出迴圈
            if not unmapped_skills:
                print("🎉 所有人資/爬蟲原始技能均已完成對照與標準化！", flush=True)
                break

            print(
                f"共找到 {len(unmapped_skills)} 筆待處理項目，開始執行 AI 標準化對齊...",
                flush=True,
            )
            
            BATCH_SIZE = 10
            # 1. 在迴圈外撈取靜態參考資料（只撈一次，節省 SQL 開銷）
            # List[Dict], 如 [{"std_skill_name": "...", "skill_category": "..."}] 
            check_and_category = check_box_and_category_refer(conn)
            
            # 2. 建立記憶體快速比對 Set (用來記錄目前已經存在的所有 std_skill_name)
            existing_std_set = {
                item["std_skill_name"]
                for item in check_and_category
                if item.get("std_skill_name")
            }

            for i in range(0, len(unmapped_skills), BATCH_SIZE):
                batch = unmapped_skills[i : i + BATCH_SIZE]
                print(f"\n處理解第 {i + 1} ~ {i + len(batch)} 筆技能中...")
                # 每一批次都要 重新撈新的資料，防止同批或下一批產生微小重複名稱
                ai_results = requir_AI_process_raw_skill_name(batch,check_and_category)

                if ai_results:
                    save_to_mapping_and_gold(ai_results,conn)

                    # 3. 動態把這批次產生的全新技能補入記憶體清單中
                    for res in ai_results:
                        new_std = res.get("std_skill_name")
                        new_cate = res.get("skill_category")

                        # 若這個 std_skill_name 是全新的，就補進快取中給後續批次參考
                        if new_std and new_std not in existing_std_set:
                            existing_std_set.add(new_std)

                            # 同步加入給 AI 的參考選單 (Dict 格式)
                            check_and_category.append(
                                {"std_skill_name": new_std, "skill_category": new_cate}
                            )

                            print(
                                f"✨ 發現全新領域技能，已動態擴充 Checkbox 選項: [{new_std}] (分類: {new_cate})",
                                flush=True,
                            )
            loop_count += 1

    finally:
        # 💡 在所有 Task 執行完成後，於主流程統一關閉連線
        if conn and conn.open:
            conn.close()
            print("\n🎉 所有 std_skill_name 處理完成！", flush=True)

if __name__ == "__main__":
    run_pipeline()
