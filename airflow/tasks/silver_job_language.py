import os

from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection


# ===== job_language =====
def import_language_to_mysql(cleaned_data_list):
    sql = """
        INSERT INTO bridge_job_language (
            job_id, language_code, language_name,
            listening_level, speaking_level, reading_level, writing_level
        ) VALUES (
            %(job_id)s, %(language_code)s, %(language_name)s,
            %(listening_level)s, %(speaking_level)s, %(reading_level)s, %(writing_level)s
        )
        AS new
        ON DUPLICATE KEY UPDATE
            language_name = new.language_name,
            listening_level = new.listening_level,
            speaking_level = new.speaking_level,
            reading_level = new.reading_level,
            writing_level = new.writing_level;
    """
    run_mysql_upsert(sql, cleaned_data_list)


def silver_job_language():
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_job_language")
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
        {"$unwind": "$condition.language"},
        {"$unwind": "$header"},
        {"$project": {
            "job_id": {
                "$let": {
                    "vars": {"urlParts": {"$split": ["$header.analysisUrl", "/"]}},
                    "in": {"$arrayElemAt": ["$$urlParts", -1]},
                }
            },
            "language_code": "$condition.language.code",
            "language_name": "$condition.language.language",
            "listening_level": "$condition.language.ability.listening",
            "speaking_level": "$condition.language.ability.speaking",
            "reading_level": "$condition.language.ability.reading",
            "writing_level": "$condition.language.ability.writing",
        }},
        {"$group": {
            "_id": {"job_id": "$job_id", "language_code": "$language_code"},
            "language_name": {"$first": "$language_name"},
            "listening_level": {"$first": "$listening_level"},
            "speaking_level": {"$first": "$speaking_level"},
            "reading_level": {"$first": "$reading_level"},
            "writing_level": {"$first": "$writing_level"},
        }},
        {"$project": {
            "_id": 0,
            "job_id": "$_id.job_id",
            "language_code": "$_id.language_code",
            "language_name": "$language_name",
            "listening_level": "$listening_level",
            "speaking_level": "$speaking_level",
            "reading_level": "$reading_level",
            "writing_level": "$writing_level",
        }},
    ]

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
            "job_id": doc.get("job_id"),
            "language_code": doc.get("language_code"),
            "language_name": doc.get("language_name"),
            "listening_level": doc.get("listening_level"),
            "speaking_level": doc.get("speaking_level"),
            "reading_level": doc.get("reading_level"),
            "writing_level": doc.get("writing_level"),
        })

    if cleaned_data_list:
        import_language_to_mysql(cleaned_data_list)

