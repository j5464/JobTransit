from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from pymysql import connect
from datetime import datetime, time, timedelta

def conn_to_mongodb(conn_ip:str,db_name: str,collection_name: str):
    """
    皆要使用"雙引號"或'單引號'包住字串，參數說明:\n
    *conn_ip*:要連線的ip\n
    *db_name*: 資料庫名稱\n
    *collection_name*: 集合表名稱\n
    """
    connection = f"mongodb://{conn_ip}:27017/"
    try:

        #使用URI連結
        client = MongoClient(connection)
        client.admin.command('ping')

        #使用(創建)資料庫
        db = client[db_name]

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

# 將語言需求資料寫入 MySQL 的 job_language 表格中 (Upsert)
def import_language_to_mysql(cleaned_data_list):
    mysql_conn = conn_to_mysql(
        conn_ip="10.2.19.84",
        db_name="TESTDB",
        user="maggie",
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
                INSERT INTO job_language (
                    job_id, language_code, language_name,
                    listening_level, speaking_level, reading_level, writing_level
                ) VALUES (
                    %(job_id)s, %(language_code)s, %(language_name)s,
                    %(listening_level)s, %(speaking_level)s, %(reading_level)s, %(writing_level)s
                )
                AS new
                ON DUPLICATE KEY UPDATE
                    language_name = new.language_name,
                    listening_level = new.listening_level,
                    speaking_level = new.speaking_level,
                    reading_level = new.reading_level,
                    writing_level = new.writing_level;
            """
            # 執行批次寫入
            cursor.executemany(sql, cleaned_data_list)

        # 提交事務
        mysql_conn.commit()
        print(
            f"成功將 {len(cleaned_data_list)} 筆資料寫入至 MySQL 的 job_language 表格！"
        )
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()

def sliver_job_language():
    collection = conn_to_mongodb("localhost", "tkr102", "job_details")
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    print("開始處理 sliver_job_language")
    # 計算「昨天 23:55 ~ 明天 00:00」時間區間
    today = datetime.now().date()
    start_time = datetime.combine(today - timedelta(days=1), time(23, 55, 0))
    end_time = datetime.combine(today + timedelta(days=1), time(0, 0, 0))

    pipeline = [
        # 1. 條件篩選：switch: on 且 ingestion_timestamp 在指定時間區間內
        {
            "$match": {
                "switch": "on",
                "ingestion_timestamp": {"$gte": start_time, "$lt": end_time},
            }
        },
        # 2. 依照 ingestion_timestamp 由新到舊排序
        {"$sort": {"ingestion_timestamp": -1}},
        # 3. 展平陣列
        {"$unwind": "$condition.language"},
        {"$unwind": "$header"},
        # 4. 解析 job_id 與語言相關欄位
        {
            "$project": {
                "job_id": {
                    "$let": {
                        "vars": {
                            "urlParts": {
                                "$split": ["$header.analysisUrl", "/"]
                            }
                        },
                        "in": {"$arrayElemAt": ["$$urlParts", -1]},
                    }
                },
                "language_code": "$condition.language.code",
                "language_name": "$condition.language.language",
                "listening_level": "$condition.language.ability.listening",
                "speaking_level": "$condition.language.ability.speaking",
                "reading_level": "$condition.language.ability.reading",
                "writing_level": "$condition.language.ability.writing",
            }
        },
        # 5. 以 job_id & language_code 去重，取最前面 (最新) 的資料欄位
        {
            "$group": {
                "_id": {
                    "job_id": "$job_id",
                    "language_code": "$language_code",
                },
                "language_name": {"$first": "$language_name"},
                "listening_level": {"$first": "$listening_level"},
                "speaking_level": {"$first": "$speaking_level"},
                "reading_level": {"$first": "$reading_level"},
                "writing_level": {"$first": "$writing_level"},
            }
        },
        # 6. 還原平坦化結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id.job_id",
                "language_code": "$_id.language_code",
                "language_name": "$language_name",
                "listening_level": "$listening_level",
                "speaking_level": "$speaking_level",
                "reading_level": "$reading_level",
                "writing_level": "$writing_level",
            }
        },
    ]

    list_data = collection.aggregate(pipeline)

    # 整理乾淨資料準備寫入 MySQL
    cleaned_data_list_language = []
    for doc in list_data:
        cleaned_item = {
            "job_id": doc.get("job_id"),
            "language_code": doc.get("language_code"),
            "language_name": doc.get("language_name"),
            "listening_level": doc.get("listening_level"),
            "speaking_level": doc.get("speaking_level"),
            "reading_level": doc.get("reading_level"),
            "writing_level": doc.get("writing_level"),
        }
        cleaned_data_list_language.append(cleaned_item)

    # 連線到 MySQL 並將清理後的資料寫入表格
    if cleaned_data_list_language:
        import_language_to_mysql(cleaned_data_list_language)
    else:
        print("指定時間區間內無符合條件的資料。")

# 執行
sliver_job_language()