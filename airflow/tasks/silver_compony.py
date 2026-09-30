import os


from datetime import datetime, timedelta, time
from utils.run_mysql_upsert import run_mysql_upsert,get_mongodb_collection


# ===== company =====
def import_company_to_mysql(cleaned_data_list):
    sql = """
        INSERT INTO company (
            cust_no, cust_name, cust_url, industry_name, industry_no,
            employees_count, employees_raw, _silver_updated_at, _source_batch_id
        ) VALUES (
            %(cust_no)s, %(cust_name)s, %(cust_url)s, %(industry_name)s, %(industry_no)s,
            %(employees_count)s, %(employees_raw)s, %(_silver_updated_at)s, %(_source_batch_id)s
        )
        AS new
        ON DUPLICATE KEY UPDATE
            cust_name = new.cust_name,
            cust_url = new.cust_url,
            industry_name = new.industry_name,
            industry_no = new.industry_no,
            employees_count = new.employees_count,
            employees_raw = new.employees_raw,
            _silver_updated_at = new._silver_updated_at,
            _source_batch_id = new._source_batch_id;
    """
    run_mysql_upsert(sql, cleaned_data_list)


def silver_company_mongodb_to_mysql(filter_by_date: bool = True):
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_company")
    today = datetime.combine(datetime.now().date(), time.min)
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)
    end_time = today + timedelta(days=1)

    pipeline = [
        {"$match": {"switch": "on"}},]
    # 依據版本參數控制是否加入時間過濾區塊
    if filter_by_date:
        pipeline.append({
            "$match": {
                "ingestion_timestamp": {
                    "$gte": start_time,
                    "$lt": end_time,
                }
            }
        })
    pipeline.extend([
        {"$sort": {"batch_id": -1}},
        {
            "$group": {
                "_id": "$custNo",
                "cust_url": {"$first": "$header.custUrl"},
                "cust_name": {"$first": "$header.custName"},
                "industry_name": {"$first": "$industry"},
                "industry_no": {"$first": "$industryNo"},
                "employees_raw": {"$first": "$employees"},
                "source_batch_id": {"$first": "$batch_id"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "cust_no": "$_id",
                "cust_name": 1,
                "cust_url": 1,
                "industry_name": 1,
                "industry_no": 1,
                "employees_raw": 1,
                "employees_count": {
                    "$let": {
                        "vars": {
                            "matches": {
                                "$regexFindAll": {
                                    "input": {"$ifNull": ["$employees_raw", ""]},
                                    "regex": "\\d+",
                                }
                            }
                        },
                        "in": {
                            "$cond": {
                                "if": {"$gt": [{"$size": "$$matches"}, 0]},
                                "then": {"$toInt": {"$arrayElemAt": ["$$matches.match", 0]}},
                                "else": None,
                            }
                        },
                    }
                },
                "_silver_updated_at": "$$NOW",
                "_source_batch_id": 1,
            }
        },
    ])

    cleaned_data_list = []
    for doc in collection.aggregate(pipeline):
        cleaned_data_list.append({
            "cust_no": doc.get("cust_no"),
            "cust_name": doc.get("cust_name"),
            "cust_url": doc.get("cust_url"),
            "industry_name": doc.get("industry_name"),
            "industry_no": doc.get("industry_no"),
            "employees_count": doc.get("employees_count"),
            "employees_raw": doc.get("employees_raw"),
            "_silver_updated_at": datetime.now(),
            "_source_batch_id": doc.get("source_batch_id"),
        })

    if cleaned_data_list:
        import_company_to_mysql(cleaned_data_list)