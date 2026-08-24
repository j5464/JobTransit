import time
import random
import requests
from export_to_csv import save_jobs_to_csv

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

total_pages_to_scrape = 3
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
                
            # 直接將整頁的原始 JSON 物件清單全數併入
            all_jobs.extend(jobs)
            print(f"-> 第 {page} 頁撈取成功，取得 {len(jobs)} 筆資料。")
        else:
            print(f"-> 第 {page} 頁請求失敗，HTTP 狀態碼: {response.status_code}")
            break

    except Exception as e:
        print(f"-> 發生例外錯誤: {e}")
        break

# 匯出至 CSV (使用你原本寫好的 export_to_csv 模組)
if all_jobs:
    save_jobs_to_csv(all_jobs, output_csv_path="104_jobs_raw.csv")
else:
    print("\n未撈取到任何資料。")