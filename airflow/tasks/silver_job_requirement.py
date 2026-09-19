import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection


# ===== job_requirement =====
def import_requirement_to_mysql(cleaned_data_list):
    sql = """
        INSERT IGNORE INTO job_requirement (
            job_id, requirement_type, requirement_value
        ) VALUES (
            %(job_id)s, %(requirement_type)s, %(requirement_value)s
        );
    """
    run_mysql_upsert(sql, cleaned_data_list)


def silver_job_requirement():
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_job_requirement")
    today = datetime.now().date()
    start_time = datetime.combine(today - timedelta(days=1), time(23, 55, 0))
    end_time = datetime.combine(today + timedelta(days=1), time(0, 0, 0))

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
        {"$project": {
            "job_id": {
                "$let": {
                    "vars": {"urlParts": {"$split": ["$header.analysisUrl", "/"]}},
                    "in": {"$arrayElemAt": ["$$urlParts", -1]},
                }
            },
            "condition.major": 1,
            "condition.driverLicense": 1,
            "condition.acceptRole.role": 1,
            "jobDetail.workType": 1,
            "condition.certificate": 1,
        }},
        {"$facet": {
            "major": [{"$unwind": "$condition.major"}, {"$project": {"_id": 0, "job_id": 1, "requirement_type": "MAJOR", "requirement_value": "$condition.major"}}],
            "driver_license": [{"$unwind": "$condition.driverLicense"}, {"$project": {"_id": 0, "job_id": 1, "requirement_type": "DRIVER_LICENSE", "requirement_value": "$condition.driverLicense"}}],
            "accept_role": [{"$unwind": "$condition.acceptRole.role"}, {"$project": {"_id": 0, "job_id": 1, "requirement_type": "ACCEPT_ROLE", "requirement_value": "$condition.acceptRole.role.description"}}],
            "work_type": [{"$unwind": "$jobDetail.workType"}, {"$project": {"_id": 0, "job_id": 1, "requirement_type": "WORK_TYPE", "requirement_value": "$jobDetail.workType"}}],
            "certificate": [{"$unwind": "$condition.certificate"}, {"$project": {"_id": 0, "job_id": 1, "requirement_type": "CERTIFICATE", "requirement_value": "$condition.certificate.description"}}],
        }},
        {"$project": {"requirements": {"$concatArrays": ["$major", "$driver_license", "$accept_role", "$work_type", "$certificate"]}}},
        {"$unwind": "$requirements"},
        {"$replaceRoot": {"newRoot": "$requirements"}},
        {"$group": {"_id": {"job_id": "$job_id", "requirement_type": "$requirement_type", "requirement_value": "$requirement_value"}}},
        {"$project": {"_id": 0, "job_id": "$_id.job_id", "requirement_type": "$_id.requirement_type", "requirement_value": "$_id.requirement_value"}},
    ]

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
            "job_id": doc.get("job_id"),
            "requirement_type": doc.get("requirement_type"),
            "requirement_value": doc.get("requirement_value"),
        })

    if cleaned_data_list:
        import_requirement_to_mysql(cleaned_data_list)

