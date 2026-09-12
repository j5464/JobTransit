from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime, time, timedelta
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

# 將 job 寫入 MySQL 的 job 表格中 (改為 Upsert 方案 A)
def insert_job_to_mysql(cleaned_data_list):
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
            # 方案 A 的 Upsert SQL 語句
            sql = """
                INSERT INTO job (
                    job_id, cust_no, job_name, appear_date, close_date,
                    job_description, salary_raw_text, salary_min, salary_max,
                    salary_type_code, is_salary_negotiable, job_type_code,
                    work_exp_requirement, edu_requirement, postal_code,
                    address_region, address_area, address_detail, landmark,
                    longitude, latitude, remote_work_status, remote_work_description,
                    vacation_policy_text, business_trip_text, manage_resp_text,
                    start_working_day_text, need_emp_count_text, hr_behavior_pr,
                    contact_email, welfare_description, analysis_url,
                    updated_at, source_batch_id
                ) VALUES (
                    %(job_id)s, %(cust_no)s, %(job_name)s, %(appear_date)s, %(close_date)s,
                    %(job_description)s, %(salary_raw_text)s, %(salary_min)s, %(salary_max)s,
                    %(salary_type_code)s, %(is_salary_negotiable)s, %(job_type_code)s,
                    %(work_exp_requirement)s, %(edu_requirement)s, %(postal_code)s,
                    %(address_region)s, %(address_area)s, %(address_detail)s, %(landmark)s,
                    %(longitude)s, %(latitude)s, %(remote_work_status)s, %(remote_work_description)s,
                    %(vacation_policy_text)s, %(business_trip_text)s, %(manage_resp_text)s,
                    %(start_working_day_text)s, %(need_emp_count_text)s, %(hr_behavior_pr)s,
                    %(contact_email)s, %(welfare_description)s, %(analysis_url)s,
                    %(updated_at)s, %(source_batch_id)s
                )
                AS new
                ON DUPLICATE KEY UPDATE
                    cust_no = new.cust_no,
                    job_name = new.job_name,
                    appear_date = new.appear_date,
                    close_date = new.close_date,
                    job_description = new.job_description,
                    salary_raw_text = new.salary_raw_text,
                    salary_min = new.salary_min,
                    salary_max = new.salary_max,
                    salary_type_code = new.salary_type_code,
                    is_salary_negotiable = new.is_salary_negotiable,
                    job_type_code = new.job_type_code,
                    work_exp_requirement = new.work_exp_requirement,
                    edu_requirement = new.edu_requirement,
                    postal_code = new.postal_code,
                    address_region = new.address_region,
                    address_area = new.address_area,
                    address_detail = new.address_detail,
                    landmark = new.landmark,
                    longitude = new.longitude,
                    latitude = new.latitude,
                    remote_work_status = new.remote_work_status,
                    remote_work_description = new.remote_work_description,
                    vacation_policy_text = new.vacation_policy_text,
                    business_trip_text = new.business_trip_text,
                    manage_resp_text = new.manage_resp_text,
                    start_working_day_text = new.start_working_day_text,
                    need_emp_count_text = new.need_emp_count_text,
                    hr_behavior_pr = new.hr_behavior_pr,
                    contact_email = new.contact_email,
                    welfare_description = new.welfare_description,
                    analysis_url = new.analysis_url,
                    updated_at = new.updated_at,
                    source_batch_id = new.source_batch_id;
            """
            # 執行 SQL 語句 (批次處理 Insert / Update)
            cursor.executemany(sql, cleaned_data_list)

        mysql_conn.commit()
        print(
            f"成功批次 Upsert {len(cleaned_data_list)} 筆資料至 MySQL 的 job 表格！"
        )
    except Exception as e:
        print(f"寫入 MySQL 時發生錯誤: {e}")
    finally:
        mysql_conn.close()

def sliver_job_mongodb_to_mysql():
    collection = conn_to_mongodb('localhost', 'tkr102', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    print("開始處理 sliver_job")
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
        # 2. 針對篩選後的資料進行排序（由新到舊 -1，取最新快照）
        {"$sort": {"ingestion_timestamp": -1}},
        # 3. 以 job_id 去重，取最新紀錄 ($first)
        {
            "$group": {
                "_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$ne": ["$header.analysisUrl", None]},
                                {"$ne": ["$header.analysisUrl", ""]},
                            ]
                        },
                        "then": {
                            "$let": {
                                "vars": {
                                    "urlParts": {
                                        "$split": ["$header.analysisUrl", "/"]
                                    }
                                },
                                "in": {"$arrayElemAt": ["$$urlParts", -1]},
                            }
                        },
                        "else": None,
                    }
                },
                "doc": {"$first": "$$ROOT"},
            }
        },
        # 4. 欄位轉置 ($project)，注意所有原始欄位前都要加 doc.
        {
            "$project": {
                "_id": 0,
                # 1. 直接取 group 算好的 _id 當作 job_id
                "job_id": "$_id",
                "cust_no": "$doc.custNo",
                "job_name": "$doc.header.jobName",
                # 2. 日期轉換
                "appear_date": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$ne": ["$doc.header.appearDate", None]},
                                {"$ne": ["$doc.header.appearDate", ""]},
                            ]
                        },
                        "then": {"$toDate": "$doc.header.appearDate"},
                        "else": None,
                    }
                },
                "close_date": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$ne": ["$doc.closeDate", None]},
                                {"$ne": ["$doc.closeDate", ""]},
                            ]
                        },
                        "then": {"$toDate": "$doc.closeDate"},
                        "else": None,
                    }
                },
                # 3. 核心內容與薪資轉置
                "job_description": "$doc.jobDetail.jobDescription",
                "salary_raw_text": "$doc.jobDetail.salary",
                "salary_min": {
                    "$cond": {
                        "if": {"$eq": ["$doc.jobDetail.salaryType", 10]},
                        "then": 0,
                        "else": "$doc.jobDetail.salaryMin",
                    }
                },
                "salary_max": {
                    "$cond": {
                        "if": {"$eq": ["$doc.jobDetail.salaryType", 10]},
                        "then": 0,
                        "else": "$doc.jobDetail.salaryMax",
                    }
                },
                "salary_type_code": "$doc.jobDetail.salaryType",
                "is_salary_negotiable": {
                    "$cond": {
                        "if": {"$eq": ["$doc.jobDetail.salaryType", 10]},
                        "then": True,
                        "else": False,
                    }
                },
                "job_type_code": "$doc.jobDetail.jobType",
                # 4. 條件與地點資訊
                "work_exp_requirement": "$doc.condition.workExp",
                "edu_requirement": "$doc.condition.edu",
                "postal_code": {
                    "$convert": {
                        "input": "$doc.postalCode",
                        "to": "int",
                        "onError": None,
                        "onNull": None,
                    }
                },
                "address_region": "$doc.jobDetail.addressRegion",
                "address_area": "$doc.jobDetail.addressArea",
                "address_detail": "$doc.jobDetail.addressDetail",
                "landmark": "$doc.jobDetail.landmark",
                "longitude": {
                    "$convert": {
                        "input": "$doc.jobDetail.longitude",
                        "to": "double",
                        "onError": None,
                        "onNull": None,
                    }
                },
                "latitude": {
                    "$convert": {
                        "input": "$doc.jobDetail.latitude",
                        "to": "double",
                        "onError": None,
                        "onNull": None,
                    }
                },
                # 5. 遠端工作狀態處理
                "remote_work_status": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {
                                    "$eq": ["$doc.jobDetail.remoteWork", None]
                                },
                                "then": "NOT_SPECIFIED",
                            },
                            {
                                "case": {
                                    "$eq": [
                                        "$doc.jobDetail.remoteWork.type",
                                        1,
                                    ]
                                },
                                "then": "ON_SITE_TYPE1",
                            },
                            {
                                "case": {
                                    "$eq": [
                                        "$doc.jobDetail.remoteWork.type",
                                        2,
                                    ]
                                },
                                "then": "HYBRID_TYPE2",
                            },
                        ],
                        "default": "NOT_SPECIFIED",
                    }
                },
                "remote_work_description": {
                    "$cond": {
                        "if": {
                            "$or": [
                                {"$eq": ["$doc.jobDetail.remoteWork", None]},
                                {
                                    "$eq": [
                                        "$doc.jobDetail.remoteWork.description",
                                        None,
                                    ]
                                },
                                {
                                    "$eq": [
                                        "$doc.jobDetail.remoteWork.description",
                                        "",
                                    ]
                                },
                            ]
                        },
                        "then": None,
                        "else": {
                            "$toString": "$doc.jobDetail.remoteWork.description"
                        },
                    }
                },
                # 6. 其他詳細條件與聯絡資訊
                "vacation_policy_text": "$doc.jobDetail.vacationPolicy",
                "business_trip_text": "$doc.jobDetail.businessTrip",
                "manage_resp_text": "$doc.jobDetail.manageResp",
                "start_working_day_text": "$doc.jobDetail.startWorkingDay",
                "need_emp_count_text": "$doc.jobDetail.needEmp",
                "hr_behavior_pr": {
                    "$convert": {
                        "input": "$doc.header.hrBehaviorPR",
                        "to": "double",
                        "onError": None,
                        "onNull": None,
                    }
                },
                "contact_email": "$doc.contact.email",
                "welfare_description": "$doc.welfare.welfare",
                "analysis_url": "$doc.header.analysisUrl",
                # 7. ETL 與 系統 Metadata
                "updated_at": "$$NOW",
                "source_batch_id": "$doc.batch_id",
            }
        },
    ]
    
    list = collection.aggregate(pipeline)

    # 將清理後的資料，依照以下指定欄位順序寫入 MySQL，欄位格是不可變動
    # 1. `job_id`
    # 2. `cust_no`
    # 3. `job_name`
    # 4. `appear_date`
    # 5. `close_date`
    # 6. `job_description`
    # 7. `salary_raw_text`
    # 8. `salary_min`
    # 9. `salary_max`
    # 10. `salary_type_code`
    # 11. `is_salary_negotiable`
    # 12. `job_type_code`
    # 13. `work_exp_requirement`
    # 14. `edu_requirement`
    # 15. `postal_code`
    # 16. `address_region`
    # 17. `address_area`
    # 18. `address_detail`
    # 19. `landmark`
    # 20. `longitude`
    # 21. `latitude`
    # 22. `remote_work_status`
    # 23. `remote_work_description`
    # 24. `vacation_policy_text`
    # 25. `business_trip_text`
    # 26. `manage_resp_text`
    # 27. `start_working_day_text`
    # 28. `need_emp_count_text`
    # 29. `hr_behavior_pr`
    # 30. `contact_email`
    # 31. `welfare_description`
    # 32. `analysis_url`
    # 33. `updated_at`
    # 34. `source_batch_id`
    cleaned_data_list = []
    for doc in list:
        cleaned_item = {
            "job_id": doc.get("job_id"),
            "cust_no": doc.get("cust_no"),
            "job_name": doc.get("job_name"),
            "appear_date": doc.get("appear_date"),
            "close_date": doc.get("close_date"),
            "job_description": doc.get("job_description"),
            "salary_raw_text": doc.get("salary_raw_text"),
            "salary_min": doc.get("salary_min"),
            "salary_max": doc.get("salary_max"),
            "salary_type_code": doc.get("salary_type_code"),
            "is_salary_negotiable": doc.get("is_salary_negotiable"),
            "job_type_code": doc.get("job_type_code"),
            "work_exp_requirement": doc.get("work_exp_requirement"),
            "edu_requirement": doc.get("edu_requirement"),
            "postal_code": doc.get("postal_code"),
            "address_region": doc.get("address_region"),
            "address_area": doc.get("address_area"),
            "address_detail": doc.get("address_detail"),
            "landmark": doc.get("landmark"),
            "longitude": doc.get("longitude"),
            "latitude": doc.get("latitude"),
            "remote_work_status": doc.get("remote_work_status"),
            "remote_work_description": doc.get("remote_work_description"),
            "vacation_policy_text": doc.get("vacation_policy_text"),
            "business_trip_text": doc.get("business_trip_text"),
            "manage_resp_text": doc.get("manage_resp_text"),
            "start_working_day_text": doc.get("start_working_day_text"),
            "need_emp_count_text": doc.get("need_emp_count_text"),
            "hr_behavior_pr": doc.get("hr_behavior_pr"),
            "contact_email": doc.get("contact_email"),
            "welfare_description": doc.get("welfare_description"),
            "analysis_url": doc.get("analysis_url"),
            "updated_at": datetime.now(),
            "source_batch_id": doc.get("source_batch_id")
        }

        cleaned_data_list.append(cleaned_item)

    #連線到 MySQL 並將清理後的資料寫入 job 表格
    insert_job_to_mysql(cleaned_data_list)

sliver_job_mongodb_to_mysql()


