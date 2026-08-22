"""專案內使用的明確例外類型。"""


class Crawler104Error(RuntimeError):
    """所有 104 爬蟲錯誤的共同父類別。"""


class AccessBlocked(Crawler104Error):
    """頁面要求驗證或拒絕存取；程式應停止，而不是嘗試繞過。"""


class ApiPayloadError(Crawler104Error):
    """API 回應格式與已驗證的契約不符；連續發生時應停止。"""


class JobUnavailable(Crawler104Error):
    """單一職缺已關閉或不存在；可略過並繼續處理其他候選。"""


class JobPageParseError(Crawler104Error):
    """單一職缺缺少 ID、職稱、公司或工作內容等必要欄位。"""
