from pendulum import today
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from urllib.parse import urlparse
from datetime import datetime, timedelta

#建立與 MongoDB 的連線，並回傳指定的 Collection
def conn_to_mongodb(conn_ip:str,db_name: str,collection_name: str):
    """
    皆要使用"雙引號"或'單引號'包住字串，參數說明:\n
    *conn_ip*:要連線的ip\n
    *db_name*: 資料庫名稱\n
    *collection_name*: 集合表名稱\n
    """
    connection = f"mongodb://{conn_ip}:27017/"
    try:

        #使用URI連結
        client = MongoClient(connection)
        client.admin.command('ping')
        print("成功連線到 MongoDB!")

        #使用(創建)資料庫
        db = client[db_name]

        #使用(創建)文檔集
        collection = db[collection_name]

        return collection

    except ConnectionFailure as e:
        print(f"連線失敗，請確認 MongoDB 伺服器是否有啟動。錯誤訊息: {e}")
        return None

def tool_list():
    # 連接到 MongoDB 並獲取指定的 collection
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return []

    # 從 MongoDB 取出資料 (使用 projection 僅讀取需要的欄位以優化效能)
    cursor = collection.find({}, {"condition.specialty.description": 1})

    tools_set = set()

    # 3. 逐筆取出並解開 List 結構
    for doc in cursor:
        condition = doc.get("condition", {})
        # specialty 是一個 List: [{"description": "iOS"}, {"description": "Android"}, ...]
        specialty_list = condition.get("specialty", [])
        
        # 確保 specialty 是 List 才能進行迴圈
        if isinstance(specialty_list, list):
            for item in specialty_list:
                # item 是 Dict: {"description": "iOS"}
                if isinstance(item, dict):
                    description = item.get("description", "")
                    if description:
                        tools_set.add(description.strip())

    print(f"解析完成，不重複的工具共 {len(tools_set)} 個：{tools_set}")

    # 4. 寫入 MongoDB 的 job_tools 集合
    tools_collection = conn_to_mongodb("localhost", "test", "job_tools")
    if tools_collection is not None and tools_set:
        for tool in tools_set:
            # 使用 upsert 來避免重複插入（若存在則更新，若不存在則新增）
            # _id 會由 MongoDB 自動生成
            tools_collection.update_one(
                {"description": tool},
                {"$setOnInsert": {"description": tool}},  # 使用 $setOnInsert 可以避免重複發送寫入請求時洗掉其他欄位
                upsert=True
            )
        print(f"成功將 {len(tools_set)} 筆不重複資料寫入/更新至 job_tools 集合！")

def data_clear():
    # 連接到 MongoDB 並獲取指定的 collection
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return
    # 1. 從 MongoDB 取出資料 (使用 projection 僅讀取需要的欄位以優化效能)
    cursor = collection.find({}, {
        "industry": 1,
        "jobDetail": 1,
        "condition": 1
    })

    cleaned_data_list = []

    # 2. 逐筆取出並清洗/組合欄位
    for doc in cursor:
        # 使用 .get() 搭配預設值，避免 KeyError 導致程式中斷
        job_detail = doc.get("jobDetail", {})
        #產業類別 > industry
        industry_type = doc.get("industry", "")
        # 職缺內容詳情
        job_description = job_detail.get("jobDescription", "").strip()
        # 招募人數
        vacancies= job_detail.get("needEmp", 0)
        # 工作性質(全職.兼職)
        employment_type= job_detail.get("jobType", "")
        # 工作區域
        location= job_detail.get("addressArea", "")

        # tool = condition.get("specialty", "")  #condition.other #jobDetail.jobDescription
        cleaned_item = {
            "industry": industry_type,
            "job_description": job_description,
            "vacancies": vacancies,
            "employment_type": employment_type,
            "location": location,
        }
        
        cleaned_data_list.append(cleaned_item)

    # 把 cleaned_data_list 寫入 MongoDB 的 job_details_cleaned 集合
    cleaned_collection = conn_to_mongodb("localhost", "test", "job_details_cleaned")
    if cleaned_collection is not None:
        #直接將 cleaned_item 寫入 MongoDB，使用 insert_many 批次寫入
        if cleaned_data_list:
            cleaned_collection.insert_many(cleaned_data_list)
        print(f"成功將 {len(cleaned_data_list)} 筆資料寫入至 job_details_cleaned 集合！")

def data_clear_tool():
    # 連接到 MongoDB 並獲取指定的 collection
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return
    # 1. 從 MongoDB 取出資料 (使用 projection 僅讀取需要的欄位以優化效能)
    cursor = collection.find({}, {
        "header.analysisUrl": 1,
        "jobDetail": 1,
        "condition": 1
    })

    cleaned_data_list_tools = []

    # 2. 逐筆取出並清洗/組合欄位
    for doc in cursor:
        # 使用 .get() 搭配預設值，避免 KeyError 導致程式中斷
        job_detail = doc.get("jobDetail", {})
        condition = doc.get("condition", {})
        header = doc.get("header", {})

        # 從 "analysisUrl" 中提取 job_id，使用 urlparse 準確取出
        # https://www.104.com.tw/jobs/apply/analysis/95hg1，取出最後一段 "95hg1" 作為 job_id
        analysis_url = header.get("analysisUrl", "")
        if analysis_url:
            path = urlparse(analysis_url).path.strip().rstrip("/")
            job_id = path.split("/")[-1]  # 取出最後一段作為 job_id

        # 擅長工具: condition.specialty.description + condition.other 中對應 job_tools 的 tool + jobDetail.jobDescription中對應 job_tools 的 tool 欄位
        tool = []
        # 從 specialty 裡添加進 tool
        specialty = condition.get("specialty", [])
        if isinstance(specialty, list):
            for specialty_item in specialty:
                if isinstance(specialty_item, dict):
                    description = specialty_item.get("description", "").strip()
                    if description:
                        tool.append(description)
        # 再從 other 裡確認是否有與 job_tools 對應的 tool，新增該 tool[]，若與重複則不添加進tool[]
        other = condition.get("other", "")
        if other:
            # 連接到 job_tools 集合
            tools_collection = conn_to_mongodb("localhost", "test", "job_tools")
            if tools_collection is not None:
                # 查詢 other 是否有任何文字與 job_tools 集合中的 tool 是否有對應
                # 若有 對應，則將該 tool 加入 tool[]，並且相同tool不要重複添加
                # 這裡使用正規表達式來模糊匹配，避免大小寫或部分文字不一致的問題
                for tool_doc in tools_collection.find({}, {"description": 1}):
                    tool_description = tool_doc.get("description", "").strip()
                    if tool_description.lower() in other.lower():
                        if not any(
                            existing_tool.casefold() == tool_description.casefold()
                            for existing_tool in tool
                        ):
                            tool.append(tool_description)

        # 再從 jobDetail.jobDescription 裡確認是否有與 job_tools 對應的 tool，新增該 tool[]，若與重複則不添加進tool[]
        job_description = job_detail.get("jobDescription", "")
        if job_description:
            # 連接到 job_tools 集合
            tools_collection = conn_to_mongodb("localhost", "test", "job_tools")
            if tools_collection is not None:
                # 查詢 jobDescription 是否有任何文字與 job_tools 集合中的 tool 是否有對應
                # 若有 對應，則將該 tool 加入 tool[]，並且相同tool不要重複添加
                # 這裡使用正規表達式來模糊匹配，避免大小寫或部分文字不一致的問題
                for tool_doc in tools_collection.find({}, {"description": 1}):
                    tool_description = tool_doc.get("description", "").strip()
                    if tool_description.lower() in job_description.lower():
                        if not any(
                            existing_tool.casefold() == tool_description.casefold()
                            for existing_tool in tool
                        ):
                            tool.append(tool_description)

        cleaned_item_tools = {"job_id": job_id, "tools": tool}
        cleaned_data_list_tools.append(cleaned_item_tools)

    # 把 cleaned_data_list_tools 寫入 MongoDB 的 job_tools_detail 集合
    tools_detail_collection = conn_to_mongodb("localhost", "test", "job_tools_detail")
    if tools_detail_collection is not None:
        for item in cleaned_data_list_tools:
            job_id = item.get("job_id", "")
            if job_id:
                # 使用 upsert 來避免重複插入（若存在則更新，若不存在則新增）
                tools_detail_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {"tools": item.get("tools", [])}},
                    upsert=True
                )
        print(f"成功將 {len(cleaned_data_list_tools)} 筆不重複資料寫入/更新至 job_tools_detail 集合！")

def data_clear_daily():
    # 連接到 MongoDB 並獲取指定的 collection
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return
    # 1. 從 MongoDB 取出資料 (使用 projection 僅讀取需要的欄位以優化效能)
    # 只撈出 ingestion_timestamp = 當天的資料
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    cursor = collection.find({"ingestion_timestamp": {"$gte": today,"$lt": tomorrow,}}, {
        "industry": 1,
        "jobDetail": 1,
        "condition": 1,
        "ingestion_timestamp": 1
    })

    cleaned_data_list = []

    # 2. 逐筆取出並清洗/組合欄位
    for doc in cursor:
        # 使用 .get() 搭配預設值，避免 KeyError 導致程式中斷
        job_detail = doc.get("jobDetail", {})
        #產業類別 > industry
        industry_type = doc.get("industry", "")
        # 職缺內容詳情
        job_description = job_detail.get("jobDescription", "").strip()
        # 招募人數
        vacancies= job_detail.get("needEmp", 0)
        # 工作性質(全職.兼職)
        employment_type= job_detail.get("jobType", "")
        # 工作區域
        location= job_detail.get("addressArea", "")

        # tool = condition.get("specialty", "")  #condition.other #jobDetail.jobDescription
        cleaned_item = {
            "industry": industry_type,
            "job_description": job_description,
            "vacancies": vacancies,
            "employment_type": employment_type,
            "location": location,
        }
        
        cleaned_data_list.append(cleaned_item)

    # 把 cleaned_data_list 寫入 MongoDB 的 job_details_cleaned 集合
    cleaned_collection = conn_to_mongodb("localhost", "test", "job_details_cleaned")
    if cleaned_collection is not None:
        #直接將 cleaned_item 寫入 MongoDB，使用 insert_many 批次寫入
        if cleaned_data_list:
            cleaned_collection.insert_many(cleaned_data_list)
        print(f"成功將 {len(cleaned_data_list)} 筆資料寫入至 job_details_cleaned 集合！")

tool_list()
data_clear_tool()
data_clear()
data_clear_daily()