from __future__ import annotations

BASE_URL = "https://www.xiaohongshu.com"


DEFAULT_PROFILE_DIR = ".xhs_browser"


DEFAULT_OUTPUT = "data/xhs_notes.csv"


DEFAULT_LOG_FILE = "data/xhs_scraper.log"


CSV_COLUMNS = [
    "keyword",
    "note_id",
    "url",
    "search_index",
    "title",
    "content",
    "author_name",
    "post_time",
    "ip_location",
    "liked_count",
    "collected_count",
    "comment_count",
    "scraped_at",
    "status",
    "error",
]
