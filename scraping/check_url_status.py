import time
import random
import requests
from pymysql import connect
import os
from dotenv import load_dotenv

def conn_to_mysql(conn_ip:str,db_name: str,user:str,password:str,port:int = 3306):
    """
    皆要使用"雙引號"或'單引號'包住字串，參數說明:\n
    *conn_ip*:要連線的ip\n
    *db_name*: 資料庫名稱\n
    *user*: 使用者名稱\n
    *password*: 使用者密碼\n
    """
    try:
        connection = connect(
            host=conn_ip,
            port=port,
            user=user,
            password=password,
            database=db_name
        )
        return connection
    except Exception as e:
        print(f"連線失敗，請確認 MySQL 伺服器是否有啟動。錯誤訊息: {e}")
        return None

def get_job_detail(session, job_id, max_retries=3):
    """
    取得單一職缺詳細資訊：
    - HTTP 200: 回傳 JSON 資料
    - HTTP 404: 表示職缺已被刪除/不存在，回傳 {"status": "404_not_found"}
    - HTTP 429: 觸發防爬限制，採用指數退避 (10分 -> 20分 -> 40分) 自動重試
    - 其他狀態: 回傳 None
    """
    detail_url = f"https://www.104.com.tw/api/jobs/{job_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.104.com.tw/job/{job_id}",
        "Origin": "https://www.104.com.tw",
        "Accept": "application/json, text/plain, */*",
    }

    retry_delay = 300  # 初始等待 10 分鐘 (600 秒)

    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(detail_url, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()

            elif response.status_code == 404:
                print(f" -> 職缺 {job_id} 找不到頁面 (HTTP 404)，判定為已下架")
                return {"status": "404_not_found"}

            elif response.status_code == 429:
                print(
                    f"\n [警告] 觸發 HTTP 429 (Too Many Requests)！"
                    f"第 {attempt}/{max_retries} 次重試，將暫停 {retry_delay // 60} 分鐘..."
                )
                time.sleep(retry_delay)
                retry_delay += 300  # 下一次觸發時等待時間翻倍
                continue

            else:
                print(
                    f" -> 職缺 {job_id} 請求失敗，HTTP 狀態碼: {response.status_code}"
                )
                return None

        except Exception as e:
            print(f" -> 請求職缺 {job_id} 時發生例外狀況: {e}")
            return None

    print(
        f" -> 職缺 {job_id} 重試 {max_retries} 次均觸發 429，放棄本筆請求"
    )
    return None

def query_job_batch(cursor):
    """傳入現有的 cursor 執行查詢作業"""
    sql = """
        SELECT job_id 
        FROM TESTDB.job 
        WHERE url_status = 'on' 
          AND updated_at <= NOW() - INTERVAL 3 DAY
    """
    cursor.execute(sql)
    results = cursor.fetchall()

    if results and isinstance(results[0], dict):
        job_ids = [row["job_id"] for row in results]
    else:
        job_ids = [row[0] for row in results]

    print(f"成功查詢到 {len(job_ids)} 筆需檢查的職缺資料")
    return job_ids

def update_job_status_batch(cursor, job_id, url_status):
    """傳入現有的 cursor 進行狀態更新"""
    try:
        sql = """
            UPDATE TESTDB.job 
            SET url_status = %s, updated_at = NOW() 
            WHERE job_id = %s
        """
        cursor.execute(sql, (url_status, job_id))
    except Exception as e:
        print(f" [DB] 更新 job_id: {job_id} 時發生錯誤: {e}")

def each_job_web():
    # 1. 初始化 Session
    session = requests.Session()

    try:
        session.get(
            "https://www.104.com.tw/jobs/main/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
    except Exception as e:
        print(f"初始化訪問 104 主頁失敗: {e}")

    # 2. 建立單一 MySQL 連線供全程使用
    mysql_conn = conn_to_mysql(
        conn_ip = "10.2.19.84",
        db_name = os.getenv("MYSQL_DATABASE"),
        user = "maggie",
        password = os.getenv("MYSQL_ROOT_PASSWORD"),
        port = 3307,
    )

    if mysql_conn is None:
        print("無法連線到 MySQL，取消執行。")
        return

    updated_count = 0

    try:
        with mysql_conn.cursor() as cursor:
            # 3. 共用連線：進行 Job 查詢
            jobs = query_job_batch(cursor)

            if not jobs:
                print("沒有需要更新狀態的職缺。")
                return

            print(f"開始檢查 {len(jobs)} 筆職缺狀態...")

            # 4. 逐一爬取與判定狀態
            for record_idx, job_id in enumerate(jobs, 1):
            # for job_id in jobs:
                raw_json = get_job_detail(session, job_id)

                if raw_json:
                    # 情境 A: 收到 404 狀態，直接標記為 off
                    if raw_json.get("status") == "404_not_found":
                        update_job_status_batch(cursor, job_id, "off")
                        updated_count += 1

                    # 情境 B: 成功取得 JSON 資料，檢查 switch 欄位
                    else:
                        data = raw_json.get("data", {})
                        switch_status = data.get("switch")

                        if switch_status == "off":
                            update_job_status_batch(cursor, job_id, "off")
                            mysql_conn.commit()
                            print(
                                f" -> [{record_idx}/{len(jobs)}]職缺 {job_id} switch 為 off，已更新"
                            ) 
                            updated_count += 1
                        else:
                            update_job_status_batch(cursor, job_id, "on")
                            print(
                                f" -> [{record_idx}/{len(jobs)}]職缺 {job_id} (switch: {switch_status})"
                            )
                else:
                    print(
                        f" -> 無法取得職缺 {job_id} 詳細內容（可能為網路問題或重試上限）"
                    )

                # 隨機間隔 1.5 ~ 3.0 秒，降低被判定為爬蟲的風險
                time.sleep(random.uniform(1.5, 3.0))
        
        mysql_conn.commit()
        print(f"\n[DB] 總計將 {updated_count} 筆更新成 off！")

    except Exception as e:
        print(f"\n[DB] 執行過程發生異常，進行 rollback: {e}")
        mysql_conn.rollback()
    finally:
        # 6. 安全關閉連線
        mysql_conn.close()
        print("MySQL 連線已關閉。")

    print(f"\n=== 本次批次執行完成！ ===")

each_job_web()