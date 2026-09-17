import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection


# ===== job_skill =====
def import_job_skill_to_mysql(cleaned_data_list):
    sql = """
        INSERT INTO job_skill (
            job_id, skill_code, skill_description
        ) VALUES (
            %(job_id)s, %(skill_code)s, %(skill_description)s
        )
        AS new
        ON DUPLICATE KEY UPDATE
            skill_description = new.skill_description;
    """
    run_mysql_upsert(sql, cleaned_data_list)


def silver_job_skill():
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_job_skill")
    today = datetime.combine(datetime.now().date(), time.min)
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)
    end_time = today + timedelta(days=1)
    
    # 這裡保留原本 skill_refer_list 邏輯
    pipeline_refer_list = [
        {"$project": {"condition": 1}},
        {"$unwind": "$condition.skill"},
        {"$group": {"_id": "$condition.skill.code", "description": {"$first": "$condition.skill.description"}}},
        {"$merge": {"into": "skill_refer_list", "whenMatched": "replace", "whenNotMatched": "insert"}},
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
            "raw_skills": {"$cond": {"if": {"$isArray": "$condition.skill"}, "then": "$condition.skill", "else": ["$condition.skill"]}},
        }},
        {
            "$lookup": {
                "from": "skill_refer_list",
                "let": {
                    "other_text": {"$ifNull": ["$condition.other", ""]},
                    "desc_text": {"$ifNull": ["$jobDetail.jobDescription", ""]},
                    "spec_names": {"$ifNull": ["$raw_skills.description", []]},
                },
                "pipeline": [
                    {"$match": {"$expr": {"$or": [
                        {"$in": ["$description", "$$spec_names"]},
                        {"$regexMatch": {"input": "$$other_text", "regex": "$description", "options": "i"}},
                        {"$regexMatch": {"input": "$$desc_text", "regex": "$description", "options": "i"}},
                    ]}}},
                    {"$project": {"_id": 0, "skill_code": "$_id", "skill_description": "$description"}},
                ],
                "as": "matched_tools",
            }
        },
        {"$unwind": "$matched_tools"},
        {"$project": {"_id": 0, "job_id": "$parsed_job_id", "skill_code": "$matched_tools.skill_code", "skill_description": "$matched_tools.skill_description"}},
        {"$group": {"_id": {"job_id": "$job_id", "skill_code": "$skill_code", "skill_description": "$skill_description"}}},
        {"$project": {"_id": 0, "job_id": "$_id.job_id", "skill_code": "$_id.skill_code", "skill_description": "$_id.skill_description"}},
    ]

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
            "job_id": doc.get("job_id"),
            "skill_code": doc.get("skill_code"),
            "skill_description": doc.get("skill_description"),
        })

    if cleaned_data_list:
        import_job_skill_to_mysql(cleaned_data_list)

