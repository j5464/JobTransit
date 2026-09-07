import pymysql


def connectAutoClose(host, port, user, password, db):
    try:
        # 離開 with 縮排區塊時，Python 會自動關閉連線
        with pymysql.connect(
            host=host, port=port, user=user, password=password, db=db
        ) as connection:
            print("connection.open (區塊內):", connection.open)
            print("Connecting to Docker MySQL successfully!!")

        # 離開區塊後，連線已經被自動關閉了
        print("connection.open (區塊外):", connection.open)

    except Exception as e:
        print("Connection failed:", e)


def main():
    host = "127.0.0.1"
    port = 3307
    user = "root"
    password = "password"
    db = "TESTDB"

    print("--- 測試 with 自動關閉 ---")
    connectAutoClose(host, port, user, password, db)


if __name__ == "__main__":
    print("=" * 40)
    main()
    print("=" * 40)