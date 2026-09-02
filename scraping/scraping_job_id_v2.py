import time
import random
import requests
from export_to_json import save_jobs_to_json
from urllib.parse import urlparse
import os
import json
from json_to_mongo import get_existing_job_ids,insert_new_job_ids

def get_job_id():
    base_url = "https://www.104.com.tw/jobs/search/api/jobs"
    # Referer https://www.104.com.tw/jobs/search/?jobcat=2007002000&jobsource=index_s&mode=s&page=1
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.104.com.tw/jobs/search/"
    }
    # 建立 jobcat list
    jobcats = [
    '2007001013', '2007001014', '2007001015', '2007001016', '2007001017',
    # '2007001018', '2007001004', '2007001019', '2007001001', '2007001007',
    # '2007001021', '2007001022', '2007001020', '2007001012', '2007001005',
    # '2007001008', '2007001006', '2007001010', '2007001023', '2007001011',
    # '2007001003', '2007001002', '2007001024', '2007001009', '2007001025',
    # '2007001026', '2007002006', '2007002005', '2007002009', '2007002007',
    # '2007002010', '2007002008', '2007002004', '2007002003', '2007002002',
    # '2007002001', '2007002011'
    ]

    # --- 讀取 Mongo DB ---
    jobs_dict = get_existing_job_ids()
    # --------------

    # jobcat list 迴圈 params 的 jobcat
    for jobcat in jobcats:
        print(f"=== 開始爬取 104 cat:{jobcat} 職缺原始資料 ===")
        page = 1  # 2. 每個類別開始前初始化 page
        while True:

            # --- 修改點 1: 判斷頁數是否超過 150 頁，超過直接跳出當前類別 --- 2026/09/02
            if page > 150:
                print(f"已達到最高 150 頁限制，自動結束 cat:{jobcat} 的撈取。")
                break

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
                    page_new_jobs = []  # 存當前頁面新發現的職缺
                    for job in jobs:
                        raw_url = job.get("link", {}).get("job", "")
                        if raw_url:
                            path = urlparse(raw_url).path.strip().rstrip("/")
                            job_id = path.split("/")[-1]
                            # 若 ID 不存在才新增，維持預設 PENDING 狀態
                            if job_id and job_id not in jobs_dict:
                                item = {
                                    "job_id": job_id,
                                    "status": "PENDING"
                                }
                                jobs_dict[job_id] = item
                                page_new_jobs.append(item)  # 加入當頁新資料
                                new_added_count += 1

                    # 每頁成功時即時更新 Mongo DB，防止突發斷電中斷
                    #---------
                    insert_new_job_ids(page_new_jobs)
                    #---------

                    print(f"-> 第 {page} 頁撈取成功，新增 {new_added_count} 筆不重複 ID (總計: {len(jobs_dict)} 筆)。")
                    page += 1

                    
                else:
                    print(f"-> 第 {page} 頁請求失敗，HTTP 狀態碼: {response.status_code}")
                    break

            except Exception as e:
                print(f"-> 發生例外錯誤: {e}")
                break

    print(f"\n目前共有 {len(jobs_dict)} 筆 Job ID 儲存")

get_job_id()

