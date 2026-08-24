import requests

# 替換為你在 DevTools -> Headers 複製的 Request URL
url = "https://www.104.com.tw/jobs/search/api/jobs?jobcat=2007002000"

# 設定標頭以模擬真實瀏覽器行為 (請填入你電腦真實的 User-Agent 與 Referer)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.104.com.tw/jobs/search/..." # 必須帶入，通常是 104 搜尋頁面的網址
}

# 發送 GET 請求
response = requests.get(url, headers=headers)

# 確認請求是否成功 (HTTP 200)
if response.status_code == 200:
    # 直接將回應解析為 JSON 格式 (完美對應 Preview 分頁的結構)
    json_data = response.json()
    
    # 提取 data 陣列中的職缺清單
    jobs = json_data.get("data", [])

    for job in jobs:
        # 欄位名稱請對照 Preview 內的實際 key 值 (例如 jobName, custName)
        job_title = job.get('jobName')
        company = job.get('custName')
        salary = job.get('salaryDesc')
        location = job.get('jobAddrNoDesc')
        experience = job.get('periodDesc')
        education = job.get('optionEdu')
        job_url = f"https:{job['link']['job']}" if 'link' in job and 'job' in job['link'] else None
        print(f"\n[{company}] {job_title} | 薪資: {salary} | 地點: {location} | 網址: {job_url}")
        print(f"jobid:{job['link']}")

    
        
    # 提取 metadata 中的分頁資訊
    metadata = json_data.get("metadata", {})
    pagination = metadata.get("pagination", {})
    print(f"\n目前頁數: {pagination.get('currentPage')}")
    print(f"總資料筆數: {pagination.get('count')}")
    
else:
    print(f"請求失敗，HTTP 狀態碼: {response.status_code}")


    # https://www.104.com.tw/api/jobs/54z7k