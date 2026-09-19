import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection



# ===== job =====
# ===== Part 1: 寫入輕量/核心欄位 (快速釋放鎖與清空 Socket Buffer) =====
def import_job_part1_to_mysql(cleaned_data_list_p1):
    sql = """
        INSERT INTO job (
            job_id, cust_no, job_name, appear_date, close_date,
            salary_raw_text, salary_min, salary_max, salary_type_code, is_salary_negotiable,
            job_type_code, work_exp_requirement, edu_requirement, postal_code, address_region,
            address_area, address_detail, landmark, longitude, latitude,
            remote_work_status, need_emp_count_text, hr_behavior_pr, contact_email,
            analysis_url, updated_at, source_batch_id, url_status
        ) VALUES (
            %(job_id)s, %(cust_no)s, %(job_name)s, %(appear_date)s, %(close_date)s,
            %(salary_raw_text)s, %(salary_min)s, %(salary_max)s, %(salary_type_code)s, %(is_salary_negotiable)s,
            %(job_type_code)s, %(work_exp_requirement)s, %(edu_requirement)s, %(postal_code)s, %(address_region)s,
            %(address_area)s, %(address_detail)s, %(landmark)s, %(longitude)s, %(latitude)s,
            %(remote_work_status)s, %(need_emp_count_text)s, %(hr_behavior_pr)s, %(contact_email)s,
            %(analysis_url)s, %(updated_at)s, %(source_batch_id)s, %(url_status)s
        )
        ON DUPLICATE KEY UPDATE
            cust_no = VALUES(cust_no),
            job_name = VALUES(job_name),
            appear_date = VALUES(appear_date),
            close_date = VALUES(close_date),
            salary_raw_text = VALUES(salary_raw_text),
            salary_min = VALUES(salary_min),
            salary_max = VALUES(salary_max),
            salary_type_code = VALUES(salary_type_code),
            is_salary_negotiable = VALUES(is_salary_negotiable),
            job_type_code = VALUES(job_type_code),
            work_exp_requirement = VALUES(work_exp_requirement),
            edu_requirement = VALUES(edu_requirement),
            postal_code = VALUES(postal_code),
            address_region = VALUES(address_region),
            address_area = VALUES(address_area),
            address_detail = VALUES(address_detail),
            landmark = VALUES(landmark),
            longitude = VALUES(longitude),
            latitude = VALUES(latitude),
            remote_work_status = VALUES(remote_work_status),
            need_emp_count_text = VALUES(need_emp_count_text),
            hr_behavior_pr = VALUES(hr_behavior_pr),
            contact_email = VALUES(contact_email),
            analysis_url = VALUES(analysis_url),
            updated_at = VALUES(updated_at),
            source_batch_id = VALUES(source_batch_id),
            url_status = VALUES(url_status);
    """
    run_mysql_upsert(sql, cleaned_data_list_p1)


# ===== Part 2: 寫入巨量長文字與補充說明欄位 (單獨更新) =====
def import_job_part2_to_mysql(cleaned_data_list_p2):
    sql = """
        INSERT INTO job (
            job_id, cust_no, job_description, remote_work_description, vacation_policy_text,
            business_trip_text, manage_resp_text, start_working_day_text, welfare_description
        ) VALUES (
            %(job_id)s, %(cust_no)s, %(job_description)s, %(remote_work_description)s, %(vacation_policy_text)s,
            %(business_trip_text)s, %(manage_resp_text)s, %(start_working_day_text)s, %(welfare_description)s
        )
        ON DUPLICATE KEY UPDATE
            cust_no = VALUES(cust_no),
            job_description = VALUES(job_description),
            remote_work_description = VALUES(remote_work_description),
            vacation_policy_text = VALUES(vacation_policy_text),
            business_trip_text = VALUES(business_trip_text),
            manage_resp_text = VALUES(manage_resp_text),
            start_working_day_text = VALUES(start_working_day_text),
            welfare_description = VALUES(welfare_description);
    """
    run_mysql_upsert(sql, cleaned_data_list_p2)


def silver_job_mongodb_to_mysql():
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_job")
    today = datetime.combine(datetime.now().date(), time.min)
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)
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
        {"$sort": {"ingestion_timestamp": -1}},
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
                                    "urlParts": {"$split": ["$header.analysisUrl", "/"]}
                                },
                                "in": {"$arrayElemAt": ["$$urlParts", -1]}
                            }
                        },
                        "else": None,
                    }
                },
                "doc": {"$first": "$$ROOT"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id",
                "cust_no": "$doc.custNo",
                "job_name": "$doc.header.jobName",
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
                "job_description": "$doc.jobDetail.jobDescription",
                "salary_raw_text": "$doc.jobDetail.salary",
                "salary_min": {"$cond": {"if": {"$eq": ["$doc.jobDetail.salaryType", 10]}, "then": 0, "else": "$doc.jobDetail.salaryMin"}},
                "salary_max": {"$cond": {"if": {"$eq": ["$doc.jobDetail.salaryType", 10]}, "then": 0, "else": "$doc.jobDetail.salaryMax"}},
                "salary_type_code": "$doc.jobDetail.salaryType",
                "is_salary_negotiable": {"$cond": {"if": {"$eq": ["$doc.jobDetail.salaryType", 10]}, "then": True, "else": False}},
                "job_type_code": "$doc.jobDetail.jobType",
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
                "updated_at": "$$NOW",
                "source_batch_id": "$doc.batch_id",
                "url_status": "$doc.switch",
            }
        }
    ]

    cleaned_data_list_p1 = []
    cleaned_data_list_p2 = []

    for doc in collection.aggregate(pipeline):
        # 拆分 1: 輕量/數值/時間/標籤欄位
        cleaned_data_list_p1.append({
            "job_id": doc.get("job_id"),
            "cust_no": doc.get("cust_no"),
            "job_name": doc.get("job_name"),
            "appear_date": doc.get("appear_date"),
            "close_date": doc.get("close_date"),
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
            "need_emp_count_text": doc.get("need_emp_count_text"),
            "hr_behavior_pr": doc.get("hr_behavior_pr"),
            "contact_email": doc.get("contact_email"),
            "analysis_url": doc.get("analysis_url"),
            "updated_at": doc.get("updated_at"),
            "source_batch_id": doc.get("source_batch_id"),
            "url_status": doc.get("url_status"),
        })

        # 拆分 2: 巨量長文字與補充欄位
        cleaned_data_list_p2.append({
            "job_id": doc.get("job_id"),
            "cust_no": doc.get("cust_no"),
            "job_description": doc.get("job_description"),
            "remote_work_description": doc.get("remote_work_description"),
            "vacation_policy_text": doc.get("vacation_policy_text"),
            "business_trip_text": doc.get("business_trip_text"),
            "manage_resp_text": doc.get("manage_resp_text"),
            "start_working_day_text": doc.get("start_working_day_text"),
            "welfare_description": doc.get("welfare_description"),
        })

    print(f"Mongo 查詢完成，共取得 {len(cleaned_data_list_p1)} 筆資料（P1/P2 各 {len(cleaned_data_list_p1)} 筆），準備分兩次寫入 MySQL")


    if cleaned_data_list_p1:
        print("執行 Part 1: 寫入基礎屬性欄位...")
        import_job_part1_to_mysql(cleaned_data_list_p1)
        
        print("執行 Part 2: 寫入長文字與細節說明欄位...")
        import_job_part2_to_mysql(cleaned_data_list_p2)
        print("silver_job 兩階段更新完畢！")


