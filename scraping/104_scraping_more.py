import time
import random
import requests
from export_to_json import save_jobs_to_json
from urllib.parse import urlparse

base_url = "https://www.104.com.tw/jobs/search/api/jobs"
# Referer https://www.104.com.tw/jobs/search/?jobcat=2007002000&jobsource=index_s&mode=s&page=1
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.104.com.tw/jobs/search/"
}

params = {
    "jobcat": "2007002000",
    "jobsource": "index104",
    "page": 1
}

total_pages_to_scrape = 1
all_jobs = []

print("=== 開始爬取 104 職缺原始資料 ===")

for page in range(1, total_pages_to_scrape + 1):
    if page > 1:
        sleep_time = random.uniform(3, 5)
        print(f"\n等待 {sleep_time:.2f} 秒後繼續撈取第 {page} 頁...")
        time.sleep(sleep_time)

    params["page"] = page
    print(f"正在撈取第 {page} 頁資料...")

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            json_data = response.json()
            jobs = json_data.get("data", [])
            
            if not jobs:
                print("已無更多職缺資料，結束撈取。")
                break
                
            for job in jobs:
                # 1. 安全取得 job link
                link_info = job.get("link") or {}
                raw_url = link_info.get("job", "")
                
                job_id = ""
                if raw_url:
                    # 2. 解析網址路徑，去除 query 參數與前後空白
                    path = urlparse(raw_url).path.strip()
                    
                    # 3. 移除結尾的斜線 (例如 /job/8w99k/ -> /job/8w99k)
                    path = path.rstrip("/")
                    
                    # 4. 取得路徑最後一部分
                    if path:
                        job_id = path.split("/")[-1]
                        
                # 5. 寫入字典
                job["job_id"] = job_id
                all_jobs.append(job)

            print(f"-> 第 {page} 頁撈取成功，取得 {len(jobs)} 筆資料。")
        else:
            print(f"-> 第 {page} 頁請求失敗，HTTP 狀態碼: {response.status_code}")
            break

    except Exception as e:
        print(f"-> 發生例外錯誤: {e}")
        break

# 匯出至 json (使用你原本寫好的 export_to_json 模組)
if all_jobs:
    save_jobs_to_json(all_jobs, output_json_path="104_jobs_collected.json")
else:
    print("\n未撈取到任何資料。")