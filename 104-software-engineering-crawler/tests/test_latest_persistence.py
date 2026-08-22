from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_crawler_104.persistence import (
    MYSQL_COLUMNS,
    MYSQL_UPSERT_SQL,
    MySqlSettings,
    job_content_hash,
    record_to_mysql_values,
    save_latest_job,
    sync_jsonl_to_mysql,
    upsert_latest_jobs,
)
from job_crawler_104.mysql_cli import latest_run_jsonl


def make_record(*, job_id: str = "abc123", title: str = "Python 工程師") -> dict:
    return {
        "schema_version": "2.0",
        "run": {
            "run_id": "20260821T143000+0800",
            "query": {"search_page": 1},
            "scraped_at": "2026-08-21T14:30:00+08:00",
        },
        "source": {
            "name": "104",
            "job_id": job_id,
            "job_url": f"https://www.104.com.tw/job/{job_id}",
        },
        "job": {
            "title": title,
            "employment_type_raw": "全職",
            "categories": ["軟體工程師"],
            "description": {"text": "開發系統", "items": []},
        },
        "company": {"id": "123", "name": "測試公司"},
        "location": {"raw": "台北市", "address_raw": "台北市"},
        "salary": {"raw": "月薪 50,000 元"},
        "requirements": {
            "text": "熟悉 Python",
            "experience_raw": "1 年",
            "education_raw": "大學",
            "majors": [],
            "languages": [],
            "tools": ["Python"],
            "skills": [],
            "other_text": None,
            "key_values": [],
        },
        "sections": [],
        "quality": {"status": "ok", "warnings": []},
    }


class BatchRecordingCursor:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def __enter__(self) -> "BatchRecordingCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def executemany(self, _sql: str, rows: list[tuple]) -> None:
        self.batch_sizes.append(len(rows))

    def execute(self, _sql: str) -> None:
        return None


class BatchRecordingConnection:
    def __init__(self) -> None:
        self.recording_cursor = BatchRecordingCursor()
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self) -> BatchRecordingCursor:
        return self.recording_cursor

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


class LatestJobFileTests(unittest.TestCase):
    def test_same_job_id_overwrites_one_sharded_latest_file(self) -> None:
        first = make_record(title="舊職稱")
        latest = make_record(title="新職稱")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_path = save_latest_job(first, root=root)
            latest_path = save_latest_job(latest, root=root)
            saved_files = list(root.rglob("*.json"))
            saved = json.loads(latest_path.read_text(encoding="utf-8"))

        self.assertEqual(first_path, root / "ab" / "abc123.json")
        self.assertEqual(latest_path, first_path)
        self.assertEqual(saved_files, [first_path])
        self.assertEqual(saved["job"]["title"], "新職稱")

    def test_older_capture_cannot_overwrite_newer_latest_file(self) -> None:
        newer = make_record(title="較新職稱")
        newer["run"]["scraped_at"] = "2026-08-22T14:30:00+08:00"
        older = make_record(title="較舊職稱")
        older["run"]["scraped_at"] = "2026-08-21T14:30:00+08:00"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = save_latest_job(newer, root=root)
            save_latest_job(older, root=root)
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved["job"]["title"], "較新職稱")

    def test_rejects_job_id_that_could_escape_latest_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                save_latest_job(make_record(job_id="../outside"), root=Path(temp_dir))
            with self.assertRaises(ValueError):
                save_latest_job(make_record(job_id="a" * 65), root=Path(temp_dir))

    def test_content_hash_ignores_capture_metadata_but_detects_job_change(self) -> None:
        original = make_record()
        later_capture = copy.deepcopy(original)
        later_capture["run"]["run_id"] = "20260822T143000+0800"
        later_capture["run"]["scraped_at"] = "2026-08-22T14:30:00+08:00"
        changed = copy.deepcopy(later_capture)
        changed["salary"]["raw"] = "月薪 60,000 元"

        self.assertEqual(job_content_hash(original), job_content_hash(later_capture))
        self.assertNotEqual(job_content_hash(original), job_content_hash(changed))

    def test_atomic_replace_failure_keeps_previous_latest_file(self) -> None:
        previous = make_record(title="仍可讀取的舊版本")
        incoming = make_record(title="尚未完成的新版本")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = save_latest_job(previous, root=root)
            with patch(
                "job_crawler_104.persistence.os.replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaises(OSError):
                    save_latest_job(incoming, root=root)
            saved = json.loads(target.read_text(encoding="utf-8"))
            temporary_files = list(target.parent.glob("*.tmp"))

        self.assertEqual(saved["job"]["title"], "仍可讀取的舊版本")
        self.assertEqual(temporary_files, [])


class MySqlLatestJobTests(unittest.TestCase):
    def test_workbench_ddl_matches_python_mapping_and_is_non_destructive(self) -> None:
        ddl = (PROJECT_ROOT / "sql" / "001_create_database_and_jobs.sql").read_text(
            encoding="utf-8"
        )

        for column in MYSQL_COLUMNS:
            self.assertIn(f"`{column}`", ddl)
        self.assertIn("PRIMARY KEY (`job_id`)", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS", ddl)
        self.assertNotRegex(ddl, r"(?mi)^\s*(DROP|TRUNCATE)\b")

    def test_record_mapping_preserves_nested_json_and_uses_utc_time(self) -> None:
        record = make_record()

        values = record_to_mysql_values(record)
        row = dict(zip(MYSQL_COLUMNS, values, strict=True))

        self.assertEqual(row["job_id"], "abc123")
        self.assertIn('"Python"', row["tools"])
        self.assertIn('"title":"Python 工程師"', row["canonical_json"])
        self.assertEqual(str(row["first_seen_at"]), "2026-08-21 06:30:00")
        self.assertEqual(row["first_seen_at"], row["last_seen_at"])

    def test_upsert_uses_one_batch_transaction_and_latest_guard(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        records = [make_record(job_id="abc123"), make_record(job_id="def456")]

        count = upsert_latest_jobs(connection, records)

        self.assertEqual(count, 2)
        cursor.executemany.assert_called_once()
        sql, rows = cursor.executemany.call_args.args
        self.assertEqual(sql, MYSQL_UPSERT_SQL)
        self.assertEqual(len(rows), 2)
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)
        self.assertIn("incoming.last_seen_at >= jobs.last_seen_at", sql)
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()

    def test_batch_dedup_keeps_latest_content_and_earliest_first_seen(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        older = make_record(title="舊版本")
        newer = make_record(title="新版本")
        newer["run"]["scraped_at"] = "2026-08-22T14:30:00+08:00"

        count = upsert_latest_jobs(connection, [newer, older])

        rows = cursor.executemany.call_args.args[1]
        row = dict(zip(MYSQL_COLUMNS, rows[0], strict=True))
        self.assertEqual(count, 1)
        self.assertEqual(row["job_title"], "新版本")
        self.assertEqual(str(row["first_seen_at"]), "2026-08-21 06:30:00")
        self.assertEqual(str(row["last_seen_at"]), "2026-08-22 06:30:00")

    def test_upsert_rolls_back_failed_batch(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.executemany.side_effect = RuntimeError("database unavailable")

        with self.assertRaises(RuntimeError):
            upsert_latest_jobs(connection, [make_record()])

        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()

    def test_mysql_settings_require_password_without_hardcoding_it(self) -> None:
        with self.assertRaisesRegex(ValueError, "JOB104_MYSQL_PASSWORD"):
            MySqlSettings.from_env({})

        settings = MySqlSettings.from_env(
            {
                "JOB104_MYSQL_PASSWORD": "test-secret",
                "JOB104_MYSQL_USER": "root",
            }
        )

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 3306)
        self.assertEqual(settings.database, "job_crawler_104")
        self.assertEqual(settings.user, "root")
        self.assertNotIn("test-secret", repr(settings))

    def test_jsonl_sync_commits_in_batches_and_closes_connection(self) -> None:
        connection = MagicMock()
        records = [make_record(job_id=f"job{number}") for number in range(5)]

        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "jobs.jsonl"
            jsonl_path.write_text(
                "".join(
                    json.dumps(record, ensure_ascii=False) + "\n" for record in records
                ),
                encoding="utf-8",
            )
            synced = sync_jsonl_to_mysql(
                jsonl_path,
                settings=MySqlSettings(
                    host="127.0.0.1",
                    port=3306,
                    database="job_crawler_104",
                    user="root",
                    password="test-secret",
                ),
                batch_size=2,
                connection_factory=lambda _settings: connection,
            )

        cursor = connection.cursor.return_value.__enter__.return_value
        self.assertEqual(synced, 5)
        self.assertEqual(cursor.executemany.call_count, 3)
        cursor.execute.assert_called_once()
        self.assertIn("SELECT", cursor.execute.call_args.args[0])
        self.assertEqual(connection.commit.call_count, 3)
        connection.close.assert_called_once_with()

    def test_mysql_replay_selects_most_recently_updated_run_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            older = data_root / "runs" / "20260820T120000+0800" / "jobs_old.jsonl"
            latest = data_root / "runs" / "20260821T120000+0800" / "jobs_new.jsonl"
            older.parent.mkdir(parents=True)
            latest.parent.mkdir(parents=True)
            older.write_text("", encoding="utf-8")
            latest.write_text("", encoding="utf-8")
            os.utime(latest, ns=(100, 100))
            os.utime(older, ns=(200, 200))

            selected = latest_run_jsonl(data_root)

        self.assertEqual(selected, older)

    def test_ten_thousand_records_use_bounded_mysql_batches(self) -> None:
        connection = BatchRecordingConnection()
        settings = MySqlSettings(password="test-secret")

        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "jobs.jsonl"
            with jsonl_path.open("w", encoding="utf-8", newline="\n") as file:
                for number in range(10_001):
                    file.write(
                        json.dumps(
                            make_record(job_id=f"job{number}"), ensure_ascii=False
                        )
                        + "\n"
                    )
            synced = sync_jsonl_to_mysql(
                jsonl_path,
                settings=settings,
                batch_size=500,
                connection_factory=lambda _settings: connection,
            )

        self.assertEqual(synced, 10_001)
        self.assertEqual(connection.recording_cursor.batch_sizes, [500] * 20 + [1])
        self.assertEqual(connection.commit_count, 21)
        self.assertEqual(connection.rollback_count, 0)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
