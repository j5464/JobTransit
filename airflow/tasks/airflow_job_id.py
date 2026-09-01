from airflow.sdk import task
import time
import random
import requests
from tasks.export_to_json import save_jobs_to_json
from urllib.parse import urlparse
import os
import json

@task
def get_job_id():
    base_url = "https://www.104.com.tw/jobs/search/api/jobs"
    # Referer https://www.104.com.tw/jobs/search/?jobcat=2007002000&jobsource=index_s&mode=s&page=1
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.104.com.tw/jobs/search/"
    }
    # 建立 jobcat list
    jobcats = ['2007001013','2007001014']
    output_file = "job_id_list.json"
    # 用set存取 job_id，避免重複添加
    jobs_dict = {}  # key: job_id, value: item_dict
    # --- 斷點續傳核心：讀取舊有已爬取的 ID ---
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                for item in existing_data:
                    jobs_dict[item["job_id"]] = item
                    print(f"[續傳機制] 成功載入歷史紀錄，已有 {len(jobs_dict)} 筆 Job ID。")
        except Exception as e:
            print(f"[警告] 讀取歷史檔案失敗 ({e})，將從頭開始。")

    # jobcat list 迴圈 params 的 jobcat
    for jobcat in jobcats:
        print(f"=== 開始爬取 104 cat:{jobcat} 職缺原始資料 ===")
        page = 1  # 2. 每個類別開始前初始化 page
        while True:
            params = {
                "jobcat": jobcat,
                "jobsource": "index104",
                "page": page
            }

            print(f"正在撈取第 {page} 頁資料...")
            if page > 1:
                sleep_time = random.uniform(3, 5)
                print(f"\n等待 {sleep_time:.2f} 秒後繼續撈取第 {page} 頁...")
                time.sleep(sleep_time)

            try:
                response = requests.get(base_url, headers=headers, params=params, timeout=10)
                
                if response.status_code == 200:
                    json_data = response.json()
                    jobs = json_data.get("data", [])
                    
                    if not jobs:
                        print("已無更多職缺資料，結束撈取。")
                        break

                    new_added_count = 0    
                    for job in jobs:
                        raw_url = job.get("link", {}).get("job", "")
                        if raw_url:
                            path = urlparse(raw_url).path.strip().rstrip("/")
                            job_id = path.split("/")[-1]
                            # 若 ID 不存在才新增，維持預設 PENDING 狀態
                            if job_id and job_id not in jobs_dict:
                                jobs_dict[job_id] = {
                                    "job_id": job_id,
                                    "status": "PENDING"
                                }
                                new_added_count += 1

                    print(f"-> 第 {page} 頁撈取成功，新增 {new_added_count} 筆不重複 ID (總計: {len(jobs_dict)} 筆)。")
                    page += 1

                    # 每頁成功時即時更新 JSON 檔案，防止突發斷電中斷
                    save_jobs_to_json(list(jobs_dict.values()), output_json_path=output_file)
                else:
                    print(f"-> 第 {page} 頁請求失敗，HTTP 狀態碼: {response.status_code}")
                    break

            except Exception as e:
                print(f"-> 發生例外錯誤: {e}")
                break

    print(f"\n目前共有 {len(jobs_dict)} 筆 Job ID 儲存於 {output_file}")

def do_something(some_str: str) -> list[str]:
    return list(some_str)
