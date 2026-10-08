import os
from dotenv import load_dotenv
import json
import re
from openai import OpenAI

from airflow.sdk import task
from utils.conn_to_mysql import conn_to_mysql

def job_weight_first_phase_insert(conn):
    """第二頁金表第一階段寫入"""
    try:
        with conn.cursor() as cursor:
            sql_truncate = [
                "TRUNCATE TABLE gold_db.fact_category_skill_weight;",
                """
                UPDATE gold_db.fact_job_ratio
                SET job_count = 0, category_job_ratio = 0.0000;
                """
            ]

            sql_insert = """
            INSERT INTO gold_db.fact_category_skill_weight (
                category_code,
                category_name,
                std_skill_name,
                weight,
                is_core_skill
            )
            WITH raw_job_skills AS (
                SELECT job_id, skill_code FROM silver_db.job_skill
                UNION ALL
                SELECT job_id, specialty_code AS skill_code FROM silver_db.job_specialty
            ),
            -- 取分母 
            category_total_jobs AS (
                SELECT 
                    category_code,
                    category_description AS category_name,
                    COUNT(DISTINCT job_id) AS total_jobs
                FROM silver_db.job_category
                GROUP BY category_code, category_description
            ),
            category_std_skill_counts AS (
                SELECT 
                    jc.category_code,
                    jc.category_description AS category_name,
                    dso.std_skill_name,  -- ★ 關鍵：以歸一化後的標準技能名稱做聚合
                    COUNT(DISTINCT rjs.job_id) AS skill_job_cnt
                FROM silver_db.job_category jc
                JOIN raw_job_skills rjs ON jc.job_id = rjs.job_id
                JOIN gold_db.dim_skill_option dso ON rjs.skill_code = dso.skill_code
                GROUP BY 
                    jc.category_code, 
                    jc.category_description, 
                    dso.std_skill_name   -- ★ 相同 std_skill_name 的多個 raw 技能會在此被收攏去重！
            )
            SELECT 
                cssc.category_code,
                cssc.category_name,
                cssc.std_skill_name,
                ROUND(cssc.skill_job_cnt / ctj.total_jobs, 4) AS weight,
                IF((cssc.skill_job_cnt / ctj.total_jobs) >= 0.5000, TRUE, FALSE) AS is_core_skill
            FROM category_std_skill_counts cssc
            JOIN category_total_jobs ctj ON cssc.category_code = ctj.category_code;
            """

            sql_insert_ratio = """
            INSERT INTO gold_db.fact_job_ratio (
                category_code,
                category_name,
                job_count,
                category_job_ratio
            )
            SELECT * FROM
            (
            SELECT 
                c.category_code,
                c.category_description AS category_name,
                COUNT(DISTINCT c.job_id) AS job_count,
                COUNT(DISTINCT c.job_id) / t.total_distinct_count AS category_job_ratio
            FROM silver_db.job_category c
            CROSS JOIN (
                SELECT COUNT(DISTINCT job_id) AS total_distinct_count 
                FROM silver_db.job_category
            ) t
            WHERE c.category_code like '2007%'  -- 只計算職業類別代碼以 '2007' 開頭的資料
            GROUP BY c.category_code, c.category_description, t.total_distinct_count
            ) AS new_data
            ON DUPLICATE KEY UPDATE
                category_name = new_data.category_name,
                job_count = new_data.job_count,
                category_job_ratio = new_data.category_job_ratio;
            """
            # 執行 SQL 指令
            print("開始清空舊資料...")
            for sql in sql_truncate:
                cursor.execute(sql)
            print("開始計算並寫入最新資料...")
            cursor.execute(sql_insert)
            print(f"fact_category_skill_weight 寫入完成！")
            cursor.execute(sql_insert_ratio)
            print(f"fact_job_ratio 寫入完成！")
            
        # 提交事務 (Transaction Commit)
        conn.commit()
        print("第二頁金表，第一階段寫入成功！")
        return True

    except Exception as e:
        # 發生例外時回滾，確保資料一致性
        if conn:
            conn.rollback()
        print(f"執行 job_weight_first_phase_insert 時發生錯誤: {e}")
        raise e

def query_category_name(conn):
    """撈出金表中尚未填入 category_desc 的原始技能資料"""
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT category_name FROM gold_db.fact_job_ratio
                WHERE category_desc IS NULL OR trim(category_desc) = '';
            """
            cursor.execute(sql)
            raw_results = cursor.fetchall()
            list = [row[0] for row in raw_results]
            return list
    except Exception as e:
        print(f"撈取未對照技能失敗: {e}")
        return []

def requir_AI_process_job_cat_des(category_names):
    """呼叫 AI 產生或匹配 std_skill_name 與分配 skill_category"""
    if not category_names:
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

    prompt = f"""
    你是一個專業的職涯顧問與求職平台內容編輯。
    我們的求職系統需要在 UI 第二頁為使用者提供「職業類別摘要說明 (category_desc)」。
    使用者不一定具備該領域的背景知識，因此敘述必須**「展現職務專業度，同時保持平易近人、簡明易懂」**，絕不可讓人覺得這份工作門檻高到無法勝任。

    【待處理職業名稱清單】：
    {json.dumps(category_names, ensure_ascii=False)}

    【撰寫規範】：
    1. **半專業口吻 (專業但不生硬)**：
    - 說明該職務的「核心價值」與「日常重要任務」。
    - **禁止使用**：抽象難懂的英文縮寫（如 KPI、OKR、SOP）或冰冷的管理術語（如 績效考核、法令維護）。
    - **禁止使用**：過度幼稚/口語的比喻（如 大腦、心臟、左右手、小幫手）。
    2. **親和力與成就感**：強調該工作「解決什麼問題」或「協助團隊達成什麼好處」，讓求職者覺得易於理解且有參與感。
    3. **精簡長度**：每篇敘述控制在 **50 ~ 80 字內**，語意完整且適合卡片閱讀。
    4. **範例對照**：
    - ❌ 太專業/壓力大：「負責制定企業中長期營運策略、KPI 績效考核及財務盈虧控制。」
    - ❌ 太白話/像小朋友：「就像公司的大腦，負責指揮大家工作，帶領公司賺大錢。」
    - ✅ 恰到好處 (專業且平易近人)：「負責規劃團隊的營運目標與執行方向，並協調各部門資源，幫助公司維持穩定運作並持續成長。」

    【輸出格式極度嚴格要求】：
    請務必僅回傳 **純 JSON Array**，絕對不要包含任何 Markdown 標記 (如 ```json)、思考過程或額外文字！
    格式如下：
    [
    {{
        "category_name": "經營管理主管",
        "category_desc": "半專業、平易近人的敘述內容..."
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

def save_category_desc_gold(processed_data,conn):
    """更新category_desc至fact_job_ratio"""
    if not processed_data:
        print(f"沒有要更新的category_desc")
        return

    try:
        with conn.cursor() as cursor:
            # 直接針對該批次的 category_desc 更新金表
            sql_gold = """
                UPDATE gold_db.fact_job_ratio
                SET category_desc = %(category_desc)s
                WHERE category_name = %(category_name)s;
            """
            cursor.executemany(sql_gold, processed_data)
        conn.commit()
        print(f"成功更新 {len(processed_data)} 筆技能資料至 MySQL 金表與對照表！")
    except Exception as e:
        print(f"資料庫更新失敗: {e}")
        conn.rollback()

@task
def run_pipeline_page2():
    #載入.env 到環境變數
    load_dotenv()
    db_name = os.getenv("MYSQL_GOLD_DATABASE")

    conn = conn_to_mysql(db_name=db_name)

    try:
        job_weight_first_phase_insert(conn)
        print("\n撈取尚未更新 category_name 的原始資料...")
        BATCH_SIZE = 10
        loop_count = 1

        # 新增 while 迴圈：只要有未說明的 category_name 資料，就持續重複執行
        while True:
            print(f"\n--- [第 {loop_count} 次檢查未處理資料] ---", flush=True)
            unmapped = query_category_name(conn)

            # 沒有空白資料即跳出迴圈
            if not unmapped:
                print("🎉 所有 category_name 均已完成 category_desc 更新！", flush=True)
                break

            print(f"共找到 {len(unmapped)} 筆 category_name 需要新增 category_desc", flush=True)

            for i in range(0, len(unmapped), BATCH_SIZE):
                batch = unmapped[i : i + BATCH_SIZE]
                print(f"\n處理解第 {i + 1} ~ {i + len(batch)} 筆 category name 中...")
                ai_results = requir_AI_process_job_cat_des(batch)

                if ai_results:
                    save_category_desc_gold(ai_results,conn)

            loop_count += 1

    finally:
        # 💡 在所有 Task 執行完成後，於主流程統一關閉連線
        if conn and conn.open:
            conn.close()
            print("\n🎉 所有 category_name 處理完成！", flush=True)

if __name__ == "__main__":
    run_pipeline_page2()