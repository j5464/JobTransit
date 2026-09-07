import pymongo

# 1. 連接 MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["tkr102"]  # 您的資料庫名稱
collection_details = db["job_details"]

# 2. 執行讀取 (純查詢 Projection，只取 job_id 與 header.custName)
# 第二個參數代表：1 為要顯示該欄位，0 為不顯示
cursor = collection_details.find(
    {}, {"_id": 0, "job_id": 1, "header.custName": 1}
)

# 3. 在 Python 記憶體中整理並匹配資料
matched_jobs = []

for doc in cursor:
    # 提取 job_id (若沒有該欄位則給空字串)
    job_id = doc.get("job_id", "")

    # 提取公司名稱 (因為 custName 藏在 header 字典裡面)
    header_info = doc.get("header", {})
    cust_name = (
        header_info.get("custName", "未公開公司")
        if isinstance(header_info, dict)
        else "未公開公司"
    )

    # 組合匹配資料
    job_item = {"job_id": job_id, "cust_name": cust_name}
    matched_jobs.append(job_item)

    # 終端機即時印出測試
    print(f"Job ID: {job_id} | 公司名稱: {cust_name}")

# 4. 驗證總筆數 (此時 matched_jobs 存在 Python 記憶體中，MongoDB 完全沒變)
print(f"\n成功讀取並匹配 {len(matched_jobs)} 筆職缺與公司資料")

# import pymongo

# # 1. 連接 MongoDB
# client = pymongo.MongoClient("mongodb://localhost:27017/")
# db = client["tkr102"]

# # 指定來源表與目標新表
# collection_details = db["job_details"]
# collection_summary = db["job_company_summary"]  # 新的 Collection 名稱

# # 2. 撈取資料 (Projection 只取所需欄位)
# cursor = collection_details.find(
#     {}, {"_id": 0, "job_id": 1, "header.custName": 1}
# )

# summary_docs = []

# for doc in cursor:
#     job_id = doc.get("job_id", "")
#     header_info = doc.get("header", {})

#     # 取出 104 API 的公司名稱
#     company_name = (
#         header_info.get("custName", "")
#         if isinstance(header_info, dict)
#         else ""
#     )

#     if job_id:
#         # 欄位名稱依您的要求設為 job_id 與 company_name
#         summary_docs.append(
#             {
#                 "_id": job_id,  # 指定 job_id 為 Primary Key 防重複
#                 "company_name": company_name,  # 欄位名稱 2: company_name
#             }
#         )

# # 3. 寫入全新的 Collection
# if summary_docs:
#     collection_summary.delete_many({})  # 清空舊資料，確保每次執行都是最新資料
#     collection_summary.insert_many(summary_docs)  # 寫入新資料
#     print(
#         f"成功將 {len(summary_docs)} 筆資料寫入"
#         " job_company_summaryCollection"
#     )