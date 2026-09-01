import json
from conn_to_mongoDB import conn_to_mongodb


#(id)取出爬過的id到SET中做後續比對
def get_existing_job_ids():
    collection = conn_to_mongodb('job_ids')
    if collection is None:
        return set()

    #只取id做比對
    results = collection.find({}, {"job_id": 1, "_id": 0})
    return {item['job_id'] for item in results}


#(id)將新的id寫入mongo
def insert_new_job_ids(jobs_list):
    if not jobs_list:
        return
        
    collection = conn_to_mongodb('job_ids')
    if collection is not None:
        collection.insert_many(jobs_list)

#(detail)確認status為pending再爬取
def get_pending_jobs():
    collection = conn_to_mongodb('job_ids')
    if collection is None:
        return []
    
    #MongoDB直接幫我們篩選
    return list(collection.find({"status": "PENDING"}))

#爬取成功後修改狀態為complete
def update_job_status_to_complete(job_id):
    collection = conn_to_mongodb('job_ids')
    if collection is not None:
        # update_one 第一個參數是查詢條件，第二個參數是 $set 更新內容
        collection.update_one(
            {"job_id": job_id}, 
            {"$set": {"status": "COMPLETED"}}
        )

#將爬取到的detail寫入SET
def insert_job_detail(detail_data):
    collection = conn_to_mongodb('job_details')
    if collection is not None:
        collection.insert_one(detail_data)



#以下先不用
def insert_data_to_mongo(data):
     collection = conn_to_mongodb()

    #確認回傳值
    if collection is None:
        print("無法取得資料庫連線，寫入中止。")
        return

    try:
        #依資料型態(array、object)，決定insert_many還是 insert_one
        if isinstance(data, list):
            if len(data) > 0:
                result = collection.insert_many(data)
                print(f"成功批次匯入 {len(result.inserted_ids)} 筆資料！")
            else:
                print("資料列表為空，沒有寫入任何資料。")

        elif isinstance(data, dict):
            result = collection.insert_one(data)
            #ID可改為job_id
            print(f"成功匯入單筆資料，(MongoDB生成的)ID為: {result.inserted_id}")

        else:
            print("寫入失敗：不支援的資料格式。必須是Dict或List。")

    except Exception as e:
        print(f"寫入 MongoDB 時發生例外錯誤: {e}")


#直接讀取json檔
#def insert_json_file_to_mongo(filepath):


if __name__ == "__main__":
    print("--- 測試模式 ---")

    #針對insert_data_to_mongo
    sample_data = [
        {"item": "蘋果", "price": 30, "source": "超市A"},
        {"item": "香蕉", "price": 20, "source": "超市A"}
    ]
    print("測試變數直接寫入：")
    insert_data_to_mongo(sample_data)

    #針對insert_json_file_to_mongo
    #print("\n測試讀取檔案寫入：")
    #insert_json_file_to_mongo("my_spider_result.json")