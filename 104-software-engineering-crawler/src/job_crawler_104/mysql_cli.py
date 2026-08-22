"""將既有 run JSONL 重播到 MySQL，不重新爬取網站。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .console import configure_utf8_console
from .paths import default_data_root, latest_run_jsonl
from .persistence import MySqlSettings, sync_jsonl_to_mysql

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="將爬蟲 JSONL 分批 upsert 到已由 Workbench 建立的 MySQL jobs 表"
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="要重播的 jobs_*.jsonl；省略時使用 data root 的最新 run",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(),
        help="省略 path 時搜尋 run JSONL 的資料根目錄",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = build_parser().parse_args(argv)
    path = args.path or latest_run_jsonl(args.data_root)
    if path is None or not path.is_file():
        print("找不到可同步的 jobs_*.jsonl。", file=sys.stderr)
        return 2
    try:
        settings = MySqlSettings.from_env()
        count = sync_jsonl_to_mysql(
            path,
            settings=settings,
            batch_size=args.batch_size,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"MySQL 同步失敗：{error}", file=sys.stderr)
        return 2
    except Exception as error:
        # PyMySQL 例外型別只在實際連線時載入；邊界統一回傳非零 exit code。
        print(f"MySQL 同步失敗：{error}", file=sys.stderr)
        return 2
    print(f"MySQL 同步完成：{count} 筆輸入已提交（latest-only upsert）")
    print(f"來源：{path}")
    return 0
