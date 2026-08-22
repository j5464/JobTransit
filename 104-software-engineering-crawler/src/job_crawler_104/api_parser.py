"""將職缺詳情 API payload 轉換成專案的 canonical schema。

只投影明確列入允許清單的職缺欄位；API ``data`` 中的 ``contact``
不會被讀取，更不會複製到輸出記錄。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .config import (
    CANONICAL_SCHEMA_VERSION,
    EMPLOYMENT_TYPE_NAME,
    SOURCE_NAME,
    query_metadata,
)
from .errors import JobPageParseError
from .privacy import redact_contact_text


def _normalize_text(value: Any) -> str:
    """正規化 API 純量值，但保留具有意義的換行。"""
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        return ""

    text = str(value).replace("\xa0", " ").replace("\u3000", " ").replace("\r", "\n")
    lines: list[str] = []
    for line in text.split("\n"):
        normalized = re.sub(r"[\t\f\v ]+", " ", line).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def _safe_text(value: Any) -> str:
    """移除範圍內文字所夾帶的明確 Email 或手機號碼。"""
    text = _normalize_text(value)
    return redact_contact_text(text)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return []


def _description_items(value: Any) -> list[str]:
    """將 API 的字串／物件陣列投影成穩定的顯示名稱。"""
    output: list[str] = []
    seen: set[str] = set()
    for item in _sequence(value):
        if isinstance(item, Mapping):
            text = _safe_text(
                item.get("description") or item.get("name") or item.get("label")
            )
        else:
            text = _safe_text(item)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _language_items(value: Any) -> list[str]:
    """每組語言與程度保留為一個 JSON 陣列元素。"""
    output: list[str] = []
    for item in _sequence(value):
        if not isinstance(item, Mapping):
            text = _safe_text(item)
        else:
            language = _safe_text(
                item.get("language") or item.get("name") or item.get("description")
            )
            ability_value = item.get("ability")
            if isinstance(ability_value, Mapping):
                ability = "、".join(
                    text
                    for text in (_safe_text(part) for part in ability_value.values())
                    if text
                )
            elif _sequence(ability_value):
                ability = "、".join(_description_items(ability_value))
            else:
                ability = _safe_text(ability_value)
            text = f"{language}：{ability}" if language and ability else language or ability
        if text:
            output.append(text)
    return output


def _employment_type(value: Any) -> str:
    text = _safe_text(value)
    if text == "1":
        return EMPLOYMENT_TYPE_NAME
    return text


def _job_description_items(description: str) -> list[dict[str, Any]]:
    """從 API 純文字投影清單，與 HTML parser 共用相同 item schema。"""
    items: list[dict[str, Any]] = []
    marker = re.compile(r"^(?:[•●▪*\-]|\d+[.)、])\s*(.+)$")
    for line in description.splitlines():
        match = marker.match(line.strip())
        if match:
            text = _safe_text(match.group(1))
            if text:
                items.append({"text": text, "children": []})
    return items


def _key_value(label: str, text: str, items: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "key_value",
        "label": label,
        "text": text,
        "items": list(items or []),
    }


def _nonempty_key_values(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in blocks if block["text"] or block["items"]]


def parse_job_detail_api(
    data: Mapping[str, Any],
    *,
    job_id: str,
    requested_url: str,
    run_id: str,
    search_page: int,
    scraped_at: str,
    raw_payload_path: str | None,
    raw_sha256: str | None,
) -> dict[str, Any]:
    """將一筆 104 詳情 API ``data`` 轉成 canonical job record。"""
    header = _mapping(data.get("header"))
    detail = _mapping(data.get("jobDetail"))
    condition = _mapping(data.get("condition"))

    title = _safe_text(header.get("jobName"))
    company_name = _safe_text(header.get("custName"))
    description = _safe_text(detail.get("jobDescription"))
    missing_required = [
        label
        for label, value in (
            ("title", title),
            ("company", company_name),
            ("description", description),
        )
        if not value
    ]
    if missing_required:
        raise JobPageParseError(
            f"職缺 {job_id} 缺少必要欄位：{', '.join(missing_required)}"
        )

    company_id = _safe_text(header.get("custNo") or data.get("custNo")) or None
    salary = _safe_text(detail.get("salary")) or None
    raw_job_type = (
        detail.get("jobType")
        if detail.get("jobType") is not None
        else header.get("jobType")
    )
    employment_type = _employment_type(raw_job_type) or None
    region = _safe_text(detail.get("addressRegion"))
    address_detail = _safe_text(detail.get("addressDetail"))
    location = f"{region}{address_detail}" or None

    categories = _description_items(detail.get("jobCategory"))
    experience = _safe_text(condition.get("workExp")) or None
    education = _safe_text(condition.get("edu")) or None
    majors = _description_items(condition.get("major"))
    languages = _language_items(condition.get("language"))
    tools = _description_items(condition.get("specialty"))
    skills = _description_items(condition.get("skill"))
    other = _safe_text(condition.get("other")) or None

    work_blocks = [
        {"type": "paragraph", "text": description},
        _key_value("職務類別", "、".join(categories), categories),
        _key_value("工作待遇", salary or ""),
        _key_value("工作性質", employment_type or ""),
        _key_value("上班地點", location or ""),
    ]
    requirement_blocks = _nonempty_key_values(
        [
            _key_value("工作經歷", experience or ""),
            _key_value("學歷要求", education or ""),
            _key_value("科系要求", "、".join(majors), majors),
            _key_value("語文條件", "\n".join(languages), languages),
            _key_value("擅長工具", "、".join(tools), tools),
            _key_value("工作技能", "、".join(skills), skills),
            _key_value("其他條件", other or ""),
        ]
    )
    requirements_text = "\n".join(
        f'{block["label"]}：{block["text"]}' for block in requirement_blocks
    ) or None

    warnings: list[str] = []
    for value, warning in (
        (salary, "missing_salary"),
        (location, "missing_location"),
        (employment_type, "missing_employment_type"),
        (requirements_text, "missing_requirements"),
    ):
        if not value:
            warnings.append(warning)

    sections = [
        {
            "heading": "工作內容",
            "text": description,
            "blocks": [work_blocks[0], *_nonempty_key_values(work_blocks[1:])],
        },
        {
            "heading": "條件要求",
            "text": requirements_text,
            "blocks": requirement_blocks,
        },
    ]

    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "query": query_metadata(search_page),
            "scraped_at": scraped_at,
        },
        "source": {
            "name": SOURCE_NAME,
            "job_id": str(job_id),
            "job_url": f"https://www.104.com.tw/job/{job_id}",
            "requested_url": requested_url,
            "display_date_raw": _safe_text(header.get("appearDate")) or None,
            "raw_payload_path": raw_payload_path,
            "raw_sha256": raw_sha256,
            # HTML fallback 使用另外兩個欄名；API record 不把 JSON 假稱為 HTML。
            "raw_html_path": None,
            "html_sha256": None,
        },
        "job": {
            "title": title,
            "employment_type_raw": employment_type,
            "categories": categories,
            "description": {
                "text": description,
                "items": _job_description_items(description),
            },
        },
        "company": {"id": company_id, "name": company_name},
        "location": {"raw": location, "address_raw": location},
        "salary": {"raw": salary},
        "requirements": {
            "text": requirements_text,
            "experience_raw": experience,
            "education_raw": education,
            "majors": majors,
            "languages": languages,
            "tools": tools,
            "skills": skills,
            "other_text": other,
            "key_values": [
                {
                    "label": block["label"],
                    "text": block["text"],
                    "items": block["items"],
                }
                for block in requirement_blocks
            ],
        },
        "sections": sections,
        "quality": {
            "status": "partial" if warnings else "ok",
            "warnings": warnings,
        },
    }
