from datetime import datetime, timedelta
import time
import random
import requests
import os
from dotenv import load_dotenv
from airflow.sdk import dag, task
from tasks.check_url_status import get_job_detail,query_job_batch,update_job_status_batch
from utils.conn_to_mysql import conn_to_mysql

# Default arguments for the DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email": ["xxxxxxx@gmail.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

@dag(
    dag_id="d_check_url_status",
    default_args=default_args,
    description="An example DAG with Python operators",
    schedule="* 10 10 12 *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    tags=["example", "decorator"]  # Optional: Add tags for better filtering in the UI
)

@task
def url_check():

    # 1. 初始化 Session
    session = requests.Session()

    try:
        session.get(
            "https://www.104.com.tw/jobs/main/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            timeout=10,
        )
    except Exception as e:
        print(f"初始化訪問 104 主頁失敗: {e}")

    # 載入 .env 檔案中的變數
    load_dotenv()
    
    # 2. 建立單一 MySQL 連線供全程使用
    mysql_conn = conn_to_mysql(
        conn_ip = os.getenv("MYSQL_HOST"),
        db_name = os.getenv("MYSQL_DATABASE"),
        user = os.getenv("MYSQL_ROOT_USER"),
        password = os.getenv("MYSQL_ROOT_PASSWORD"),
        port = os.getenv("MYSQL_PORT"),
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

# 主執行
url_check()
