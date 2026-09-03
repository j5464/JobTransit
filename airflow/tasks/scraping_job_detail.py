from airflow.sdk import task
import time
import random
import requests
from tasks.json_to_mongo import get_pending_jobs,update_job_status_to_complete,insert_job_detail

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

    # 篩選出 status 為 PENDING 的項目
    pending_jobs = get_pending_jobs()

    print(f"=== 狀態檢查 ===")
    print(f"待處理 (PENDING): {len(pending_jobs)}")

    if not pending_jobs:
        print("所有職缺皆已處理完成！")
        exit()

    # 全域共用一個 Session，提升連線速度
    session = requests.Session()
    # 初始化先訪問一次主頁取得 Cookie 即可
    session.get("https://www.104.com.tw/jobs/main/", headers={"User-Agent": "Mozilla/5.0"})

    # with 連線 as 
    for i, status in enumerate(pending_jobs, 1):
        time.sleep(random.uniform(0.5, 1.5))  # 適度縮短等待時間

        job_id = status["job_id"]
        detail_data = get_job_detail(session, job_id)

        if detail_data:
            insert_job_detail(detail_data)
            # status["status"] = "COMPLETED"  # 更新狀態為完成
            update_job_status_to_complete(job_id)
            print(f"[{i}/{len(pending_jobs)}] 成功存取職缺: {job_id}")
        else:
            print(f"[{i}/{len(pending_jobs)}] 跳過職缺: {job_id}")

    print(f"\n=== 本次批次執行完成！ ===")

each_job_web()