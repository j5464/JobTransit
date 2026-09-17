import os

from dotenv import load_dotenv
from utils.conn_to_mysql import conn_to_mysql
from utils.conn_to_mongo import conn_to_mongodb



# 依序合併silver_compony.py與silver_job.py與job_category.py與job_skill.py與job_specialty與silver_job_language.py與job_requirement.py的清洗資料程式合為一檔案
# ===== 共用工具 =====
def run_mysql_upsert(sql: str, cleaned_data_list: list, batch_size: int = 200):
    #載入.env 到環境變數
    load_dotenv()
    mysql_conn = conn_to_mysql(
        # conn_ip=os.getenv("MYSQL_HOST"),
        # db_name=os.getenv("MYSQL_DATABASE"),
        # user=os.getenv("MYSQL_USER"),
        # password=os.getenv("MYSQL_ROOT_PASSWORD"),
        # port=int(os.getenv("MYSQL_PORT")),
    )
    if mysql_conn is None:
        print("無法連線到 MySQL，請檢查伺服器狀態。")
        return

    try:
        with mysql_conn.cursor() as cursor:
            # 切成每 200 筆寫入一次，避免封包過大或鎖定時間過長
            for i in range(0, len(cleaned_data_list), batch_size):
                chunk = cleaned_data_list[i : i + batch_size]
                cursor.executemany(sql, chunk)
                mysql_conn.commit()  # 分批提交
                print(f"已成功寫入 {i + len(chunk)} / {len(cleaned_data_list)} 筆資料...")
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()


def get_mongodb_collection():
    collection = conn_to_mongodb("job_details")
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return None
    return collection
