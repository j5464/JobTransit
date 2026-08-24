import time
import random
import requests
import json
from export_to_json import save_jobs_to_json

def get_job_id():
    # 讀取 json 檔案: 104_jobs_collected.json
    with open("104_jobs_collected.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 假設 JSON 資料結構為職缺清單 (List of dicts) 或包含 jobs 欄位
    # 擷取每一個職缺的 job_id
    if isinstance(data, list):
        job_ids = [item.get("job_id") for item in data if "job_id" in item]
    elif isinstance(data, dict):
        # 若資料層級放在 jobs 或 data 鍵值下，可進行微調
        job_list = data.get("jobs", data.get("data", []))
        job_ids = [
            item.get("job_id") for item in job_list if "job_id" in item
        ]
    else:
        job_ids = []

    return job_ids

def get_job_detail(job_id):
    """
    輸入職缺代碼 (例如 '54z7k')，發送請求取得該職缺的 Preview 內頁完整 JSON 資料。
    """
    detail_url = f"https://www.104.com.tw/api/jobs/{job_id}"
    
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": f"https://www.104.com.tw/job/{job_id}",
    "Origin": "https://www.104.com.tw",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}
    
    try:
        session = requests.Session()
        session.get("https://www.104.com.tw/jobs/main/", headers=headers)
        response = session.get(detail_url, headers=headers, timeout=10)
        if response.status_code == 200:
            json_data = response.json()
            # 104 單一職缺 API 回傳格式通常為 {"data": {...}, ...}
            return json_data.get("data", {})
        else:
            print(f"-> 職缺 {job_id} 內頁請求失敗，HTTP 狀態碼: {response.status_code}")
            return None
    except Exception as e:
        print(f"-> 請求職缺 {job_id} 內頁時發生例外: {e}")
        return None
    
jobs_id = get_job_id()
collected_details = []  # 建立一個清單用來收集所有內頁資料

for job_id in jobs_id:
    time.sleep(random.uniform(1, 3))
    detail_data = get_job_detail(job_id)

    if detail_data:
        collected_details.append(detail_data)  # 將資料存入列表

print(f"{len(collected_details)}")

# 迴圈結束後，一次性調用 save_jobs_to_json 寫入 JSON 檔
save_jobs_to_json(
    collected_details, output_json_path="104_details.json"
    )

            
    
        