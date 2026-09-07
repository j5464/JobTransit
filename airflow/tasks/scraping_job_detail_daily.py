from airflow.sdk import task
from datetime import datetime, timezone
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
            # --- 修改點：為確保 source_response_timestamp 的正確 API 時間
            # json_data = response.json()
            # return json_data.get("data", {})
            return response.json()
            
        else:
            print(f" -> 職缺 {job_id} 請求失敗，HTTP: {response.status_code}")
            return None
    except Exception as e:
        print(f" -> 請求職缺 {job_id} 時發生例外: {e}")

        return None

@task
def each_job_web():
    # 全域共用一個 Session，提升連線速度
     session = requests.Session()
     # 初始化先訪問一次主頁取得 Cookie 即可
     session.get("https://www.104.com.tw/jobs/main/", headers={"User-Agent": "Mozilla/5.0"})
     max_batches = 3
 
     for batch_count in range(1, max_batches + 1):
         # 篩選出 status 為 PENDING 的項目
         pending_jobs = get_pending_jobs()
 
         print(f"=== 狀態檢查 ===")
         print(f"\n=== 第 {batch_count}/{max_batches} 輪狀態檢查 ===")
         print(f"待處理 (PENDING): {len(pending_jobs)}")
         # --- 新增點：產生 Batch ID（整個任務共用一個）
         batch_id = datetime.now().strftime(f"%Y%m%d_{batch_count:03d}")
         # --- 
 
         if not pending_jobs:
             print("所有職缺皆已處理完成！")
             exit()
 
         # with 連線 as 
         for record_idx, status in enumerate(pending_jobs, 1):
             time.sleep(random.uniform(0.5, 1.5))  # 適度縮短等待時間
 
             job_id = status["job_id"]
             # --- 修改點: 為確保 source_response_timestamp 的正確 API 時間
             # detail_data = get_job_detail(session, job_id)
             raw_json = get_job_detail(session, job_id)
             # --- 新增點：
             if raw_json:
                 # 取得資料核心內容 (data)
                 detail_data = raw_json.get("data", {})
                 # --- 3. 全部在主程式組裝附加欄位 ---
                 # (1) batch_id
                 detail_data["batch_id"] = batch_id
 
                 # (2) ingestion_timestamp (資料寫入 Bronze / MongoDB 的時間)
                 detail_data["ingestion_timestamp"] = datetime.now()
 
                 # (3) record_index_in_batch (陣列索引，從 0 開始)
                 detail_data["record_index_in_batch"] = record_idx
 
                 # (4) source_response_timestamp (轉型自原始 JSON 裡的 interactionRecord.now)
                 epoch_sec = raw_json.get("interactionRecord", {}).get("nowTimestamp")
                 if epoch_sec:
                     detail_data["source_response_timestamp"] = datetime.fromtimestamp(
                         epoch_sec,
                         tz = timezone.utc,
                         )
                 else:
                     detail_data["source_response_timestamp"] = datetime.now()
             # --- 
 
             # --- 修改點：
             # if detail_data:
             # ---
                 insert_job_detail(detail_data)
                 update_job_status_to_complete(job_id)
                 print(f"[{record_idx+1}/{len(pending_jobs)}] 成功存取職缺: {job_id}")
             else:
                 print(f"[{record_idx+1}/{len(pending_jobs)}] 跳過職缺: {job_id}")
 
         print(f"\n=== 本次批次執行完成！ ===")
