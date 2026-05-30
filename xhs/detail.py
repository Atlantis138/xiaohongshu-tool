from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from .browser import detect_checkpoint
from .extractors import EXTRACT_NOTE_JS
from .logging_utils import now_text
from .models import SearchItem
from .parsing import compact_text, normalize_time, parse_count, split_time_and_ip


def merge_extraction(extracted: dict[str, Any]) -> dict[str, Any]:
    dom = extracted.get("dom") or {}
    state_candidates = extracted.get("state_candidates") or []
    state = state_candidates[0] if state_candidates else {}

    row: dict[str, Any] = {}
    for field in [
        "title",
        "content",
        "author_name",
        "post_time",
        "ip_location",
        "raw_liked_count",
        "raw_collected_count",
        "raw_comment_count",
    ]:
        row[field] = state.get(field) or dom.get(field) or ""

    if not row["title"]:
        row["title"] = dom.get("meta_title") or ""
    if not row["content"]:
        row["content"] = dom.get("meta_description") or ""
    if row["content"]:
        title_match = re.search(r"标题[:：]\s*(?P<title>.+?)\s+正文[:：]\s*(?P<content>.+)", str(row["content"]), re.S)
        if title_match and (not row["title"] or row["title"] == dom.get("meta_title")):
            row["title"] = title_match.group("title")
            row["content"] = title_match.group("content")

    row["post_time"] = normalize_time(row["post_time"])
    row["post_time"], row["ip_location"] = split_time_and_ip(row["post_time"], row["ip_location"])

    for field in ["title", "content", "author_name", "post_time", "ip_location"]:
        row[field] = compact_text(row[field])
    row["title"] = re.sub(r"\s*-\s*小红书\s*$", "", row["title"]).strip()

    for field in ["raw_liked_count", "raw_collected_count", "raw_comment_count"]:
        row[field] = compact_text(row[field], max_len=100)

    row["liked_count"] = parse_count(row["raw_liked_count"])
    row["collected_count"] = parse_count(row["raw_collected_count"])
    row["comment_count"] = parse_count(row["raw_comment_count"])
    return row


def click_expand_buttons(page: Page) -> None:
    for label in ["展开", "更多"]:
        try:
            locator = page.get_by_text(label, exact=True).first
            if locator.count() > 0:
                locator.click(timeout=1000)
                page.wait_for_timeout(500)
        except Exception:
            continue


def save_debug_files(
    debug_dir: Path,
    note_id: str,
    page: Page,
    extracted: dict[str, Any] | None = None,
    suffix: str = "",
) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    key = note_id or re.sub(r"\W+", "_", page.url)[-80:]
    suffix_text = f"_{suffix}" if suffix else ""
    html_path = debug_dir / f"{key}{suffix_text}.html"
    html_path.write_text(page.content(), encoding="utf-8")
    if extracted is not None:
        json_path = debug_dir / f"{key}{suffix_text}.json"
        json_path.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")


def build_base_note_row(item: SearchItem, keyword: str) -> dict[str, Any]:
    row_keyword = item.source_keyword or keyword
    return {
        "keyword": row_keyword,
        "note_id": item.note_id,
        "url": item.url,
        "title": item.source_title,
        "author_name": item.source_author_name,
        "raw_liked_count": item.source_raw_liked_count,
        "liked_count": parse_count(item.source_raw_liked_count),
        "search_index": item.search_index,
        "source_title": item.source_title,
        "source_author_name": item.source_author_name,
        "source_raw_liked_count": item.source_raw_liked_count,
        "source_liked_count": parse_count(item.source_raw_liked_count),
        "scraped_at": now_text(),
        "status": "ok",
        "error": "",
    }


def scrape_note_detail(
    context: BrowserContext,
    item: SearchItem,
    keyword: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    page = context.new_page()
    row = build_base_note_row(item, keyword)
    try:
        page.goto(item.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        row = scrape_open_note_page(page, item, keyword, args)
    except Exception as exc:
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
        if args.debug_on_error:
            try:
                save_debug_files(Path(args.debug_dir), item.note_id, page, suffix="error")
            except Exception:
                pass
    finally:
        page.close()
    return row


def scrape_open_note_page(
    page: Page,
    item: SearchItem,
    keyword: str,
    args: argparse.Namespace,
    debug_suffix: str = "",
) -> dict[str, Any]:
    row = build_base_note_row(item, keyword)
    try:
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(1500)
        marker = detect_checkpoint(page)
        if marker and not args.ignore_checkpoint:
            row["status"] = "checkpoint"
            row["error"] = f"Detected login/verification/access checkpoint: {marker}"
            if args.debug_on_error:
                save_debug_files(Path(args.debug_dir), item.note_id, page, suffix=debug_suffix or "checkpoint")
            return row
        click_expand_buttons(page)

        extracted = page.evaluate(EXTRACT_NOTE_JS, item.note_id)
        details = merge_extraction(extracted)
        if item.source_author_name:
            details["author_name"] = item.source_author_name
        extracted_dom = extracted.get("dom") or {}
        if item.source_title and (
            not details.get("title") or details.get("title") == extracted_dom.get("meta_title")
        ):
            details["title"] = item.source_title
        if item.source_raw_liked_count and not details.get("raw_liked_count"):
            details["raw_liked_count"] = item.source_raw_liked_count
            details["liked_count"] = parse_count(item.source_raw_liked_count)
        row.update(details)
        if args.debug:
            save_debug_files(Path(args.debug_dir), item.note_id, page, extracted, suffix=debug_suffix)
    except Exception as exc:
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
        if args.debug_on_error:
            try:
                save_debug_files(Path(args.debug_dir), item.note_id, page, suffix=debug_suffix or "error")
            except Exception:
                pass
    return row
