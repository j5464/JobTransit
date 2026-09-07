import pymongo

# 1. 連接 MongoDB (請確認與您 json_to_mongo.py 內的設定一致)
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["tkr102"]  # 您的資料庫名稱

collection_job_ids = db["job_ids"]
collection_job_details = db["job_details"]


def match_and_bind_job_ids():
    # 取出所有 job_ids 資料
    job_ids_list = list(collection_job_ids.find({}))
    # 取出所有 job_details 資料
    job_details_list = list(collection_job_details.find({}))

    print(f"job_ids 筆數: {len(job_ids_list)}")
    print(f"job_details 筆數: {len(job_details_list)}")

    updated_count = 0

    # 按照順序一比一匹配更新
    limit = min(len(job_ids_list), len(job_details_list))
    for i in range(limit):
        target_job_id = job_ids_list[i]["job_id"]  # 取得如 "92dx8"
        detail_doc_id = job_details_list[i]["_id"]  # 取得 MongoDB 的 ObjectId

        # 寫入 job_id 欄位到 job_details collection
        collection_job_details.update_one(
            {"_id": detail_doc_id}, {"$set": {"job_id": target_job_id}}
        )
        updated_count += 1

    print(
        f"成功完成比對更新！已為 {updated_count} 筆 job_details 補上"
        " job_id 欄位。"
    )


if __name__ == "__main__":
    match_and_bind_job_ids()