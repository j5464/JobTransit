from pendulum import today
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from urllib.parse import urlparse
from datetime import datetime, timedelta, time
from pymysql import connect

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

# 將 company 寫入 MySQL 的 company 表格中 (PK 改為僅 cust_no)
def import_company_to_mysql(cleaned_data_list):
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
            # 1. 套用方案 A 的 Upsert SQL 語句 (PK 為 cust_no)
            sql = """
                INSERT INTO company (
                    cust_no, cust_name, cust_url, industry_name, industry_no,
                    employees_count, employees_raw, _silver_updated_at, _source_batch_id
                ) VALUES (
                    %(cust_no)s, %(cust_name)s, %(cust_url)s, %(industry_name)s, %(industry_no)s,
                    %(employees_count)s, %(employees_raw)s, %(_silver_updated_at)s, %(_source_batch_id)s
                )
                AS new
                ON DUPLICATE KEY UPDATE
                    cust_name = new.cust_name,
                    cust_url = new.cust_url,
                    industry_name = new.industry_name,
                    industry_no = new.industry_no,
                    employees_count = new.employees_count,
                    employees_raw = new.employees_raw,
                    _silver_updated_at = new._silver_updated_at,
                    _source_batch_id   = new._source_batch_id;
            """
            # 執行 SQL 語句 (批次處理 Insert / Update)
            cursor.executemany(sql, cleaned_data_list)

        mysql_conn.commit()
        print(
            f"成功將 {len(cleaned_data_list)} 筆資料批次 Upsert 至 MySQL 的 company 表格！"
        )
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()

def sliver_company_mongodb_to_mysql():
    collection = conn_to_mongodb("localhost", "tkr102", "job_details")
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    print("開始處理 sliver_company")
    today = datetime.combine(datetime.now().date(), time.min)

    # 1. 昨天 (今天 - 1 天) 的 23:55
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)

    # 2. 明天 (今天 + 1 天) 的 00:00
    end_time = today + timedelta(days=1)

    pipeline = [
        # 篩選條件
        {"$match": {"switch": "on"}},
        # 1. 先用 $match 篩選時間區間（優先縮小資料量，才能走索引效能最好）
        {
            "$match": {
                "ingestion_timestamp": {
                    "$gte": start_time,  # 昨天 23:55:00
                    "$lt": end_time,  # 明天 00:00:00
                }
            }
        },
        # 2. 依照 batch_id 降冪排序，確保 $first 取得最新批次資料
        {"$sort": {"batch_id": -1}},
        # 3. 群組階段：依據單一 PK (custNo) 進行去重
        {
            "$group": {
                "_id": "$custNo",
                "cust_url": {"$first": "$header.custUrl"},
                "cust_name": {"$first": "$header.custName"},
                "industry_name": {"$first": "$industry"},
                "industry_no": {"$first": "$industryNo"},
                "employees_raw": {"$first": "$employees"},
                "source_batch_id": {"$first": "$batch_id"}
            }
        },
        # 4. 欄位清洗與轉置 (取號方式微調)
        {
            "$project": {
                "_id": 0,
                "cust_no": "$_id",  # 直接將 _id 當作 cust_no
                "cust_name": 1,
                "cust_url": 1,
                "industry_name": 1,
                "industry_no": 1,
                "employees_raw": 1,
                # 擷取數字，若完全找不到數字則返回 null
                "employees_count": {
                    "$let": {
                        "vars": {
                            "matches": {
                                "$regexFindAll": {
                                    "input": {
                                        "$ifNull": ["$employees_raw", ""]
                                    },
                                    "regex": "\\d+",
                                }
                            }
                        },
                        "in": {
                            "$cond": {
                                "if": {"$gt": [{"$size": "$$matches"}, 0]},
                                "then": {
                                    "$toInt": {
                                        "$arrayElemAt": ["$$matches.match", 0]
                                    }
                                },
                                "else": None,
                            }
                        },
                    }
                },
                "_silver_updated_at": "$$NOW",
                "_source_batch_id": 1,
            }
        },
    ]

    cursor_list = collection.aggregate(pipeline)

    cleaned_data_list_company = []
    for doc in cursor_list:
        cleaned_item = {
            "cust_no": doc.get("cust_no"),
            # 2. 修正 typo: 原為 "ust_name" -> 修正為 "cust_name"
            "cust_name": doc.get("cust_name"),
            "cust_url": doc.get("cust_url"),
            "industry_name": doc.get("industry_name"),
            "industry_no": doc.get("industry_no"),
            "employees_count": doc.get("employees_count"),
            "employees_raw": doc.get("employees_raw"),
            "_silver_updated_at": datetime.now(),
            "_source_batch_id": doc.get("source_batch_id"),
        }

        cleaned_data_list_company.append(cleaned_item)

    # 連線到 MySQL 並將清理後的資料寫入 company 表格
    import_company_to_mysql(cleaned_data_list_company)

sliver_company_mongodb_to_mysql()

