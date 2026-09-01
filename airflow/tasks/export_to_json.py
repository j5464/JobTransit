from airflow.sdk import task
import os
import json

@task
def save_jobs_to_json(jobs_list, output_json_path:str):
    """
    將傳入的資料（List 或 Set/Dict）完整覆寫儲存至 JSON 檔案中。
    採用原子寫入機制，確保檔案不會因突發斷線而損壞。
    
    :param jobs_list: 包含職缺字典資料的 List
    :param output_json_path: 輸出的 JSON 檔案路徑
    """
    if not jobs_list:
        print("沒有傳入任何職缺資料，無法儲存。")
        return

    if isinstance(jobs_list, set):
        data_to_save = list(jobs_list)
    else:
        data_to_save = jobs_list

    # 使用 .tmp 暫存檔寫入，避免寫入中途斷線導致原檔案損毀
    temp_path = f"{output_json_path}.tmp"


    try:
        # 1. 寫入暫存檔
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)

        # 2. 寫入成功後，覆蓋目標檔案
        if os.path.exists(temp_path):
            os.replace(temp_path, output_json_path)

        data_count = len(data_to_save) if isinstance(data_to_save, (list, set, dict)) else 1
        print(f"[ SavePoint ] 成功更新 {data_count} 筆資料至: {os.path.basename(output_json_path)}")

    except Exception as e:
        print(f"[錯誤] 儲存 JSON 檔案時發生例外: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

# 測試用
if __name__ == "__main__":
    sample_jobs = [
        {
            "職缺名稱": "Python 軟體工程師",
            "公司名稱": "測試科技股份有限公司",
            "薪資待遇": "月薪 60,000~80,000 元",
            "工作地點": "台北市信義區",
            "經歷要求": "2年以上",
            "學歷要求": "大學",
            "應徵人數": "0~5人應徵",
            "更新日期": "20260823",
            "產業類別": "網際網路相關業",
            "職缺連結": "https://www.104.com.tw/job/sample"
        }
    ]
    save_jobs_to_json(sample_jobs, "test_jobs.json")