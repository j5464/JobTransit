from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_crawler_104.errors import AccessBlocked, JobPageParseError
from job_crawler_104.parser import parse_job_detail, parse_search_page


FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    """以 UTF-8 讀取固定測試頁面，測試不依賴網路。"""
    return (FIXTURES / name).read_text(encoding="utf-8")


class SearchPageParserTests(unittest.TestCase):
    def test_extracts_canonical_job_links_and_deduplicates_job_id(self) -> None:
        refs = parse_search_page(
            read_fixture("search_page.html"),
            page_url=(
                "https://www.104.com.tw/jobs/search/"
                "?area=6001000000&jobcat=2007001000&ro=1&page=1"
            ),
        )

        self.assertEqual([ref["job_id"] for ref in refs], ["abc123", "def456"])
        self.assertEqual(
            refs[0]["job_url"], "https://www.104.com.tw/job/abc123"
        )
        self.assertEqual(refs[0]["title_hint"], "Python 後端工程師")
        self.assertIn("jobsource=joblist_search", refs[0]["original_url"])

        private_refs = parse_search_page(
            '<h2><a href="/job/privacy1">工程師 person@example.com 0912-345-678</a></h2>',
            page_url="https://www.104.com.tw/jobs/search/",
        )
        self.assertNotIn("person@example.com", private_refs[0]["title_hint"])
        self.assertNotIn("0912-345-678", private_refs[0]["title_hint"])

    def test_challenge_page_is_rejected(self) -> None:
        with self.assertRaises(AccessBlocked):
            parse_search_page(
                read_fixture("challenge_page.html"),
                page_url="https://www.104.com.tw/jobs/search/",
            )

    def test_zero_result_page_is_rejected_as_possible_soft_block(self) -> None:
        html = """
        <html><body>
          <p class="job-list-summary">共 <strong>0</strong> 筆職缺</p>
        </body></html>
        """

        with self.assertRaisesRegex(AccessBlocked, "0 筆"):
            parse_search_page(
                html,
                page_url="https://www.104.com.tw/jobs/search/",
            )


class JobDetailParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = parse_job_detail(
            read_fixture("job_detail.html"),
            job_url="https://www.104.com.tw/job/abc123?jobsource=test",
            scraped_at="2026-08-21T14:30:00+08:00",
            run_id="20260821T143000+0800",
            search_page=1,
            raw_html_path="data/raw/20260821T143000+0800/detail/abc123.html",
        )

    def test_extracts_required_job_fields(self) -> None:
        self.assertEqual(self.record["source"]["job_id"], "abc123")
        self.assertEqual(self.record["job"]["title"], "Python 後端工程師")
        self.assertEqual(
            self.record["company"]["name"], "測試科技股份有限公司"
        )
        self.assertEqual(self.record["company"]["id"], "company789")
        self.assertEqual(self.record["job"]["employment_type_raw"], "全職")
        self.assertEqual(
            self.record["location"]["raw"], "台北市信義區市府路 1 號"
        )
        self.assertEqual(
            self.record["salary"]["raw"], "月薪 50,000~70,000 元"
        )
        self.assertEqual(self.record["quality"]["status"], "ok")

    def test_preserves_line_breaks_and_structured_blocks(self) -> None:
        work_section = next(
            section
            for section in self.record["sections"]
            if section["heading"] == "工作內容"
        )
        block_types = [block["type"] for block in work_section["blocks"]]

        self.assertEqual(
            work_section["blocks"][0]["text"],
            "第一行 工作內容\n第二行工作內容\n第三行工作內容",
        )
        self.assertEqual(
            block_types[:4], ["paragraph", "list", "table", "definition_list"]
        )
        list_block = work_section["blocks"][1]
        self.assertTrue(list_block["ordered"] is False)
        self.assertEqual(
            [
                child_list["ordered"]
                for child_list in list_block["items"][0]["children"]
            ],
            [False, True],
        )
        self.assertEqual(
            [
                [item["text"] for item in child_list["items"]]
                for child_list in list_block["items"][0]["children"]
            ],
            [["撰寫自動化測試"], ["建立測試資料", "執行回歸測試"]],
        )
        table_block = work_section["blocks"][2]
        self.assertEqual(table_block["headers"], ["技術", "程度"])
        self.assertEqual(table_block["rows"][1], ["SQL", ""])
        definition_block = work_section["blocks"][3]
        self.assertEqual(
            definition_block["items"][0]["definitions"],
            ["具備雲端經驗", "了解 CI/CD"],
        )

    def test_maps_known_requirement_fields_and_keeps_unknown_sections(self) -> None:
        requirements = self.record["requirements"]

        self.assertEqual(requirements["experience_raw"], "2年以上")
        self.assertEqual(requirements["education_raw"], "大學、碩士")
        self.assertEqual(
            requirements["majors"], ["資訊工程相關", "資訊管理相關"]
        )
        self.assertEqual(requirements["tools"], ["Python", "Git", "Docker"])
        self.assertEqual(
            requirements["skills"], ["軟體程式設計", "資料庫程式設計"]
        )
        self.assertIn("重視團隊合作", requirements["other_text"])
        self.assertIn("工作經歷：2年以上", requirements["text"])
        self.assertIn(
            "職務亮點", [section["heading"] for section in self.record["sections"]]
        )

    def test_description_projection_matches_work_section_text(self) -> None:
        work_section = next(
            section
            for section in self.record["sections"]
            if section["heading"] == "工作內容"
        )
        self.assertEqual(self.record["job"]["description"]["text"], work_section["text"])

    def test_missing_optional_fields_returns_partial_record_with_warnings(self) -> None:
        html = """
        <html><body>
          <div class="job-header__area">
            <h1>無薪資範例</h1>
            <a data-gtm-head="公司名稱" href="/company/c1">範例公司</a>
          </div>
          <div class="dialog job-description">
            <h2>工作內容</h2><p class="job-description__content">撰寫程式。</p>
            <div class="list-row"><h3>工作性質</h3><div class="list-row__data">全職</div></div>
          </div>
          <div class="dialog job-requirement"><h2>條件要求</h2></div>
        </body></html>
        """

        record = parse_job_detail(
            html,
            job_url="https://www.104.com.tw/job/missing1",
            scraped_at="2026-08-21T14:30:00+08:00",
            run_id="test-run",
            search_page=1,
        )

        self.assertIsNone(record["salary"]["raw"])
        self.assertIsNone(record["location"]["raw"])
        self.assertEqual(record["quality"]["status"], "partial")
        self.assertIn("missing_salary", record["quality"]["warnings"])
        self.assertIn("missing_location", record["quality"]["warnings"])

    def test_missing_required_identity_raises_parse_error(self) -> None:
        html = "<html><body><h1>沒有公司名稱</h1></body></html>"
        with self.assertRaises(JobPageParseError):
            parse_job_detail(
                html,
                job_url="https://www.104.com.tw/job/broken1",
                scraped_at="2026-08-21T14:30:00+08:00",
                run_id="test-run",
                search_page=1,
            )

    def test_work_metadata_is_not_fabricated_as_job_description(self) -> None:
        html = """
        <html><body>
          <div class="job-header__area">
            <h1>無工作描述範例</h1>
            <a data-gtm-head="公司名稱" href="/company/c1">範例公司</a>
          </div>
          <div class="dialog job-description">
            <h2>工作內容</h2>
            <div class="list-row"><h3>工作性質</h3><div class="list-row__data">全職</div></div>
          </div>
        </body></html>
        """

        with self.assertRaisesRegex(JobPageParseError, "description"):
            parse_job_detail(
                html,
                job_url="https://www.104.com.tw/job/narrative1",
                scraped_at="2026-08-21T14:30:00+08:00",
                run_id="test-run",
                search_page=1,
            )

    def test_excludes_contact_section_and_redacts_contact_text(self) -> None:
        html = """
        <html><body>
          <div class="job-header__area">
            <h1>聯絡資訊測試</h1>
            <a data-gtm-head="公司名稱" href="/company/c1">範例公司</a>
          </div>
          <div class="dialog job-description">
            <h2>工作內容</h2>
            <p class="job-description__content">
              請將作品寄到 person@example.com，或撥打 0912-345-678；
              國際格式為 +886 912 345 678。
            </p>
            <ul><li><a href="#">token@example.com</a></li></ul>
            <div class="list-row">
              <h3>擅長工具</h3>
              <div class="list-row__data"><a href="#">anchor@example.com</a></div>
            </div>
          </div>
          <div class="dialog contact"><h2>聯絡方式</h2><p>王小明</p></div>
        </body></html>
        """

        record = parse_job_detail(
            html,
            job_url="https://www.104.com.tw/job/contact1",
            scraped_at="2026-08-21T14:30:00+08:00",
            run_id="test-run",
            search_page=1,
        )

        self.assertNotIn(
            "聯絡方式", [section["heading"] for section in record["sections"]]
        )
        self.assertNotIn("person@example.com", record["job"]["description"]["text"])
        self.assertNotIn("0912-345-678", record["job"]["description"]["text"])
        self.assertNotIn("+886 912 345 678", record["job"]["description"]["text"])
        self.assertNotIn("token@example.com", json.dumps(record, ensure_ascii=False))
        self.assertNotIn("anchor@example.com", json.dumps(record, ensure_ascii=False))
        self.assertIn("[已遮罩電子郵件]", record["job"]["description"]["text"])
        self.assertEqual(
            record["job"]["description"]["text"].count("[已遮罩電話]"), 2
        )

    def test_challenge_page_is_rejected(self) -> None:
        with self.assertRaises(AccessBlocked):
            parse_job_detail(
                read_fixture("challenge_page.html"),
                job_url="https://www.104.com.tw/job/blocked1",
                scraped_at="2026-08-21T14:30:00+08:00",
                run_id="test-run",
                search_page=1,
            )


if __name__ == "__main__":
    unittest.main()
