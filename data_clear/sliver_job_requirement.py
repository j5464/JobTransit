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

# 將 job 寫入 MySQL 的 job 表格中，並依照指定欄位順序寫入
def import_requirement_to_mysql(cleaned_data_list):
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
            # 採用方案 A (MySQL 原生語法 ON DUPLICATE KEY UPDATE)
            # MySQL 8.0+ 建議使用 new 別名語法，或 VALUES() 語法
            sql = """
                INSERT INTO job_requirement (
                    job_id, requirement_type, requirement_value
                ) VALUES (
                    %(job_id)s, %(requirement_type)s, %(requirement_value)s
                )
                AS new
                ON DUPLICATE KEY UPDATE
                    requirement_value = new.requirement_value;
            """
            # 執行批次寫入
            cursor.executemany(sql, cleaned_data_list)

        # 提交事務
        mysql_conn.commit()
        print(
            f"成功將 {len(cleaned_data_list)} 筆資料寫入至 MySQL 的 job_requirement 表格！"
        )
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()


def sliver_job_requirement():
    collection = conn_to_mongodb("localhost", "tkr102", "job_details")
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    print("開始處理 sliver_job_requirement")
    # 計算「昨天 23:55 ~ 明天 00:00」時間區間
    today = datetime.now().date()
    start_time = datetime.combine(today - timedelta(days=1), time(23, 55, 0))
    end_time = datetime.combine(today + timedelta(days=1), time(0, 0, 0))

    pipeline = [
        # 1. 條件篩選：switch: on 且 ingestion_timestamp 在指定範圍內
        {
            "$match": {
                "switch": "on",
                "ingestion_timestamp": {"$gte": start_time, "$lt": end_time},
            }
        },
        # 2. 依照 ingestion_timestamp 由新到舊排序
        {"$sort": {"ingestion_timestamp": -1}},
        # 3. 擷取純 job_id，並保留相關條件欄位
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
                "condition.major": 1,
                "condition.driverLicense": 1,
                "condition.acceptRole.role": 1,
                "jobDetail.workType": 1,
                "condition.certificate": 1,
            }
        },
        # 4. 利用 $facet 分別拆解與展平各項條件陣列
        {
            "$facet": {
                # 1. 科系要求 (MAJOR)
                "major": [
                    {"$unwind": "$condition.major"},
                    {
                        "$project": {
                            "_id": 0,
                            "job_id": 1,
                            "requirement_type": "MAJOR",
                            "requirement_value": "$condition.major",
                        }
                    },
                ],
                # 2. 駕照要求 (DRIVER_LICENSE)
                "driver_license": [
                    {"$unwind": "$condition.driverLicense"},
                    {
                        "$project": {
                            "_id": 0,
                            "job_id": 1,
                            "requirement_type": "DRIVER_LICENSE",
                            "requirement_value": "$condition.driverLicense",
                        }
                    },
                ],
                # 3. 接受身份 (ACCEPT_ROLE)
                "accept_role": [
                    {"$unwind": "$condition.acceptRole.role"},
                    {
                        "$project": {
                            "_id": 0,
                            "job_id": 1,
                            "requirement_type": "ACCEPT_ROLE",
                            "requirement_value": "$condition.acceptRole.role.description",
                        }
                    },
                ],
                # 4. 工作性質 (WORK_TYPE)
                "work_type": [
                    {"$unwind": "$jobDetail.workType"},
                    {
                        "$project": {
                            "_id": 0,
                            "job_id": 1,
                            "requirement_type": "WORK_TYPE",
                            "requirement_value": "$jobDetail.workType",
                        }
                    },
                ],
                # 5. 證照需求 (CERTIFICATE)
                "certificate": [
                    {"$unwind": "$condition.certificate"},
                    {
                        "$project": {
                            "_id": 0,
                            "job_id": 1,
                            "requirement_type": "CERTIFICATE",
                            "requirement_value": "$condition.certificate",
                        }
                    },
                ],
            }
        },
        # 5. 將所有條件陣列合併並展平為獨立 Document
        {
            "$project": {
                "requirements": {
                    "$concatArrays": [
                        "$major",
                        "$driver_license",
                        "$accept_role",
                        "$work_type",
                        "$certificate",
                    ]
                }
            }
        },
        {"$unwind": "$requirements"},
        {"$replaceRoot": {"newRoot": "$requirements"}},
        # 6. 以 job_id & requirement_type 去重，取最新 (第一筆) 的 requirement_value
        {
            "$group": {
                "_id": {
                    "job_id": "$job_id",
                    "requirement_type": "$requirement_type",
                },
                "requirement_value": {"$first": "$requirement_value"},
            }
        },
        # 7. 還原平坦化結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id.job_id",
                "requirement_type": "$_id.requirement_type",
                "requirement_value": "$requirement_value",
            }
        },
    ]

    list_data = collection.aggregate(pipeline)

    # 將清理後的資料，依照指定欄位順序寫入 MySQL
    cleaned_data_list_requirement = []
    for doc in list_data:
        cleaned_item = {
            "job_id": doc.get("job_id"),
            "requirement_type": doc.get("requirement_type"),
            "requirement_value": doc.get("requirement_value"),
        }
        cleaned_data_list_requirement.append(cleaned_item)

    # 連線到 MySQL 並將清理後的資料寫入 job 表格
    if cleaned_data_list_requirement:
        import_requirement_to_mysql(cleaned_data_list_requirement)
    else:
        print("指定時間區間內無符合條件的資料。")


sliver_job_requirement()