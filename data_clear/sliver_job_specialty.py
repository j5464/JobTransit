from pendulum import today
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from urllib.parse import urlparse
from datetime import datetime, timedelta, time
from pymysql import connect

#建立與 MongoDB 的連線，並回傳指定的 Collection
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

def specialty_refer_list(collection):
    # # 連接到 MongoDB 並獲取指定的 collection
    # collection = conn_to_mongodb('localhost', 'test', 'job_details')
    # if collection is None:
    #     print("無法連線到 MongoDB，請檢查伺服器狀態。")
    #     return []

    # 1. 從 MongoDB 取出資料 (使用 MongoDB 的聚合管道來展開 specialty 陣列並去重)
    pipeline_refer_list = [
        {"$project": {"condition": 1}},
        {"$unwind": "$condition.specialty"},
        {"$group": {
                "_id": "$condition.specialty.code",
                "description": {"$first": "$condition.specialty.description"}
            }
        },
        {
            "$merge": {
                "into": "specialties_refer_list",
                "whenMatched": "replace",      # 若主鍵存在則替換更新
                "whenNotMatched": "insert"      # 若不存在則新增
            }
        }
    ]

    collection.aggregate(pipeline_refer_list)

    print(f"已更新specialty參照清單")

# 2. 寫入 MySQL 的函式 (套用 Schema：job_id, specialty_code, specialty_name)
def import_job_specialty_to_mysql(cleaned_data_list):
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
            # 對齊 MySQL Schema 欄位：job_id, specialty_code, specialty_name
            sql = """
                INSERT INTO job_specialty (
                    job_id, specialty_code, specialty_name
                ) VALUES (
                    %(job_id)s, %(specialty_code)s, %(specialty_name)s
                )
                AS new
                ON DUPLICATE KEY UPDATE
                    specialty_name = new.specialty_name;
            """
            # 批次執行 Upsert
            cursor.executemany(sql, cleaned_data_list)

        mysql_conn.commit()
        print(
            f"成功將 {len(cleaned_data_list)} 筆資料批次 Upsert 至 MySQL 的 job_specialty 表格！"
        )
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()

# 3. MongoDB 轉置與主要 ETL 流程
def sliver_job_specialty():
    collection = conn_to_mongodb("localhost", "test", "job_details")
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return
    
    print("開始處理 sliver_job_specialty")

    specialty_refer_list(collection)
        
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
        # 2. 針對篩選後的資料進行排序（由新到舊 -1，取最新快照）
        {"$sort": {"ingestion_timestamp": -1}},
        # 1. 展開 condition 陣列
        {"$unwind": "$condition"},
        # 2. 解析 job_id，並取出原始 condition.specialty
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
                "raw_specialties": {
                    "$cond": {
                        "if": {"$isArray": "$condition.specialty"},
                        "then": "$condition.specialty",
                        "else": ["$condition.specialty"],
                    }
                },
            }
        },
        # 3. 關聯 job_tools
        {
            "$lookup": {
                "from": "specialties_refer_list",
                "let": {
                    "other_text": {"$ifNull": ["$condition.other", ""]},
                    "desc_text": {
                        "$ifNull": ["$jobDetail.jobDescription", ""]
                    },
                    "spec_names": {
                        "$ifNull": ["$raw_specialties.description", []]
                    },
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$or": [
                                    {"$in": ["$description", "$$spec_names"]},
                                    {
                                        "$regexMatch": {
                                            "input": "$$other_text",
                                            "regex": "$description",
                                            "options": "i",
                                        }
                                    },
                                    {
                                        "$regexMatch": {
                                            "input": "$$desc_text",
                                            "regex": "$description",
                                            "options": "i",
                                        }
                                    },
                                ]
                            }
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "specialty_code": "$_id",
                            "specialty_name": "$description",
                        }
                    },
                ],
                "as": "matched_tools",
            }
        },
        # 4. 展開匹配到的工具物件陣列
        {"$unwind": "$matched_tools"},
        # 5. 整理輸出結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$parsed_job_id",
                "specialty_code": "$matched_tools.specialty_code",
                "specialty_name": "$matched_tools.specialty_name",
            }
        },
        # 6. 利用 $group 去重
        {
            "$group": {
                "_id": {
                    "job_id": "$job_id",
                    "specialty_code": "$specialty_code",
                    "specialty_name": "$specialty_name",
                }
            }
        },
        # 7. 還原平坦化結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id.job_id",
                "specialty_code": "$_id.specialty_code",
                "specialty_name": "$_id.specialty_name",
            }
        },
    ]

    cursor_list = collection.aggregate(pipeline)

    # 封裝為符合 Schema 的格式
    cleaned_data_list = []
    for doc in cursor_list:
        cleaned_item = {
            "job_id": doc.get("job_id"),
            "specialty_code": doc.get("specialty_code"),
            "specialty_name": doc.get("specialty_name"),
        }
        cleaned_data_list.append(cleaned_item)

    # 執行 MySQL Upsert 寫入
    if cleaned_data_list:
        import_job_specialty_to_mysql(cleaned_data_list)
    else:
        print("未產出任何清洗資料。")

# 執行流程
specialty_refer_list()
sliver_job_specialty()