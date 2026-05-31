from __future__ import annotations

import argparse
import sys

from .config import DEFAULT_LOG_FILE, DEFAULT_OUTPUT, DEFAULT_PROFILE_DIR
from .logging_utils import log, setup_log
from .modes import KeywordTask, keyword_tasks_from_args, parse_keyword_task, validate_runtime_args
from .runner import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Xiaohongshu keyword search note details into a local CSV."
    )
    parser.add_argument("--keyword", help="Search keyword, for example: 城市露营")
    parser.add_argument(
        "--keyword-task",
        action="append",
        type=parse_keyword_task,
        help="Repeatable multi-keyword task in KEYWORD=COUNT format, for example: --keyword-task 城市露营=50",
    )
    parser.add_argument("--max-notes", type=int, default=30, help="Maximum note detail pages to collect.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV path.")
    parser.add_argument("--input-csv", help="Read note URLs from a previous --search-only CSV instead of searching again.")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR, help="Persistent browser profile directory.")
    parser.add_argument("--login-only", action="store_true", help="Open browser for manual login and save session.")
    parser.add_argument("--check-login", action="store_true", help="Check whether the saved browser session appears usable.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode. Not recommended for login.")
    parser.add_argument("--slow-mo", type=int, default=0, help="Playwright slow motion in milliseconds.")
    parser.add_argument("--max-scrolls", type=int, default=25, help="Maximum scroll rounds on search page.")
    parser.add_argument(
        "--stagnant-limit",
        type=int,
        default=8,
        help="Stop search scrolling after this many rounds without new links.",
    )
    parser.add_argument("--scroll-pixels", type=int, default=2600, help="Pixels to scroll each search round.")
    parser.add_argument("--search-settle-ms", type=int, default=3000, help="Initial wait after opening the search page.")
    parser.add_argument("--scroll-delay", type=float, default=2.0, help="Delay after each search page scroll.")
    parser.add_argument("--search-only", action="store_true", help="Only collect search result cards and do not open detail pages.")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Collect details by opening note previews on the search page instead of navigating to detail URLs.",
    )
    parser.add_argument(
        "--new-tab",
        action="store_true",
        help="Collect details by opening each search result card in a new tab and extracting the opened page.",
    )
    parser.add_argument("--min-delay", type=float, default=3.0, help="Minimum delay between detail pages.")
    parser.add_argument("--max-delay", type=float, default=7.0, help="Maximum delay between detail pages.")
    parser.add_argument(
        "--rest-every",
        type=int,
        default=100,
        help="Take a longer rest after this many detail pages. Use 0 to disable.",
    )
    parser.add_argument("--rest-minutes", type=float, default=3.0, help="Long-rest duration in minutes.")
    parser.add_argument(
        "--restart-every",
        type=int,
        default=200,
        help="Restart the browser context after this many detail pages. Use 0 to disable.",
    )
    parser.add_argument(
        "--max-runtime-minutes",
        type=float,
        default=0,
        help="Stop gracefully after this many minutes. Use 0 to disable.",
    )
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Page navigation timeout in milliseconds.")
    parser.add_argument(
        "--max-errors",
        type=int,
        default=3,
        help="Pause for manual takeover after this many consecutive detail or preview errors.",
    )
    parser.add_argument("--error-delay", type=float, default=20.0, help="Extra delay after a detail-page error.")
    parser.add_argument(
        "--ignore-checkpoint",
        action="store_true",
        help="Continue even if a login, verification, or access checkpoint is detected.",
    )
    parser.add_argument(
        "--block-media",
        action="store_true",
        help="Block image, media, and font requests to reduce bandwidth.",
    )
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="Append run logs to this file. Use an empty string to disable.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing CSV instead of appending/resuming.")
    parser.add_argument("--debug", action="store_true", help="Save debug HTML and extraction JSON for each detail page.")
    parser.add_argument("--debug-on-error", action="store_true", help="Save debug HTML only for failed detail pages.")
    parser.add_argument("--debug-dir", default="data/debug", help="Directory for debug files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_log(args.log_file)
    keyword_tasks = keyword_tasks_from_args(args)
    if not args.login_only and not args.check_login and not keyword_tasks and not args.input_csv:
        print(
            "请提供 --keyword、--keyword-task，或使用 --input-csv 读取已保存链接，或使用 --login-only 先完成登录。",
            file=sys.stderr,
        )
        return 2
    try:
        runtime_warnings = validate_runtime_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for warning in runtime_warnings:
        log(f"参数提示：{warning}")
    return run(args, keyword_tasks)
