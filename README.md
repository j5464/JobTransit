# JobTransit
for TibaMe TKR102_G1 Project

## Airflow
Docker run指令
```
docker run -it -d `
  --name airflow3-server `
  -p 8080:8080 `
  -v "${PWD}/dags:/opt/airflow/dags" `
  -v "${PWD}/logs:/opt/airflow/logs" `
  -v "${PWD}/utils:/opt/airflow/utils" `
  -v "${PWD}/tasks:/opt/airflow/tasks" `
  -e PYTHONPATH=/opt/airflow `
  -e _PIP_ADDITIONAL_REQUIREMENTS="pymongo" `
  apache/airflow:3.0.3-python3.11 airflow standalone
```
git clone scraping
