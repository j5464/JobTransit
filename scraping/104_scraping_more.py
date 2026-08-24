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
# 建立 jobcat list
jobcats = ['2007001013','2007001014']
# 用set存取 job_id，避免重複添加
job_ids = set()

# jobcat list 迴圈 params 的 jobcat
for jobcat in jobcats:
    print(f"=== 開始爬取 104 cat:{jobcat} 職缺原始資料 ===")
    page = 1  # 2. 每個類別開始前初始化 page
    while True:
        params = {
            "jobcat": {jobcat},
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
                    
                for job in jobs:
                    raw_url = job.get("link", {}).get("job", "")
                    if raw_url:
                        path = urlparse(raw_url).path.strip().rstrip("/")
                        job_id = path.split("/")[-1]
                        if job_id and job_id not in job_ids:
                            job_ids.add(job_id)

                print(f"-> 第 {page} 頁撈取成功，取得 {len(jobs)} 筆資料。")
                page += 1
            else:
                print(f"-> 第 {page} 頁請求失敗，HTTP 狀態碼: {response.status_code}")
                break

        except Exception as e:
            print(f"-> 發生例外錯誤: {e}")
            break

# 匯出至 json (使用你原本寫好的 export_to_json 模組)
if job_ids:
    save_jobs_to_json(list(job_ids), output_json_path="job_id_list.json")
    print(f"\n成功匯出 {len(job_ids)} 筆不重複的 job_id 至 job_id_list.json")
else:
    print("\n未撈取到任何資料。")