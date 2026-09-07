import time
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def main():
    options = webdriver.ChromeOptions()
    
    # 防擋機制與視窗設定
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--start-maximized")


    driver = webdriver.Chrome(options=options)
    url = "https://www.104.com.tw/jobs/search/?jobcat=2007002000&jobsource=index_s&mode=s&page=1"
    # url = "https://www.104.com.tw/jobs/search/?jobcat=2007002000&page=1"
    
    try:
        driver.get(url)
        print("正在開啟 104 網頁...")

        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # 分次向下滾動，觸發 104 動態列表渲染
        print("模擬向下滾動載入資料...")
        for i in range(1, 4):
            driver.execute_script(f"window.scrollTo(0, {i * 600});")
            sleep_time = random.uniform(3.0, 5.0)
            time.sleep(sleep_time)

        # 取得網頁原始碼
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # 104 職缺標題精準定位（優選 data-qa-id 屬性，次選 info-job__text 類別）
        job_titles = soup.select('a[data-qa-id="jobCardTitle"]') or soup.select('a.info-job__text')

        if not job_titles:
            # 備用方案：抓取所有文字長度大於 2 且包含 /job/ 的標題連結
            job_titles = [a for a in soup.select('a[href*="/job/"]') if len(a.get_text(strip=True)) > 2]

        print(f"\n成功解析出 {len(job_titles)} 個職缺：\n")
        print({job_titles})
        seen = set()

        # for a_tag in job_titles:
        #     title = a_tag.get_text(strip=True)
        #     href = a_tag.get("href", "")

        #     # 過濾無效與重複項目
        #     if title and title not in seen and "jobcat" not in href:
        #         seen.add(title)
                
        #         # 補齊完整網址
        #         link = f"https:{href}" if href.startswith("//") else href
        #         if not link.startswith("http"):
        #             link = f"https://www.104.com.tw{link}"
     #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


                # print(f"職缺名稱: {title}")
                # print(f"連結: {link}")
                # print("-" * 50)


    except Exception as e:
        print(f"自動化操作或解析發生錯誤: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    print("=" * 30)
    main()
    print("=" * 30)