from __future__ import annotations

from xhs.browser import check_login_status, detect_checkpoint, ensure_not_checkpoint, launch_context, run_login_only
from xhs.cli import main, parse_args
from xhs.config import BASE_URL, CSV_COLUMNS, DEFAULT_LOG_FILE, DEFAULT_OUTPUT, DEFAULT_PROFILE_DIR
from xhs.csv_store import (
    ResumeIndex,
    append_rows,
    csv_header_matches,
    existing_keys,
    load_resume_index,
    load_search_items_from_csv,
    normalize_csv_row,
    row_has_content,
    row_resume_key,
    search_item_to_row,
)
from xhs.detail import click_expand_buttons, merge_extraction, save_debug_files, scrape_note_detail
from xhs.logging_utils import log, now_text, setup_log
from xhs.modes import (
    KeywordTask,
    RunConfig,
    RunStats,
    ScrapeMode,
    build_run_config,
    keyword_tasks_from_args,
    parse_keyword_task,
    validate_runtime_args,
)
from xhs.models import SearchItem
from xhs.new_tab import NewTabScrapeStats, scrape_keyword_new_tabs
from xhs.parsing import compact_text, normalize_time, parse_count, split_time_and_ip
from xhs.preview import PreviewScrapeStats, scrape_keyword_previews
from xhs.runner import run
from xhs.runtime import sleep_random
from xhs.search import collect_search_items
from xhs.search_scan import extract_current_search_items, items_in_scan_band
from xhs.strategies import NewTabStrategy, PreviewOverlayStrategy, ScrapeStrategy, strategy_for_mode
from xhs.urls import build_search_url, extract_note_id, normalize_note_url


if __name__ == "__main__":
    raise SystemExit(main())
