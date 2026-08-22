"""把 Selenium 取得的 HTML 解析成可清洗的結構化資料。

這個模組刻意不負責開瀏覽器或寫檔。如此一來，解析器可以使用固定
HTML fixture 離線測試；104 網頁改版時，也能只修改這裡的 selector。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .config import CANONICAL_SCHEMA_VERSION, SOURCE_NAME, query_metadata
from .errors import AccessBlocked, JobPageParseError
from .privacy import redact_contact_text


JOB_ID_PATTERN = re.compile(r"/job/([0-9A-Za-z]+)(?:/|$)")
COMPANY_ID_PATTERN = re.compile(r"/company/([0-9A-Za-z]+)(?:/|$)")

# 這些訊息代表驗證頁或拒絕頁。偵測到時必須停止，不把它當成職缺資料。
BLOCK_PAGE_MARKERS = (
    "just a moment",
    "verify you are human",
    "請完成安全驗證",
    "captcha",
    "cf-chl-",
    "access denied",
    "too many requests",
    "http error 403",
    "http error 429",
    "403 forbidden",
)

SKIPPED_SECTION_HEADINGS = {"聯絡方式"}

# 104 頁面中可能出現在資料欄旁的導流文字，不屬於職缺欄位本身。
NON_DATA_TEXT = {
    "取得專屬你的薪水報告",
    "贊助",
    "提升專業能力",
}


def _normalize_text(text: str | None) -> str:
    """正規化 NBSP 與多餘空白，同時保留有意義的換行。"""
    if not text:
        return ""

    text = text.replace("\xa0", " ").replace("\u3000", " ").replace("\r", "\n")
    normalized_lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[\t\f\v ]+", " ", line).strip()
        if line:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _is_hidden(tag: Tag, *, stop_at: Tag | None = None) -> bool:
    """判斷節點或其父層是否為常見的隱藏／廣告容器。"""
    current: Tag | None = tag
    while current is not None and current is not stop_at:
        classes = set(current.get("class", []))
        style = str(current.get("style", "")).replace(" ", "").lower()
        if "d-none" in classes or "display:none" in style:
            return True
        if current.get("aria-hidden") == "true":
            return True
        if current.name in {"adsmart-ui-switch", "script", "style", "noscript"}:
            return True
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return False


def _clean_clone(tag: Tag) -> Tag:
    """複製節點後移除隱藏內容、廣告元件與非資料 CTA。"""
    fragment = BeautifulSoup(str(tag), "html.parser")
    clone = fragment.find()
    if not isinstance(clone, Tag):  # pragma: no cover - Tag 輸入正常時不會發生
        raise ValueError("無法複製 HTML 節點")

    for unwanted in clone.select(
        "script, style, noscript, svg, adsmart-ui-switch, .d-none, "
        '[aria-hidden="true"], [style*="display: none"], [style*="display:none"]'
    ):
        unwanted.decompose()

    for element in list(clone.find_all(["a", "button"])):
        text = _normalize_text(element.get_text(" ", strip=False))
        href = str(element.get("href", ""))
        if text in NON_DATA_TEXT or "guide.104.com.tw/salary" in href:
            element.decompose()
    return clone


def _text_from_tag(tag: Tag, *, multiline: bool = True) -> str:
    """讀取可見文字；先把 br 轉成換行，避免段落全部黏在一起。"""
    clone = _clean_clone(tag)
    for br in clone.find_all("br"):
        br.replace_with("\n")
    text = redact_contact_text(_normalize_text(clone.get_text(" ", strip=False)))
    return text if multiline else text.replace("\n", " ")


def _extract_id(url: str, pattern: re.Pattern[str], label: str) -> str:
    """從網址 path 取得穩定 ID；不以職稱＋公司猜測識別碼。"""
    match = pattern.search(urlparse(url).path)
    if not match:
        raise JobPageParseError(f"無法從網址取得{label}：{url}")
    return match.group(1)


def _canonical_job_url(job_id: str) -> str:
    return f"https://www.104.com.tw/job/{job_id}"


def _raise_if_blocked(html: str) -> None:
    """遇到 Cloudflare/CAPTCHA/拒絕頁就明確報錯並停止。"""
    sample = html[:200_000].lower()
    if any(marker in sample for marker in BLOCK_PAGE_MARKERS):
        raise AccessBlocked("頁面要求安全驗證或拒絕存取；已停止，未嘗試規避。")


def parse_search_page(html: str, *, page_url: str) -> list[dict[str, str]]:
    """解析搜尋結果卡片，依職缺 ID 去重並保留 DOM 原始順序。

    104 搜尋頁由 JavaScript 渲染，因此傳入的 ``html`` 應來自
    ``driver.page_source``，而不是假設 requests 一定能取得相同內容。
    """
    _raise_if_blocked(html)
    soup = BeautifulSoup(html, "html.parser")
    page_text = _normalize_text(soup.get_text(" ", strip=False))
    if re.search(r"共\s*0\s*筆", page_text):
        raise AccessBlocked("搜尋頁顯示共 0 筆職缺，可能為軟性拒絕；已停止。")

    jobs: list[dict[str, str]] = []
    seen_job_ids: set[str] = set()
    for link in soup.select('h2 a[href*="/job/"]'):
        href = link.get("href")
        if not href:
            continue
        original_url = urljoin(page_url, href)
        match = JOB_ID_PATTERN.search(urlparse(original_url).path)
        if not match:
            continue
        job_id = match.group(1)
        if job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)
        jobs.append(
            {
                "job_id": job_id,
                "job_url": _canonical_job_url(job_id),
                "original_url": original_url,
                "title_hint": redact_contact_text(
                    _normalize_text(link.get_text(" ", strip=False))
                ),
            }
        )
    return jobs


def _parse_list_item(item: Tag) -> dict[str, Any]:
    """遞迴保留每個子清單的類型與分組，避免文字重複拼接。"""
    clone = _clean_clone(item)
    nested_lists = list(clone.find_all(["ul", "ol"], recursive=False))
    children: list[dict[str, Any]] = []
    for nested in nested_lists:
        children.append(_parse_list(nested))
        nested.decompose()
    text = redact_contact_text(_normalize_text(clone.get_text(" ", strip=False)))
    return {"text": text, "children": children}


def _parse_list(tag: Tag) -> dict[str, Any]:
    return {
        "type": "list",
        "ordered": tag.name == "ol",
        "items": [_parse_list_item(item) for item in tag.find_all("li", recursive=False)],
    }


def _parse_table(tag: Tag) -> dict[str, Any]:
    """把 table 保留為 headers + rows；表頭不重複放進資料列。"""
    headers: list[str] = []
    header_row = tag.select_one("thead tr")
    if header_row is not None:
        headers = [
            _text_from_tag(cell, multiline=False)
            for cell in header_row.find_all(["th", "td"], recursive=False)
        ]
    elif tag.find("th") is not None:
        first_row = tag.find("tr")
        if first_row is not None:
            headers = [
                _text_from_tag(cell, multiline=False)
                for cell in first_row.find_all(["th", "td"], recursive=False)
            ]
            header_row = first_row

    rows: list[list[str]] = []
    for row in tag.find_all("tr"):
        if row is header_row:
            continue
        cells = row.find_all(["th", "td"], recursive=False)
        if cells:
            rows.append([_text_from_tag(cell, multiline=False) for cell in cells])
    return {"type": "table", "headers": headers, "rows": rows}


def _parse_definition_list(tag: Tag) -> dict[str, Any]:
    """將 dt 與它後面的一或多個 dd 配對，並維持原順序。"""
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for child in tag.find_all(["dt", "dd"], recursive=False):
        if child.name == "dt":
            current = {"term": _text_from_tag(child, multiline=False), "definitions": []}
            items.append(current)
        elif current is not None:
            current["definitions"].append(_text_from_tag(child, multiline=False))
    return {"type": "definition_list", "items": items}


def _visible_tokens(data: Tag) -> list[str]:
    """抽出工具、技能、職務類別等頁面上明列的項目。"""
    tokens: list[str] = []
    seen: set[str] = set()
    for element in data.select("a, u"):
        if element.name == "u" and element.find_parent("a") is not None:
            continue
        if _is_hidden(element, stop_at=data):
            continue
        text = redact_contact_text(
            _normalize_text(element.get_text(" ", strip=False))
        )
        href = str(element.get("href", ""))
        if not text or text in NON_DATA_TEXT or "guide.104.com.tw/salary" in href:
            continue
        if text not in seen:
            seen.add(text)
            tokens.append(text)
    return tokens


def _parse_key_value(row: Tag) -> dict[str, Any] | None:
    head = row.select_one(".list-row__head h3") or row.find("h3")
    data = row.select_one(".list-row__data")
    if head is None or data is None:
        return None
    label = _text_from_tag(head, multiline=False)
    text = _text_from_tag(data, multiline=False)
    return {
        "type": "key_value",
        "label": label,
        "text": text,
        "items": _visible_tokens(data),
    }


def _has_block_ancestor(tag: Tag, section: Tag) -> bool:
    """只處理最外層 block，防止 ul 裡的 ul 或 table 裡的 p 被重複解析。"""
    block_names = {"p", "ul", "ol", "table", "dl"}
    parent = tag.parent
    while isinstance(parent, Tag) and parent is not section:
        if parent.name in block_names or "list-row" in parent.get("class", []):
            return True
        parent = parent.parent
    return False


def _flatten_list_text(items: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item["text"]:
            output.append(item["text"])
        for child_list in item["children"]:
            output.extend(_flatten_list_text(child_list["items"]))
    return output


def _block_text(block: dict[str, Any]) -> str:
    if block["type"] == "paragraph":
        return block["text"]
    if block["type"] == "list":
        return "\n".join(_flatten_list_text(block["items"]))
    if block["type"] == "table":
        rows = ([block["headers"]] if block["headers"] else []) + block["rows"]
        return "\n".join(" | ".join(row) for row in rows)
    if block["type"] == "definition_list":
        return "\n".join(
            f'{item["term"]}：{"、".join(item["definitions"])}'
            for item in block["items"]
        )
    return ""


def _parse_section(section: Tag, heading: str) -> dict[str, Any]:
    """依 DOM 順序擷取段落、清單、表格、dl 與 104 label/value 列。"""
    blocks: list[dict[str, Any]] = []
    narrative_parts: list[str] = []
    key_value_parts: list[str] = []

    for element in section.descendants:
        if not isinstance(element, Tag) or _is_hidden(element, stop_at=section):
            continue

        block: dict[str, Any] | None = None
        if "list-row" in element.get("class", []):
            parent_row = element.find_parent(class_="list-row")
            if parent_row is None or parent_row is section:
                block = _parse_key_value(element)
                if block and block["label"]:
                    key_value_parts.append(f'{block["label"]}：{block["text"]}')
        elif element.name in {"p", "ul", "ol", "table", "dl"}:
            if _has_block_ancestor(element, section):
                continue
            if element.name == "p":
                text = _text_from_tag(element)
                if text:
                    block = {"type": "paragraph", "text": text}
            elif element.name in {"ul", "ol"}:
                block = _parse_list(element)
            elif element.name == "table":
                block = _parse_table(element)
            elif element.name == "dl":
                block = _parse_definition_list(element)

            if block is not None:
                text = _block_text(block)
                if text:
                    narrative_parts.append(text)

        if block is not None:
            blocks.append(block)

    # 工作內容不可用「工作性質／待遇」等 metadata 冒充描述；條件區才允許
    # 在沒有敘事 block 時，以 label/value 組合成方便分析的全文投影。
    text_parts = (
        narrative_parts
        if heading == "工作內容"
        else narrative_parts or key_value_parts
    )
    text = "\n".join(text_parts)
    return {"heading": heading, "text": text, "blocks": blocks}


def _find_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for container in soup.select("div.dialog"):
        # 104 目前將區段名稱放在 .title h2；第二個 selector 是改版時的保守 fallback。
        heading_tag = container.select_one(":scope > .row .title h2") or container.find("h2")
        if heading_tag is None:
            continue
        heading = _text_from_tag(heading_tag, multiline=False)
        # 聯絡人姓名／回覆設定不在研究欄位範圍內，結構化結果不輸出該區段。
        if heading and heading not in SKIPPED_SECTION_HEADINGS:
            sections.append(_parse_section(container, heading))
    return sections


def _section_by_heading(
    sections: list[dict[str, Any]], heading: str
) -> dict[str, Any] | None:
    return next((section for section in sections if section["heading"] == heading), None)


def _key_values(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    if section is None:
        return []
    return [block for block in section["blocks"] if block["type"] == "key_value"]


def _key_value_map(section: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    # 便利投影只取相同 label 的第一筆；原始順序與重複 label 仍保留在 sections。
    output: dict[str, dict[str, Any]] = {}
    for block in _key_values(section):
        output.setdefault(block["label"], block)
    return output


def _split_zh_items(text: str | None) -> list[str]:
    if not text:
        return []
    return [item.strip() for item in re.split(r"[、，,]", text) if item.strip()]


def _items_or_split(block: dict[str, Any] | None) -> list[str]:
    if block is None:
        return []
    return block["items"] or _split_zh_items(block["text"])


def _description_list_items(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    if section is None:
        return []
    items: list[dict[str, Any]] = []
    for block in section["blocks"]:
        if block["type"] == "list":
            items.extend(block["items"])
    return items


def parse_job_detail(
    html: str,
    *,
    job_url: str,
    scraped_at: str,
    run_id: str,
    search_page: int,
    raw_html_path: str | None = None,
) -> dict[str, Any]:
    """將單一 104 詳情頁解析成 JSONL 友善的 canonical record。"""
    _raise_if_blocked(html)
    soup = BeautifulSoup(html, "html.parser")

    job_id = _extract_id(job_url, JOB_ID_PATTERN, "職缺 ID")
    title_tag = soup.select_one(".job-header__area h1") or soup.find("h1")
    company_tag = soup.select_one('a[data-gtm-head="公司名稱"]')
    title = _text_from_tag(title_tag, multiline=False) if title_tag else ""
    company_name = _text_from_tag(company_tag, multiline=False) if company_tag else ""
    if not title or not company_name:
        raise JobPageParseError(
            f"職缺 {job_id} 缺少必要欄位："
            f"title={'ok' if title else 'missing'}, "
            f"company={'ok' if company_name else 'missing'}"
        )

    company_href = urljoin(job_url, company_tag.get("href", ""))
    company_match = COMPANY_ID_PATTERN.search(urlparse(company_href).path)
    company_id = company_match.group(1) if company_match else None

    sections = _find_sections(soup)
    work_section = _section_by_heading(sections, "工作內容")
    requirement_section = _section_by_heading(sections, "條件要求")
    work_values = _key_value_map(work_section)
    requirement_values = _key_value_map(requirement_section)

    salary_raw = work_values.get("工作待遇", {}).get("text") or None
    employment_type = work_values.get("工作性質", {}).get("text") or None
    location_raw = work_values.get("上班地點", {}).get("text") or None
    description_text = work_section["text"] if work_section else None
    requirements_text = requirement_section["text"] if requirement_section else None
    if not description_text:
        raise JobPageParseError(f"職缺 {job_id} 缺少必要欄位：description")

    warnings: list[str] = []
    for value, warning in (
        (salary_raw, "missing_salary"),
        (location_raw, "missing_location"),
        (employment_type, "missing_employment_type"),
        (requirements_text, "missing_requirements"),
    ):
        if not value:
            warnings.append(warning)

    date_tag = soup.select_one('.job-header__area [title*="更新"]')
    display_date = None
    if date_tag is not None:
        display_date = _normalize_text(str(date_tag.get("title") or date_tag.get_text(" ")))

    record: dict[str, Any] = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "query": query_metadata(search_page),
            "scraped_at": scraped_at,
        },
        "source": {
            "name": SOURCE_NAME,
            "job_id": job_id,
            "job_url": _canonical_job_url(job_id),
            "requested_url": job_url,
            "display_date_raw": display_date,
            "raw_payload_path": None,
            "raw_sha256": None,
            "raw_html_path": raw_html_path,
            "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        },
        "job": {
            "title": title,
            "employment_type_raw": employment_type,
            "categories": _items_or_split(work_values.get("職務類別")),
            "description": {
                "text": description_text,
                "items": _description_list_items(work_section),
            },
        },
        "company": {"id": company_id, "name": company_name},
        "location": {"raw": location_raw, "address_raw": location_raw},
        "salary": {"raw": salary_raw},
        "requirements": {
            "text": requirements_text,
            "experience_raw": requirement_values.get("工作經歷", {}).get("text")
            or None,
            "education_raw": requirement_values.get("學歷要求", {}).get("text")
            or None,
            "majors": _items_or_split(requirement_values.get("科系要求")),
            "languages": (
                [requirement_values["語文條件"]["text"]]
                if requirement_values.get("語文條件", {}).get("text")
                else []
            ),
            "tools": _items_or_split(requirement_values.get("擅長工具")),
            "skills": _items_or_split(requirement_values.get("工作技能")),
            "other_text": requirement_values.get("其他條件", {}).get("text")
            or None,
            "key_values": [
                {
                    "label": block["label"],
                    "text": block["text"],
                    "items": block["items"],
                }
                for block in _key_values(requirement_section)
            ],
        },
        "sections": sections,
        "quality": {
            "status": "partial" if warnings else "ok",
            "warnings": warnings,
        },
    }
    return record
