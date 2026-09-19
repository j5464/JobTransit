import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection


# ===== job_specialty =====
def import_job_specialty_to_mysql(cleaned_data_list):
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
    run_mysql_upsert(sql, cleaned_data_list)


def silver_job_specialty():
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_job_specialty")
    today = datetime.combine(datetime.now().date(), time.min)
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)
    end_time = today + timedelta(days=1)

    pipeline_refer_list = [
        {"$project": {"condition": 1}},
        {"$unwind": "$condition.specialty"},
        {"$group": {"_id": "$condition.specialty.code", "description": {"$first": "$condition.specialty.description"}}},
        {"$merge": {"into": "specialties_refer_list", "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]
    collection.aggregate(pipeline_refer_list)

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
        {"$unwind": "$condition"},
        {"$addFields": {
            "parsed_job_id": {
                "$arrayElemAt": [
                    {"$split": [{"$trim": {"input": "$header.analysisUrl", "chars": "/"}}, "/"]},
                    -1,
                ]
            },
            "raw_specialties": {"$cond": {"if": {"$isArray": "$condition.specialty"}, "then": "$condition.specialty", "else": ["$condition.specialty"]}},
        }},
        {
            "$lookup": {
                "from": "specialties_refer_list",
                "let": {
                    "other_text": {"$ifNull": ["$condition.other", ""]},
                    "desc_text": {"$ifNull": ["$jobDetail.jobDescription", ""]},
                    "spec_names": {"$ifNull": ["$raw_specialties.description", []]},
                },
                "pipeline": [
                    {"$match": {"$expr": {"$or": [
                        {"$in": ["$description", "$$spec_names"]},
                        {"$regexMatch": {"input": "$$other_text", "regex": "$description", "options": "i"}},
                        {"$regexMatch": {"input": "$$desc_text", "regex": "$description", "options": "i"}},
                    ]}}},
                    {"$project": {"_id": 0, "specialty_code": "$_id", "specialty_name": "$description"}},
                ],
                "as": "matched_tools",
            }
        },
        {"$unwind": "$matched_tools"},
        {"$project": {"_id": 0, "job_id": "$parsed_job_id", "specialty_code": "$matched_tools.specialty_code", "specialty_name": "$matched_tools.specialty_name"}},
        {"$group": {"_id": {"job_id": "$job_id", "specialty_code": "$specialty_code", "specialty_name": "$specialty_name"}}},
        {"$project": {"_id": 0, "job_id": "$_id.job_id", "specialty_code": "$_id.specialty_code", "specialty_name": "$_id.specialty_name"}},
    ]

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
            "job_id": doc.get("job_id"),
            "specialty_code": doc.get("specialty_code"),
            "specialty_name": doc.get("specialty_name"),
        })

    if cleaned_data_list:
        import_job_specialty_to_mysql(cleaned_data_list)

