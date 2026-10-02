import os
import re
from datetime import datetime, timedelta, time
from pymongo import UpdateOne
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


def silver_job_specialty(filter_by_date: bool = True):
    collection = get_mongodb_collection()
    if collection is None:
        return

    print("開始處理 silver_job_specialty")
    today = datetime.combine(datetime.now().date(), time.min)
    start_time = (today - timedelta(days=1)).replace(hour=23, minute=55)
    end_time = today + timedelta(days=1)

    # 1. 更新專長參照表
    pipeline_refer_list = [
        {"$project": {"condition": 1}},
        {"$unwind": "$condition.specialty"},
        {
            "$group": {
                "_id": "$condition.specialty.code",
                "description": {"$first": "$condition.specialty.description"},
            }
        },
        {"$merge": {"into": "specialties_refer_list", "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]
    collection.aggregate(pipeline_refer_list)

    # 💡 效能優化 1：使用 bulk_write 批量更新參照表，並載入 Python 記憶體
    refer_coll = collection.database["specialties_refer_list"]
    refer_specialties = []
    bulk_ops = []

    for doc in refer_coll.find():
        code = doc.get("_id")
        desc = doc.get("description", "")
        if desc and code:
            escaped_desc = re.escape(desc)
            # 前後加上「非英數字元或字串開結尾」限制，防止誤抓（例如 A+）
            pattern_str = f"(?:^|[^a-zA-Z0-9]){escaped_desc}(?:$|[^a-zA-Z0-9])"
            
            bulk_ops.append(
                UpdateOne({"_id": code}, {"$set": {"escaped_regex": pattern_str}})
            )
            # 預編譯正則，提升 Python 端比對效能
            refer_specialties.append({
                "code": code,
                "name": desc,
                "compiled_regex": re.compile(pattern_str, re.IGNORECASE)
            })

    if bulk_ops:
        refer_coll.bulk_write(bulk_ops)

    # 2. 構建輕量化的 MongoDB 提取管道（不執行耗時的 $lookup）
    pipeline = [
        {"$match": {"switch": "on"}},]
    # 依據版本參數控制是否加入時間過濾區塊
    if filter_by_date:
        pipeline.append({
            "$match": {
                "ingestion_timestamp": {
                    "$gte": start_time,  # 昨天 23:55:00
                    "$lt": end_time,  # 明天 00:00:00
                }
            }
        })
    # 串接剩餘的 Pipeline 階段
    pipeline.extend([
        {"$sort": {"ingestion_timestamp": -1}},
        {"$unwind": "$condition"},
        {
            "$project": {
                "_id": 0,
                "analysisUrl": "$header.analysisUrl",
                "other_text": {"$ifNull": ["$condition.other", ""]},
                "desc_text": {"$ifNull": ["$jobDetail.jobDescription", ""]},
                "raw_specialties": {
                    "$cond": {
                        "if": {"$isArray": "$condition.specialty"},
                        "then": "$condition.specialty",
                        "else": ["$condition.specialty"],
                    }
                },
            }
        }
    ])

    # 💡 效能優化 2：在 Python 端完成高效率專長比對與去重
    cleaned_data_set = set()  # 用 set 確保不重複記錄 (job_id, specialty_code)

    for doc in collection.aggregate(pipeline, allowDiskUse=True):
        # 解析 job_id
        url = doc.get("analysisUrl", "").strip("/")
        if not url:
            continue
        job_id = url.split("/")[-1]

        # 整理結構化欄位中的專長名稱列表
        raw_specialties_objs = doc.get("raw_specialties", [])
        struct_spec_names = set()
        for item in raw_specialties_objs:
            if isinstance(item, dict) and "description" in item and item["description"]:
                struct_spec_names.add(item["description"])

        other_text = doc.get("other_text", "")
        desc_text = doc.get("desc_text", "")

        # 開始比對每一項標準專長
        for spec in refer_specialties:
            s_code = spec["code"]
            s_name = spec["name"]
            regex = spec["compiled_regex"]

            # 滿足以下任一條件即代表命中：
            # 1. 存在於結構化欄位
            # 2. 正則匹配到 other 欄位
            # 3. 正則匹配到 jobDescription 欄位
            is_matched = (
                s_name in struct_spec_names
                or bool(regex.search(other_text))
                or bool(regex.search(desc_text))
            )

            if is_matched:
                cleaned_data_set.add((job_id, s_code, s_name))

    # 轉換為 List 結構準備 Upsert 至 MySQL
    cleaned_data_list = [
        {
            "job_id": item[0],
            "specialty_code": item[1],
            "specialty_name": item[2]
        }
        for item in cleaned_data_set
    ]

    print(f"處理完成，共產出 {len(cleaned_data_list)} 筆專長資料")

    if cleaned_data_list:
        import_job_specialty_to_mysql(cleaned_data_list)

