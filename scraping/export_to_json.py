import os
import json

def save_jobs_to_json(jobs_list, output_json_path:str):
    """
    將爬取到的職缺資料清單儲存/追加至 JSON 檔案中。
    
    :param jobs_list: 包含職缺字典資料的 List
    :param output_json_path: 輸出的 JSON 檔案路徑
    """
    if not jobs_list:
        print("沒有傳入任何職缺資料，無法儲存。")
        return

    existing_data = []

    # 1. 檢查檔案是否存在，若存在則先讀取舊資料
    if os.path.exists(output_json_path):
        try:
            with open(output_json_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            print(f"警告：{output_json_path} 解析失敗或格式不正確，將重新建立檔案。")
            existing_data = []

    # 2. 將新資料合併至舊資料列表中
    existing_data.extend(jobs_list)

    # 3. 寫入 JSON 檔案 (indent=4 保持縮排格式，ensure_ascii=False 防止中文變萬國碼)
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=4)

    print(f"\n[資料處理完成]")
    print(f"成功將 {len(jobs_list)} 筆新資料寫入 JSON 檔（總計 {len(existing_data)} 筆）: {os.path.abspath(output_json_path)}")

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
    save_jobs_to_json(sample_jobs)