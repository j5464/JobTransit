"""專案與敏感原始資料的可攜式路徑規則。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def project_root() -> Path:
    """由套件位置反推專案根目錄，不綁定特定使用者名稱。"""
    return Path(__file__).resolve().parents[2]


def default_raw_root(
    *,
    local_app_data: str | None = None,
) -> Path:
    """將 Raw snapshot 放在 Windows 本機資料夾，避免隨 OneDrive 同步。

    `local_app_data` 是方便單元測試注入的參數；一般執行時會自動讀取
    Windows 的 LOCALAPPDATA。若其他作業系統沒有此變數，才退回系統暫存區。
    """
    local_base = local_app_data or os.environ.get("LOCALAPPDATA")
    if local_base:
        return Path(local_base) / "job-crawler-104" / "raw"
    return Path(tempfile.gettempdir()) / "job-crawler-104" / "raw"


def default_data_root(*, configured: str | None = None) -> Path:
    """回傳 latest／run exports 的大型資料根目錄。

    CLI 可用 ``JOB104_DATA_ROOT`` 或 ``--data-root`` 覆寫；Raw 歷史仍使用
    :func:`default_raw_root`，不與可覆寫的 latest 資料混在一起。
    """

    selected = configured or os.environ.get("JOB104_DATA_ROOT")
    if selected:
        return Path(selected)
    if os.name == "nt":
        return Path(r"C:\JobData\job-crawler-104")
    return Path.home() / ".local" / "share" / "job-crawler-104"


def latest_run_jsonl(data_root: Path) -> Path | None:
    """依最後修改時間選出最近寫入／續跑的 run JSONL。"""

    candidates = list((data_root / "runs").glob("*/jobs_*.jsonl"))
    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.parent.name, path.name),
        default=None,
    )


def display_path(path: Path, *, root: Path) -> str:
    """專案內用相對 POSIX 路徑，專案外則保留可追溯的絕對路徑。"""
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError:
        return str(resolved)


def raw_locator(path: Path, *, raw_root: Path) -> str:
    """建立不含 Windows 帳號名稱、但可由 Raw root 解回的定位字串。"""
    resolved = path.resolve()
    resolved_root = raw_root.resolve()
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise ValueError(f"Raw 檔案不在設定的 Raw root 內：{resolved}") from error
    return f"raw-root://{relative}" if relative != "." else "raw-root://"
