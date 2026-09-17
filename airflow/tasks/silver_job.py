import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection



# ===== job =====
def import_job_to_mysql(cleaned_data_list):
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
            updated_at, source_batch_id, url_status
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
            %(updated_at)s, %(source_batch_id)s, %(url_status)s
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
            source_batch_id = new.source_batch_id,
            url_status = new.url_status;
    """
    run_mysql_upsert(sql, cleaned_data_list)


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
        # {
        #     "$match": {
        #         "ingestion_timestamp": {
        #             "$gte": start_time,  # 昨天 23:55:00
        #             "$lt": end_time,  # 明天 00:00:00
        #         }
        #     }
        # },
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
                "edu_requirement": "$doc.condition.education",
                "postal_code": "$doc.jobDetail.postalCode",
                "address_region": "$doc.jobDetail.addressRegion",
                "address_area": "$doc.jobDetail.addressArea",
                "address_detail": "$doc.jobDetail.addressDetail",
                "landmark": "$doc.jobDetail.landmark",
                "longitude": "$doc.location.longitude",
                "latitude": "$doc.location.latitude",
                "remote_work_status": "$doc.jobDetail.remoteWorkStatus",
                "remote_work_description": "$doc.jobDetail.remoteWorkDescription",
                "vacation_policy_text": "$doc.jobDetail.vacationPolicy",
                "business_trip_text": "$doc.jobDetail.businessTrip",
                "manage_resp_text": "$doc.jobDetail.manageResponse",
                "start_working_day_text": "$doc.jobDetail.startWorkingDay",
                "need_emp_count_text": "$doc.jobDetail.needEmpCount",
                "hr_behavior_pr": "$doc.jobDetail.hrBehaviorPr",
                "contact_email": "$doc.jobDetail.contactEmail",
                "welfare_description": "$doc.jobDetail.welfare",
                "analysis_url": "$doc.header.analysisUrl",
                "updated_at": "$doc.ingestion_timestamp",
                "source_batch_id": "$doc.batch_id",
                "url_status": "$doc.switch",
            }
        }
    ]

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
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
            "updated_at": doc.get("updated_at"),
            "source_batch_id": doc.get("source_batch_id"),
            "url_status": doc.get("url_status"),
        })
    print(f"Mongo 查詢完成，共取得 {len(cleaned_data_list)} 筆資料")

    if cleaned_data_list:
        import_job_to_mysql(cleaned_data_list)


