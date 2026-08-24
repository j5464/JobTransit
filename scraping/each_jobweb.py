import time
import random
import requests
import json
from export_to_json import save_jobs_to_json

def get_job_id(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, str)]
        return []
    except FileNotFoundError:
        print(f"錯誤：找不到檔案 {file_name}")
        return []

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

# --- 主程式執行 ---
jobs_id = get_job_id("job_id_list.json")
print(f"成功讀取 {len(jobs_id)} 筆 Job ID，準備開始撈取內頁...")

collected_details = []
error_job_list=[]

# 全域共用一個 Session，提升連線速度
session = requests.Session()
# 初始化先訪問一次主頁取得 Cookie 即可
session.get("https://www.104.com.tw/jobs/main/", headers={"User-Agent": "Mozilla/5.0"})

for i, job_id in enumerate(jobs_id, 1):
    time.sleep(random.uniform(0.5, 1.5))  # 適度縮短等待時間
    
    detail_data = get_job_detail(session, job_id)

    if detail_data:
        collected_details.append(detail_data)
        print(f"[{i}/{len(jobs_id)}] 成功撈取職缺: {job_id}")
    else:
        print(f"[{i}/{len(jobs_id)}] 跳過職缺: {job_id}")
        error_job_list.append(job_id)


    # 每 500 筆分批存檔，並清空暫存清單
    if i % 500 == 0:
        save_jobs_to_json(
            collected_details, 
            output_json_path=f"details_part_{i}.json"
        )
        print(f"=== 已成功備份第 {i} 筆前的 500 筆資料 ===")
        collected_details.clear() # 清空列表，避免重複寫入與佔用記憶體

# 處理剩餘未滿 500 筆的尾數資料
if collected_details:
    save_jobs_to_json(collected_details, output_json_path="details_final.json")
    print(f"=== 全部撈取完成，最後 {len(collected_details)} 筆已匯出 ===")
if error_job_list:
    save_jobs_to_json(error_job_list, output_json_path="error_job_list.json")
    print(f"最後有 {len(error_job_list)} 筆 未撈取成功 已匯出 error_job_list.json ===")