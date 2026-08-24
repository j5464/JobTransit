import time
import random
import requests
import json
from export_to_json import save_jobs_to_json

def get_job_id(file_name):
    # 讀取 json 檔案
    with open(file_name, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 確保資料格式為 list，且只取出字串類型的 job_id
    if isinstance(data, list):
        job_ids = [item for item in data if isinstance(item, str)]
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
    
jobs_id = get_job_id("job_id_list.json")
collected_details = []  # 建立一個清單用來收集所有內頁資料

for i, job_id in enumerate(jobs_id, 1):
    time.sleep(random.uniform(1, 3))
    detail_data = get_job_detail(job_id)

    if detail_data:
        collected_details.append(detail_data)

    # 每 500 筆存檔一次，並清空記憶體
    if i % 500 == 0:
        save_jobs_to_json(
            collected_details, 
            output_json_path=f"details_part_{i}.json" # 或寫入 SQLite
        )
        print(f"--- 已成功存檔第 {i} 筆資料 ---")

# 處理剩餘未滿 500 筆的資料
if collected_details:
    save_jobs_to_json(collected_details, output_json_path="details_final.json")


            
    
        