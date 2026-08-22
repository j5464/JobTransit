"""輸出前的聯絡資訊遮罩，保留原有換行與 JSON 結構。"""

from __future__ import annotations

import re
from typing import Any


EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
TAIWAN_MOBILE_PATTERN = re.compile(
    r"(?<!\d)(?:09\d{2}|\+?886[-\s]?9\d{2})[-\s]?\d{3}[-\s]?\d{3}(?!\d)"
)
TAIWAN_LANDLINE_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"(?:02|\+?886[-\s]?2)[-\s]?\d{4}[-\s]?\d{4}"
    r"|(?:0[3-8]|\+?886[-\s]?[3-8])[-\s]?\d{3,4}[-\s]?\d{4}"
    r"|(?:037|\+?886[-\s]?37)[-\s]?\d{3}[-\s]?\d{3}"
    r"|(?:049|\+?886[-\s]?49)[-\s]?\d{3}[-\s]?\d{4}"
    r"|(?:08[29]|\+?886[-\s]?8[29])[-\s]?\d{3}[-\s]?\d{3}"
    r"|(?:08(?:26|36)|\+?886[-\s]?8(?:26|36))[-\s]?\d{2}[-\s]?\d{3}"
    r")(?!\d)"
)
SENSITIVE_KEY_PREFIXES = (
    "contact",
    "email",
    "phone",
    "mobile",
    "telephone",
    "fax",
    "recruiter",
    "hrname",
    "interaction",
    "member",
    "userapply",
    "resume",
)
SENSITIVE_KEYS = {
    "tel",
    "telno",
    "issaved",
    "isapplied",
    "isfollowed",
    "applydate",
}


def redact_contact_text(text: str) -> str:
    """遮罩明確 Email／台灣手機與市話格式，不改動其餘文字。"""
    redacted = EMAIL_PATTERN.sub("[已遮罩電子郵件]", text)
    redacted = TAIWAN_MOBILE_PATTERN.sub("[已遮罩電話]", redacted)
    return TAIWAN_LANDLINE_PATTERN.sub("[已遮罩電話]", redacted)


def _sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return normalized in SENSITIVE_KEYS or normalized.startswith(
        SENSITIVE_KEY_PREFIXES
    )


def redact_nested(value: Any) -> Any:
    """遞迴遮罩文字並排除明確聯絡／個人互動鍵。"""
    if isinstance(value, str):
        return redact_contact_text(value)
    if isinstance(value, dict):
        return {
            key: redact_nested(item)
            for key, item in value.items()
            if not _sensitive_key(key)
        }
    if isinstance(value, list):
        return [redact_nested(item) for item in value]
    return value
