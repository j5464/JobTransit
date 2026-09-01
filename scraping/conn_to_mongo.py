#安裝 pymongo：python -m pip install pymongo (uv add pymongo)
#升級 pymongo：python -m pip install --upgrade pymongo

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

#建立與 MongoDB 的連線，並回傳指定的 Collection
def conn_to_mongodb(collection_name: str):
    connection = "mongodb://localhost:27017/"
    try:

        #使用URI連結
        client = MongoClient(connection)
        client.admin.command('ping')
        print("成功連線到 MongoDB!")

        #使用(創建)資料庫
        db = client['tkr102']

        #使用(創建)文檔集
        collection = db[collection_name]

        return collection

    except ConnectionFailure as e:
        print(f"連線失敗，請確認 MongoDB 伺服器是否有啟動。錯誤訊息: {e}")
        return None
