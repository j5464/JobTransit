import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection


# ===== job_category =====
def import_category_to_mysql(cleaned_data_list):
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
    run_mysql_upsert(sql, cleaned_data_list)


def silver_category_mongodb_to_mysql():
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_category")
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
            "$addFields": {
                "parsed_job_id": {
                    "$arrayElemAt": [
                        {
                            "$split": [
                                {"$trim": {"input": "$header.analysisUrl", "chars": "/"}},
                                "/",
                            ]
                        },
                        -1,
                    ]
                },
                "raw_job_category": "$jobDetail.jobCategory",
            }
        },
        {"$unwind": "$jobDetail.jobCategory"},
        {
            "$project": {
                "_id": 0,
                "job_id": "$parsed_job_id",
                "category_code": "$jobDetail.jobCategory.code",
                "category_description": "$jobDetail.jobCategory.description",
                "seq_no": {"$indexOfArray": ["$raw_job_category", "$jobDetail.jobCategory"]},
            }
        },
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

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
            "job_id": doc.get("job_id"),
            "category_code": doc.get("category_code"),
            "category_description": doc.get("category_description"),
            "seq_no": doc.get("seq_no"),
        })

    if cleaned_data_list:
        import_category_to_mysql(cleaned_data_list)

