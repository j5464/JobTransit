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

    # 1. 從 MongoDB 取出資料 (使用 MongoDB 的聚合管道來展開 specialty 陣列並去重)
    pipeline = [
        {"$project": {"condition": 1}},
        {"$unwind": "$condition.specialty"},
        {"$group": {
                "_id": "$condition.specialty.code",
                "description": {"$first": "$condition.specialty.description"},
            }
        },
    ]

    cursor = collection.aggregate(pipeline)

    # 2. 將 cursor 寫入 MongoDB 的 job_tools 集合
    tools_collection = conn_to_mongodb("localhost", "test", "job_tools")
    tools_collection.insert_many(cursor)
    print(f"已成功轉換")
    
def data_clear():
    # 連接到 MongoDB 並獲取指定的 collection
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return
    # 1. 從 MongoDB 取出資料 (使用 projection 僅讀取需要的欄位以優化效能)
    cursor = collection.find({}, {
        "header.analysisUrl": 1,
        "industry": 1,
        "jobDetail": 1,
        "condition": 1
    })

    cleaned_data_list = []

    # 2. 逐筆取出並清洗/組合欄位
    for doc in cursor:
        # 使用 .get() 搭配預設值，避免 KeyError 導致程式中斷
        job_detail = doc.get("jobDetail", {})
        header = doc.get("header", {})

        # 從 "analysisUrl" 中提取 job_id，使用 urlparse 準確取出
        # https://www.104.com.tw/jobs/apply/analysis/95hg1，取出最後一段 "95hg1" 作為 job_id
        analysis_url = header.get("analysisUrl", "")
        if analysis_url:
            path = urlparse(analysis_url).path.strip().rstrip("/")
            job_id = path.split("/")[-1]  # 取出最後一段作為 job_id

        #產業類別 > industry
        industry_type = doc.get("industry", "")
        # 職缺內容詳情
        job_description = job_detail.get("jobDescription", "").strip()
        # 招募人數
        vacancies= job_detail.get("needEmp", 0)
        # 工作性質(全職.兼職) # 2 = 兼職 - 長期工讀, 1= 全職
        employment_type= job_detail.get("jobType", "")
        employment_type_des = "兼職 - 長期工讀" if employment_type == 2 else "全職" if employment_type == 1 else "其他"
        # 工作區域
        location= job_detail.get("addressArea", "")

        # tool = condition.get("specialty", "")  #condition.other #jobDetail.jobDescription
        cleaned_item = {
            "job_id": job_id,
            "industry": industry_type,
            "job_description": job_description,
            "vacancies": vacancies,
            "employment_type": employment_type_des,
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

    tools_pipeline = [
    {"$unwind":"$condition"},
    {"$project":{"job_id_url":"$header.analysisUrl",
        "job_description":"$jobDetail.jobDescription",
        "specialty":"$condition.specialty",
        "other":"$condition.other"}}
    ]

    cursor = collection.aggregate(tools_pipeline)

    cleaned_data_list_tools = []

# 預先讀取 job_tools 集合以優化效能（避免在迴圈內頻繁連線與查詢）
    tools_collection = conn_to_mongodb("localhost", "test", "job_tools")
    known_tools = []
    if tools_collection is not None:
        known_tools = [
            doc.get("description", "").strip()
            for doc in tools_collection.find({}, {"description": 1})
            if doc.get("description")
        ]

    # 2. 逐筆取出並清洗/組合欄位
    for doc in cursor:
        analysis_url = doc.get("job_id_url", "")
        if not analysis_url:
            continue

        path = urlparse(analysis_url).path.strip().rstrip("/")
        job_id = path.split("/")[-1]  # 取出最後一段作為 job_id

        tool = []
        
        # 從 specialty 提取
        specialty = doc.get("specialty", [])
        specialty_items = specialty if isinstance(specialty, list) else [specialty]
        for specialty_item in specialty_items:
            if isinstance(specialty_item, dict):
                description = specialty_item.get("description", "").strip()
                if description:
                    tool.append(description)

        # 從 other 匹配工具
        other = doc.get("other", "").strip()
        if other and known_tools:
            for tool_description in known_tools:
                if tool_description.lower() in other.lower():
                    if not any(t.casefold() == tool_description.casefold() for t in tool):
                        tool.append(tool_description)

        # 從 job_description 匹配工具
        job_description = doc.get("job_description", "")
        if job_description and known_tools:
            for tool_description in known_tools:
                if tool_description.lower() in job_description.lower():
                    if not any(t.casefold() == tool_description.casefold() for t in tool):
                        tool.append(tool_description)

        # 【核心修改點 1】：將 List 展開，每一個 tool 獨立產生一筆 Dict 資料
        for single_tool in tool:
            cleaned_item_tools = {
                "job_id": job_id,
                "tools": single_tool  # 單字串型態，例如 "Java"
            }
            cleaned_data_list_tools.append(cleaned_item_tools)

    # 3. 寫入 MongoDB 的 job_tools_detail 集合
    tools_detail_collection = conn_to_mongodb("localhost", "test", "job_tools_detail")
    if tools_detail_collection is not None and cleaned_data_list_tools:
        # 【核心修改點 2】：改用複合條件 upsert，或是先清空再 insert_many
        for item in cleaned_data_list_tools:
            tools_detail_collection.update_one(
                {
                    "job_id": item["job_id"],
                    "tools": item["tools"]
                },  # 依據 job_id + tools 共同判斷是否存在
                {"$set": item},
                upsert=True  # 若不存在則建立，並由 MongoDB 自動產生全新 _id
            )
        print(f"成功將 {len(cleaned_data_list_tools)} 筆資料寫入至 job_tools_detail 集合！")

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

def data_clear_tool_in_mongodb():
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    pipeline = [
        # 1. 展開 condition 陣列
        {"$unwind": "$condition"},

        # 2. 解析 job_id，並取出原始 condition.specialty
        {
            "$addFields": {
                "parsed_job_id": {
                    "$arrayElemAt": [
                        {"$split": [{"$trim": {"input": "$header.analysisUrl", "chars": "/"}}, "/"]},
                        -1
                    ]
                },
                "raw_specialties": {
                    "$cond": {
                        "if": {"$isArray": "$condition.specialty"},
                        "then": "$condition.specialty",
                        "else": ["$condition.specialty"]
                    }
                }
            }
        },

        # 3. 關聯 job_tools：同時透過名稱完全比對（specialty）與模糊比對（other, jobDescription）
        {
            "$lookup": {
                "from": "job_tools",
                "let": {
                    "other_text": {"$ifNull": ["$condition.other", ""]},
                    "desc_text": {"$ifNull": ["$jobDetail.jobDescription", ""]},
                    "spec_names": {"$ifNull": ["$raw_specialties.description", []]}
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$or": [
                                    # 情境 A: 屬於 condition.specialty 的工具名稱
                                    {"$in": ["$description", "$$spec_names"]},
                                    # 情境 B: other 包含該工具
                                    {"$regexMatch": {"input": "$$other_text", "regex": "$description", "options": "i"}},
                                    # 情境 C: jobDescription 包含該工具
                                    {"$regexMatch": {"input": "$$desc_text", "regex": "$description", "options": "i"}}
                                ]
                            }
                        }
                    },
                    # 【核心修改點 1】：將 _id 保留並更名為 specialty_code，同時留著 description
                    {
                        "$project": {
                            "_id": 0,
                            "specialty_code": "$_id",
                            "tools": "$description"
                        }
                    }
                ],
                "as": "matched_tools"
            }
        },

        # 4. 【核心步驟】：直接將匹配到的工具物件陣列展開（unwind）
        {"$unwind": "$matched_tools"},

        # 5. 整理最終輸出欄位與結構
        {
            "$project": {
                "_id": 0,  # 讓 MongoDB 寫入時自動生成全新的 _id
                "job_id": "$parsed_job_id",
                "specialty_code": "$matched_tools.specialty_code",
                "tools": "$matched_tools.tools"
            }
        },

        # 6. 利用 $group 去重（避免同一職缺重複比對到相同工具）
        {
            "$group": {
                "_id": {
                    "job_id": "$job_id",
                    "tools": "$tools",
                    "specialty_code": "$specialty_code"
                }
            }
        },

        # 7. 還原成平坦的 Document 結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id.job_id",
                "specialty_code": "$_id.specialty_code",
                "tools": "$_id.tools"
            }
        },

        # 8. 寫入目標集合
        {
            "$out": {
                "db": "test",
                "coll": "job_tools_detail_test"
            }
        }
    ]

    collection.aggregate(pipeline)
    print("成功將包含 specialty_code 的資料轉換並寫入 job_tools_detail_test！")

def data_clear_tool_in_mongodb_daily():
    collection = conn_to_mongodb('localhost', 'test', 'job_details')
    if collection is None:
        print("無法連線到 MongoDB，請檢查伺服器狀態。")
        return

    # 計算當天半夜 00:00:00 與隔天半夜 00:00:00 的時間物件
    today_start = datetime.combine(datetime.now().date(), time.min)
    tomorrow_start = datetime.combine(datetime.now().date(), time.max)

    pipeline = [
        # 【新增】：1. 僅選取 ingestion_timestamp 為當天的資料
        {
            "$match": {
                "ingestion_timestamp": {
                    "$gte": today_start,
                    "$lte": tomorrow_start
                }
            }
        },

        # 2. 展開 condition 陣列
        {"$unwind": "$condition"},

        # 3. 解析 job_id，並取出原始 condition.specialty
        {
            "$addFields": {
                "parsed_job_id": {
                    "$arrayElemAt": [
                        {"$split": [{"$trim": {"input": "$header.analysisUrl", "chars": "/"}}, "/"]},
                        -1
                    ]
                },
                "raw_specialties": {
                    "$cond": {
                        "if": {"$isArray": "$condition.specialty"},
                        "then": "$condition.specialty",
                        "else": ["$condition.specialty"]
                    }
                }
            }
        },

        # 4. 關聯 job_tools 進行匹配
        {
            "$lookup": {
                "from": "job_tools",
                "let": {
                    "other_text": {"$ifNull": ["$condition.other", ""]},
                    "desc_text": {"$ifNull": ["$jobDetail.jobDescription", ""]},
                    "spec_names": {"$ifNull": ["$raw_specialties.description", []]}
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$or": [
                                    {"$in": ["$description", "$$spec_names"]},
                                    {"$regexMatch": {"input": "$$other_text", "regex": "$description", "options": "i"}},
                                    {"$regexMatch": {"input": "$$desc_text", "regex": "$description", "options": "i"}}
                                ]
                            }
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "specialty_code": "$_id",
                            "tools": "$description"
                        }
                    }
                ],
                "as": "matched_tools"
            }
        },

        # 5. 展開匹配到的工具物件
        {"$unwind": "$matched_tools"},

        # 6. 整理欄位
        {
            "$project": {
                "_id": 0,
                "job_id": "$parsed_job_id",
                "specialty_code": "$matched_tools.specialty_code",
                "tools": "$matched_tools.tools"
            }
        },

        # 7. 去重
        {
            "$group": {
                "_id": {
                    "job_id": "$job_id",
                    "tools": "$tools",
                    "specialty_code": "$specialty_code"
                }
            }
        },

        # 8. 還原結構
        {
            "$project": {
                "_id": 0,
                "job_id": "$_id.job_id",
                "specialty_code": "$_id.specialty_code",
                "tools": "$_id.tools"
            }
        },

        # 9. 寫入目標集合
        # 註：如果每天都要增量寫入，建議改用 $merge 避免覆蓋舊日期的資料
        {
            "$merge": {
                "into": "job_tools_detail_test",
                "on": ["job_id", "specialty_code", "tools"],
                "whenMatched": "keepExisting",
                "whenNotMatched": "insert"
            }
        }
    ]

    collection.aggregate(pipeline)
    print("成功篩選當天資料、轉換並寫入/增量至 job_tools_detail_test！")

# tool_list()
# data_clear_tool()
# data_clear()
# data_clear_daily()
data_clear_tool_in_mongodb()
data_clear_tool_in_mongodb_daily()