"""Windows／VS Code 終端機的 UTF-8 輸出設定。"""

from __future__ import annotations

import sys
from typing import TextIO


def _reconfigure(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def configure_utf8_console() -> None:
    """讓繁體中文在 PowerShell、VS Code 與重導向日誌中使用 UTF-8。"""
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)

