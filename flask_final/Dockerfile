# 1. 使用輕量級的 Python 基礎映像檔
FROM python:3.10-slim

# 2. 設定工作目錄
WORKDIR /app

# 3. 把網頁需要的套件清單複製進去，並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 指定放入映像檔的檔案
COPY app_2.py ./
COPY templates/ ./templates/

# 5. Flask 開發預設跑在 5000 port 但考量未來cloud run的正式版的一致性，調整成 8080 port
EXPOSE 8080

# 6. 正式容器以 Gunicorn 啟動；Cloud Run 會透過 PORT 指定連接埠；將存取及錯誤日誌送到平台可收集的位置；impoert app_2.py中的app
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --access-logfile - --error-logfile - app_2:app"]

# 建置時輸入
# docker build -t jobtransit-web:local "C:\Users\leots\OneDrive\Desktop\project\TKR102_G1\flask_final"