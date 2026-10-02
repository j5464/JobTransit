import os
import re
from datetime import datetime, timedelta, time
from pymongo import UpdateOne
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


def silver_job_skill(filter_by_date: bool = True):
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

    # 💡 效能優化 1：使用 bulk_write 批量更新參照表
    skill_refer_coll = collection.database["skill_refer_list"]
    refer_skills = []  # 順便載入 Python 記憶體供後續比對
    bulk_ops = []

    for doc in skill_refer_coll.find():
        code = doc.get("_id")
        desc = doc.get("description", "")
        if desc and code:
            escaped_desc = re.escape(desc)
            # 精準邊界：防止 C++、A+ 誤抓其他英文單字（如 team 中的 a）
            pattern_str = f"(?:^|[^a-zA-Z0-9]){escaped_desc}(?:$|[^a-zA-Z0-9])"
            
            bulk_ops.append(
                UpdateOne({"_id": code}, {"$set": {"escaped_regex": pattern_str}})
            )
            # 預編譯正則，大幅提升 Python 端的比對速度
            refer_skills.append({
                "code": code,
                "name": desc,
                "compiled_regex": re.compile(pattern_str, re.IGNORECASE)
            })

    if bulk_ops:
        skill_refer_coll.bulk_write(bulk_ops)

    # 2. 構建輕量化的 MongoDB 提取管道（不跑耗時的 $lookup）
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
                "raw_skills": {
                    "$cond": {
                        "if": {"$isArray": "$condition.skill"},
                        "then": "$condition.skill",
                        "else": ["$condition.skill"],
                    }
                },
            }
        }
    ])

    # 💡 效能優化 2：在 Python 端高效率完成技能匹配與去重
    cleaned_data_set = set()  # 用 set 避免重複的 (job_id, skill_code)

    for doc in collection.aggregate(pipeline, allowDiskUse=True):
        # 解析 job_id
        url = doc.get("analysisUrl", "").strip("/")
        if not url:
            continue
        job_id = url.split("/")[-1]

        # 整理結構化欄位中的技能名稱列表 (修復原本的 $raw_skills.description)
        raw_skills_objs = doc.get("raw_skills", [])
        struct_skill_names = set()
        for item in raw_skills_objs:
            if isinstance(item, dict) and "description" in item and item["description"]:
                struct_skill_names.add(item["description"])

        other_text = doc.get("other_text", "")
        desc_text = doc.get("desc_text", "")

        # 開始比對每一項標準技能
        for skill in refer_skills:
            s_code = skill["code"]
            s_name = skill["name"]
            regex = skill["compiled_regex"]

            # 三條件滿足其一即可：
            # 1. 存在於結構化欄位
            # 2. 匹配 other 說明欄位
            # 3. 匹配 jobDescription 欄位
            is_matched = (
                s_name in struct_skill_names
                or bool(regex.search(other_text))
                or bool(regex.search(desc_text))
            )

            if is_matched:
                cleaned_data_set.add((job_id, s_code, s_name))

    # 轉回 List 結構準備寫入 MySQL
    cleaned_data_list = [
        {
            "job_id": item[0],
            "skill_code": item[1],
            "skill_description": item[2]
        }
        for item in cleaned_data_set
    ]

    print(f"處理完成，共產出 {len(cleaned_data_list)} 筆技能資料")

    if cleaned_data_list:
        import_job_skill_to_mysql(cleaned_data_list)

