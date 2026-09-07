from airflow.sdk import task
from utils.conn_to_mongo import conn_to_mongodb

#(id)取出爬過的id到SET中做後續比對

def get_existing_job_ids():
    collection = conn_to_mongodb('job_ids')
    if collection is None:
        return {}

    # 取出所有欄位並轉為 key: job_id, value: item 的字典
    results = collection.find({})
    return {item['job_id']: item for item in results if 'job_id' in item}


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