from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import CSV_COLUMNS
from .logging_utils import now_text
from .models import SearchItem
from .parsing import compact_text, parse_count
from .urls import extract_note_id, normalize_note_url


def item_resume_key(note_id: str = "", url: str = "") -> str:
    normalized_url = normalize_note_url(url or "")
    clean_note_id = str(note_id or "").strip()
    return clean_note_id or extract_note_id(normalized_url) or normalized_url


@dataclass
class ResumeIndex:
    global_keys: set[str] = field(default_factory=set)
    keyword_keys: set[tuple[str, str]] = field(default_factory=set)
    row_count: int = 0

    def contains(self, keyword: str, item: SearchItem, keyword_scoped: bool = False) -> bool:
        key = item_resume_key(item.note_id, item.url)
        if not key:
            return False
        return key in self.global_keys

    def add(self, keyword: str, item: SearchItem) -> None:
        key = item_resume_key(item.note_id, item.url)
        if not key:
            return
        row_keyword = (item.source_keyword or keyword or "").strip()
        is_new = key not in self.global_keys
        self.global_keys.add(key)
        self.keyword_keys.add((row_keyword, key))
        if is_new:
            self.row_count += 1

    def contains_row(self, row: dict[str, Any]) -> bool:
        key = row_resume_key(row)
        return bool(key and key in self.global_keys)

    def add_row(self, row: dict[str, Any]) -> None:
        key = row_resume_key(row)
        if not key:
            return
        keyword = str(row.get("keyword") or "").strip()
        is_new = key not in self.global_keys
        self.global_keys.add(key)
        self.keyword_keys.add((keyword, key))
        if is_new:
            self.row_count += 1


def row_resume_key(row: dict[str, Any]) -> str:
    return item_resume_key(str(row.get("note_id") or ""), str(row.get("url") or ""))


def normalize_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    safe_row = {
        column: "" if row.get(column, "") is None else row.get(column, "")
        for column in CSV_COLUMNS
    }
    url = normalize_note_url(str(safe_row.get("url") or ""))
    note_id = str(safe_row.get("note_id") or "").strip() or extract_note_id(url)
    safe_row["url"] = url
    safe_row["note_id"] = note_id
    return safe_row


def row_has_content(row: dict[str, Any]) -> bool:
    return any(str(row.get(column, "")).strip() for column in CSV_COLUMNS)


def load_resume_index(output_path: Path) -> ResumeIndex:
    index = ResumeIndex()
    if not output_path.exists():
        return index
    with output_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            safe_row = normalize_csv_row(row)
            if not row_has_content(safe_row):
                continue
            index.add_row(safe_row)
    return index


def existing_keys(output_path: Path) -> set[str]:
    return load_resume_index(output_path).global_keys


def csv_header_matches(output_path: Path) -> bool:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return True
    with output_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return True
    return header == CSV_COLUMNS


def _ensure_append_boundary(output_path: Path) -> None:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return
    with output_path.open("rb+") as f:
        f.seek(-1, 2)
        last_byte = f.read(1)
        if last_byte not in {b"\n", b"\r"}:
            f.write(b"\n")


def append_rows(output_path: Path, rows: list[dict[str, Any]], overwrite: bool = False) -> int:
    safe_rows = []
    for row in rows:
        safe_row = normalize_csv_row(row)
        if row_has_content(safe_row):
            safe_rows.append(safe_row)
    if not safe_rows:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    append_to_existing = output_path.exists() and not overwrite
    has_existing_content = append_to_existing and output_path.stat().st_size > 0
    if has_existing_content and not csv_header_matches(output_path):
        raise ValueError(f"CSV header mismatch: {output_path}. Use --overwrite or choose a new output file.")
    if has_existing_content:
        _ensure_append_boundary(output_path)
    mode = "a" if append_to_existing else "w"
    with output_path.open(mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if not has_existing_content:
            writer.writeheader()
        for safe_row in safe_rows:
            writer.writerow(safe_row)
    return len(safe_rows)


def load_search_items_from_csv(
    input_path: Path,
    max_notes: int,
    start_row: int = 1,
    end_row: int | None = None,
) -> list[SearchItem]:
    items: dict[str, SearchItem] = {}
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=1):
            if row_number < start_row:
                continue
            if end_row is not None and row_number > end_row:
                break
            url = normalize_note_url(row.get("url", ""))
            note_id = row.get("note_id") or extract_note_id(url)
            key = note_id or url
            if not key or not url or key in items:
                continue
            items[key] = SearchItem(
                url=url,
                note_id=note_id,
                source_keyword=row.get("keyword", ""),
                source_title=row.get("title", ""),
                source_author_name=row.get("author_name", ""),
                source_raw_liked_count=row.get("liked_count", ""),
                search_index=row.get("search_index", ""),
            )
            if len(items) >= max_notes:
                break
    return list(items.values())


def search_item_to_row(keyword: str, item: SearchItem) -> dict[str, Any]:
    raw_liked_count = compact_text(item.source_raw_liked_count, max_len=100)
    row_keyword = item.source_keyword or keyword
    return {
        "keyword": row_keyword,
        "note_id": item.note_id,
        "url": item.url,
        "search_index": item.search_index,
        "title": compact_text(item.source_title),
        "author_name": compact_text(item.source_author_name),
        "liked_count": parse_count(raw_liked_count),
        "scraped_at": now_text(),
        "status": "search_only",
        "error": "",
    }
