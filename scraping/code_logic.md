# Plan A
建立 jobcat list
jobcat list 迴圈 params 的 jobcat 
    每一個 jobcat 爬蟲所有頁面取的 job_id
    用set 存取 job_id
    匯出json(有資料庫後可以匯出到DB)
讀取 job_id 的 json檔案
階段(假設每10筆)讀取job_id 爬蟲每一個job_detail
整理成我們要的資料結構 (可以寫一個function再import進主檔案)
傳到 BD 儲存，轉成 json (或存到SQL)

# Plan B
 建立 jobcat list
 jobcat list 迴圈 params 的 jobcat 
    每一個 jobcat 爬蟲所有頁面的job_id
        每一個job_id 爬蟲 job_detail
        每爬蟲到 job_detail
        整理成我們要的資料結構 (可以寫一個function再import進主檔案)
        傳到 BD 儲存

