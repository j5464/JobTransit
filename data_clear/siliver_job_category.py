import os

from pendulum import today
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from urllib.parse import urlparse
from datetime import datetime, timedelta, time
from pymysql import connect

#建立與 MongoDB 的連線，並回傳指定的 Collection
def conn_to_mongodb(collection_name: str):
    #抓取環境變數
    connection =  os.getenv("MONGODB_URI")
    try:

        #使用URI連結
        client = MongoClient(connection)
        client.admin.command('ping')
        print("成功連線到 MongoDB!")

        #使用(創建)資料庫
        db = client['tkr102']

        #使用(創建)文檔集
        collection = db[collection_name]

        return collection

    except ConnectionFailure as e:
        print(f"連線失敗，請確認 MongoDB 伺服器是否有啟動。錯誤訊息: {e}")
        return None

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

# 將 job 寫入 MySQL 的 job_category 表格中
def import_category_to_mysql(cleaned_data_list):
    mysql_conn = conn_to_mysql(
        conn_ip="10.2.19.84",
        db_name="TESTDB",
        user="root",
        password="password",
        port=3307,
    )
    if mysql_conn is None:
        print("無法連線到 MySQL，請檢查伺服器狀態。")
        return

    try:
        with mysql_conn.cursor() as cursor:
            # 採用 MySQL 原生 ON DUPLICATE KEY UPDATE 語法
            sql = """
                INSERT INTO job_category (
                    job_id, category_code, category_description, seq_no
                ) VALUES (
                    %(job_id)s, %(category_code)s, %(category_description)s, %(seq_no)s
                )
                AS new
                ON DUPLICATE KEY UPDATE
                    category_description = new.category_description;
            """
            cursor.executemany(sql, cleaned_data_list)

        mysql_conn.commit()
        print(
            f"成功將 {len(cleaned_data_list)} 筆資料處理並寫入至 MySQL 的 job_category 表格！"
        )
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()

def silver_category_mongodb_to_mysql():
    collection = conn_to_mongodb("job_details")
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    print("開始處理 silver_company")
    today = datetime.combine(datetime.now().date(), time.min)

    # 1. 昨天 (今天 - 1 天) 的 23:55
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)

    # 2. 明天 (今天 + 1 天) 的 00:00
    end_time = today + timedelta(days=1)

    pipeline = [
        {"$match": {"switch": "on"}},
        {
            "$match": {
                "ingestion_timestamp": {
                    "$gte": start_time,  # 昨天 23:55:00
                    "$lt": end_time,  # 明天 00:00:00
                }
            }
        },
        # 1. 針對篩選後的資料進行排序（由新到舊 -1，取最新快照）
        {"$sort": {"ingestion_timestamp": -1}},
        # 2. 解析 job_id 並保留原始的 jobCategory 陣列作為 index 對照
        {
            "$addFields": {
                "parsed_job_id": {
                    "$arrayElemAt": [
                        {
                            "$split": [
                                {
                                    "$trim": {
                                        "input": "$header.analysisUrl",
                                        "chars": "/",
                                    }
                                },
                                "/",
                            ]
                        },
                        -1,
                    ]
                },
                "raw_job_category": "$jobDetail.jobCategory",
            }
        },
        # 3. 展開 jobDetail.jobCategory 陣列
        {"$unwind": "$jobDetail.jobCategory"},
        # 4. 計算 seq_no (陣列 index, 0 為主分類) 與整理結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$parsed_job_id",
                "category_code": "$jobDetail.jobCategory.code",
                "category_description": "$jobDetail.jobCategory.description",
                "seq_no": {
                    "$indexOfArray": [
                        "$raw_job_category",
                        "$jobDetail.jobCategory",
                    ]
                },
            }
        },
        # 5. 利用 $group 去重
        {
            "$group": {
                "_id": {
                    "job_id": "$job_id",
                    "category_code": "$category_code",
                    "category_description": "$category_description",
                    "seq_no": "$seq_no",
                }
            }
        },
        # 6. 還原平坦化結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id.job_id",
                "category_code": "$_id.category_code",
                "category_description": "$_id.category_description",
                "seq_no": "$_id.seq_no",
            }
        },
    ]

    cursor_list = collection.aggregate(pipeline)

    # 封裝為符合 Schema 的格式
    cleaned_data_list = []
    for doc in cursor_list:
        cleaned_item = {
            "job_id": doc.get("job_id"),
            "category_code": doc.get("category_code"),
            "category_description": doc.get("category_description"),
            "seq_no": doc.get("seq_no"),
        }
        cleaned_data_list.append(cleaned_item)

    # 執行 MySQL Upsert 寫入
    if cleaned_data_list:
        import_category_to_mysql(cleaned_data_list)
    else:
        print("未產出任何清洗資料。")

# 執行流程
silver_category_mongodb_to_mysql()