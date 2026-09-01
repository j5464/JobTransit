from airflow.sdk import task
import time
import random
import requests
import json
import os
from tasks.export_to_json import save_jobs_to_json

@task
def load_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

@task
def get_job_detail(session, job_id):
    detail_url = f"https://www.104.com.tw/api/jobs/{job_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.104.com.tw/job/{job_id}",
        "Origin": "https://www.104.com.tw",
        "Accept": "application/json, text/plain, */*",
    }
    
    try:
        response = session.get(detail_url, headers=headers, timeout=10)
        if response.status_code == 200:
            json_data = response.json()
            return json_data.get("data", {})
        else:
            print(f" -> 職缺 {job_id} 請求失敗，HTTP: {response.status_code}")
            return None
    except Exception as e:
        print(f" -> 請求職缺 {job_id} 時發生例外: {e}")

        return None

@task
def each_job_web():
    # --- 主程式執行 ---
    JOB_ID_FILE = "job_id_list.json"
    SUCCESS_DETAILS_FILE = "all_job_details.json"
    jobs_list = load_json(JOB_ID_FILE)
    collected_details = load_json(SUCCESS_DETAILS_FILE)


    # 篩選出 status 為 PENDING 的項目
    pending_jobs = [item for item in jobs_list if item.get("status") == "PENDING"]

    print(f"=== 狀態檢查 ===")
    print(f"總筆數: {len(jobs_list)} | 待處理 (PENDING): {len(pending_jobs)}")

    if not pending_jobs:
        print("所有職缺皆已處理完成！")
        exit()

    # 全域共用一個 Session，提升連線速度
    session = requests.Session()
    # 初始化先訪問一次主頁取得 Cookie 即可
    session.get("https://www.104.com.tw/jobs/main/", headers={"User-Agent": "Mozilla/5.0"})

    for i, status in enumerate(pending_jobs, 1):
        time.sleep(random.uniform(0.5, 1.5))  # 適度縮短等待時間

        job_id = status["job_id"]
        detail_data = get_job_detail(session, job_id)

        if detail_data:
            collected_details.append(detail_data)
            status["status"] = "COMPLETED"  # 更新狀態為完成
            print(f"[{i}/{len(pending_jobs)}] 成功撈取職缺: {job_id}")
        else:
            print(f"[{i}/{len(pending_jobs)}] 跳過職缺: {job_id}")

        # 每 50 筆儲存一次狀態與明細資料
        if i % 50 == 0:
            save_jobs_to_json(jobs_list, output_json_path=JOB_ID_FILE)
            save_jobs_to_json(collected_details, output_json_path=SUCCESS_DETAILS_FILE)
            print(f"=== [SavePoint] 已備份進度至第 {i} 筆 ===")

    # 最後全量存檔
    save_jobs_to_json(jobs_list, output_json_path=JOB_ID_FILE)
    save_jobs_to_json(collected_details, output_json_path=SUCCESS_DETAILS_FILE)
    print(f"\n=== 本次批次執行完成！ ===")

each_job_web()