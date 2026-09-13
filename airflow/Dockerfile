FROM apache/airflow:3.0.0
USER airflow
#只裝 Airflow 排程「真正會用到」的輕量級套件
RUN pip install --no-cache-dir pymongo requests beautifulsoup4 pymysql apache-airflow-providers-mysql
#未來若有任何修改，在重新啟動時要在啟動指令後方加上 --build (docker-compose up -d --build)