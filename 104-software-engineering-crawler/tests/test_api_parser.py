from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_crawler_104.api_parser import parse_job_detail_api
from job_crawler_104.errors import JobPageParseError
from job_crawler_104.parser import parse_job_detail
from job_crawler_104.storage import flatten_record


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "job_detail_api.json"


def read_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class ApiJobDetailParserTests(unittest.TestCase):
    def test_maps_current_api_data_to_canonical_record_without_contact_data(self) -> None:
        record = parse_job_detail_api(
            read_fixture(),
            job_id="abc123",
            requested_url="https://www.104.com.tw/api/jobs/abc123",
            run_id="20260821T143000+0800",
            search_page=2,
            scraped_at="2026-08-21T14:30:00+08:00",
            raw_payload_path="raw-root://20260821T143000+0800/detail/abc123.json",
            raw_sha256="known-payload-sha256",
        )

        self.assertEqual(record["job"]["title"], "Python 後端工程師")
        self.assertEqual(record["company"]["name"], "範例科技股份有限公司")
        self.assertEqual(record["company"]["id"], "example-company-001")
        self.assertEqual(record["location"]["raw"], "台北市信義區市府路 1 號")
        self.assertEqual(record["salary"]["raw"], "月薪 50,000~70,000 元")
        self.assertEqual(record["job"]["employment_type_raw"], "全職")
        self.assertEqual(
            record["job"]["description"]["text"],
            "開發 REST API\n撰寫自動化測試",
        )
        self.assertEqual(
            record["job"]["categories"], ["後端工程師", "軟體工程師"]
        )
        self.assertEqual(record["requirements"]["experience_raw"], "2年以上")
        self.assertEqual(record["requirements"]["education_raw"], "大學以上")
        self.assertEqual(
            record["requirements"]["majors"],
            ["資訊工程相關", "資訊管理相關"],
        )
        self.assertEqual(
            record["requirements"]["languages"],
            ["英文：聽 /中等、說 /中等、讀 /中等、寫 /中等"],
        )
        self.assertEqual(record["requirements"]["tools"], ["Python", "Git"])
        self.assertEqual(record["requirements"]["skills"], ["軟體程式設計"])
        self.assertEqual(record["requirements"]["other_text"], "重視團隊合作")

        self.assertEqual(record["run"]["query"]["search_page"], 2)
        self.assertEqual(record["run"]["query"]["jobcat_code"], "2007001000")
        self.assertEqual(record["source"]["name"], "104")
        self.assertEqual(
            record["source"]["requested_url"],
            "https://www.104.com.tw/api/jobs/abc123",
        )
        self.assertEqual(
            record["source"]["raw_payload_path"],
            "raw-root://20260821T143000+0800/detail/abc123.json",
        )
        self.assertEqual(record["source"]["raw_sha256"], "known-payload-sha256")
        self.assertIsNone(record["source"]["raw_html_path"])
        self.assertIsNone(record["source"]["html_sha256"])
        self.assertEqual(record["quality"], {"status": "ok", "warnings": []})

        csv_row = flatten_record(record)
        self.assertEqual(csv_row["job_title"], "Python 後端工程師")
        self.assertEqual(csv_row["source_job_id"], "abc123")
        self.assertEqual(csv_row["tools_json"], '["Python","Git"]')

        sections = {section["heading"]: section for section in record["sections"]}
        self.assertEqual(sections["工作內容"]["blocks"][0]["type"], "paragraph")
        self.assertEqual(
            next(
                block
                for block in sections["條件要求"]["blocks"]
                if block["label"] == "擅長工具"
            )["items"],
            ["Python", "Git"],
        )

        serialized = json.dumps(record, ensure_ascii=False).lower()
        for forbidden in (
            "contact",
            "email",
            "phone",
            "private@example.invalid",
            "+886 912 345 678",
            "不應輸出的聯絡人",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_missing_optional_fields_returns_partial_record_with_warnings(self) -> None:
        data = {
            "header": {
                "jobName": "最小職缺",
                "custName": "範例公司",
            },
            "jobDetail": {"jobDescription": "負責系統開發。"},
        }

        record = parse_job_detail_api(
            data,
            job_id="minimal1",
            requested_url="https://www.104.com.tw/api/jobs/minimal1",
            run_id="test-run",
            search_page=1,
            scraped_at="2026-08-21T14:30:00+08:00",
            raw_payload_path=None,
            raw_sha256=None,
        )

        self.assertIsNone(record["salary"]["raw"])
        self.assertIsNone(record["location"]["raw"])
        self.assertIsNone(record["job"]["employment_type_raw"])
        self.assertIsNone(record["requirements"]["text"])
        self.assertEqual(record["quality"]["status"], "partial")
        self.assertEqual(
            record["quality"]["warnings"],
            [
                "missing_salary",
                "missing_location",
                "missing_employment_type",
                "missing_requirements",
            ],
        )

    def test_missing_required_title_company_or_description_raises_parse_error(self) -> None:
        cases = {
            "title": {
                "header": {"custName": "公司"},
                "jobDetail": {"jobDescription": "工作內容"},
            },
            "company": {
                "header": {"jobName": "職缺"},
                "jobDetail": {"jobDescription": "工作內容"},
            },
            "description": {
                "header": {"jobName": "職缺", "custName": "公司"},
                "jobDetail": {},
            },
        }

        for missing_field, data in cases.items():
            with self.subTest(missing_field=missing_field):
                with self.assertRaisesRegex(JobPageParseError, missing_field):
                    parse_job_detail_api(
                        data,
                        job_id="broken1",
                        requested_url="https://www.104.com.tw/api/jobs/broken1",
                        run_id="test-run",
                        search_page=1,
                        scraped_at="2026-08-21T14:30:00+08:00",
                        raw_payload_path=None,
                        raw_sha256=None,
                    )

    def test_api_and_html_parsers_share_description_item_contract(self) -> None:
        api_data = read_fixture()
        api_data["jobDetail"]["jobDescription"] = "- API 清單項目"
        api_record = parse_job_detail_api(
            api_data,
            job_id="abc123",
            requested_url="https://www.104.com.tw/api/jobs/abc123",
            run_id="contract-run",
            search_page=1,
            scraped_at="2026-08-21T14:30:00+08:00",
            raw_payload_path=None,
            raw_sha256=None,
        )
        html_record = parse_job_detail(
            (Path(__file__).parent / "fixtures" / "job_detail.html").read_text(
                encoding="utf-8"
            ),
            job_url="https://www.104.com.tw/job/abc123",
            scraped_at="2026-08-21T14:30:00+08:00",
            run_id="contract-run",
            search_page=1,
        )

        for record in (api_record, html_record):
            self.assertEqual(record["schema_version"], "2.0")
            items = record["job"]["description"]["items"]
            self.assertTrue(items)
            self.assertTrue(
                all(
                    isinstance(item, dict)
                    and isinstance(item.get("text"), str)
                    and isinstance(item.get("children"), list)
                    for item in items
                )
            )
        self.assertEqual(
            set(api_record["source"]), set(html_record["source"])
        )


if __name__ == "__main__":
    unittest.main()
