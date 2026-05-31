from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .browser import ensure_not_checkpoint, wait_for_manual_takeover
from .csv_store import ResumeIndex
from .detail import build_base_note_row, scrape_open_note_page
from .logging_utils import log
from .models import SearchItem
from .runtime import sleep_random
from .search_scan import (
    capture_scroll_y,
    extract_current_search_items,
    item_link_selectors,
    items_in_scan_band,
    restore_scroll_y,
    scroll_locator_into_view,
    scroll_search_page_forward,
)
from .urls import build_search_url


@dataclass
class NewTabScrapeStats:
    discovered_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    written_count: int = 0
    stopped_by_checkpoint: bool = False
    stopped_by_user: bool = False


def _open_item_new_tab(page: Page, item: SearchItem, timeout_ms: int) -> Page | None:
    timeout = min(timeout_ms, 15000)
    for selector in item_link_selectors(item):
        locator = None
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            scroll_locator_into_view(locator)
            with page.context.expect_page(timeout=timeout) as page_info:
                locator.click(button="middle", timeout=5000)
            detail_page = page_info.value
            detail_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            return detail_page
        except Exception:
            pass

        modifier = "Meta" if sys.platform == "darwin" else "Control"
        try:
            if locator is None or locator.count() == 0:
                continue
            scroll_locator_into_view(locator)
            with page.context.expect_page(timeout=timeout) as page_info:
                locator.click(modifiers=[modifier], timeout=5000)
            detail_page = page_info.value
            detail_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            return detail_page
        except Exception:
            continue

    return None


def scrape_keyword_new_tabs(
    page: Page,
    keyword: str,
    max_notes: int,
    args: argparse.Namespace,
    resume_index: ResumeIndex,
    resume_keyword_scoped: bool,
    write_row: Callable[[dict[str, Any]], None],
) -> NewTabScrapeStats:
    search_url = build_search_url(keyword)
    log(f"打开搜索页（新标签页采集）：{search_url}")
    page.goto(search_url, wait_until="domcontentloaded")
    page.wait_for_timeout(args.search_settle_ms)
    stats = NewTabScrapeStats()
    if not ensure_not_checkpoint(page, args.ignore_checkpoint, "搜索页"):
        stats.stopped_by_checkpoint = True
        return stats

    seen_keys: dict[str, SearchItem] = {}
    attempted_keys: set[str] = set()
    stagnant_rounds = 0
    consecutive_errors = 0
    processed_since_rest = 0
    start_time = time.monotonic()

    for round_index in range(1, args.max_scrolls + 1):
        if args.max_runtime_minutes > 0:
            elapsed_minutes = (time.monotonic() - start_time) / 60
            if elapsed_minutes >= args.max_runtime_minutes:
                log(f"达到最大运行时长 {args.max_runtime_minutes} 分钟，已平稳停止。")
                break

        current_items = extract_current_search_items(page, keyword)
        scan_items = items_in_scan_band(current_items)
        before = len(seen_keys)
        for item in current_items:
            key = item.note_id or item.url
            if key and key not in seen_keys:
                seen_keys[key] = item
        stats.discovered_count = len(seen_keys)
        processed_this_round = 0
        log(
            f"新标签页模式滚动 {round_index}/{args.max_scrolls}，"
            f"已发现 {stats.discovered_count} 条笔记，本屏待检查 {len(scan_items)} 条。"
        )

        for item in scan_items:
            if stats.written_count + stats.skipped_count >= max_notes:
                break
            key = item.note_id or item.url
            if not key or key in attempted_keys:
                continue
            attempted_keys.add(key)

            current_position = stats.written_count + stats.skipped_count + 1
            if resume_index.contains(keyword, item, keyword_scoped=resume_keyword_scoped):
                stats.skipped_count += 1
                processed_this_round += 1
                log(f"[{current_position}/{max_notes}] 跳过已存在：{key}")
                continue

            row = build_base_note_row(item, keyword)
            detail_page: Page | None = None
            saved_scroll_y = capture_scroll_y(page)
            log(f"[{current_position}/{max_notes}] 新标签页采集：{item.url}")
            try:
                detail_page = _open_item_new_tab(page, item, args.timeout_ms)
                if detail_page is None:
                    row["status"] = "error"
                    row["error"] = "未能从搜索页卡片打开新标签页。"
                else:
                    row = scrape_open_note_page(detail_page, item, keyword, args, debug_suffix="newtab")
            except Exception as exc:
                row["status"] = "error"
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if detail_page is not None:
                    try:
                        detail_page.close()
                    except Exception:
                        pass
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                restore_scroll_y(page, saved_scroll_y)

            write_row(row)
            resume_index.add(keyword, item)
            stats.written_count += 1
            processed_this_round += 1
            processed_since_rest += 1
            if row.get("status") == "ok":
                stats.success_count += 1
                consecutive_errors = 0
            else:
                stats.failed_count += 1
                consecutive_errors += 1
                log(f"新标签页采集异常：{row.get('status')} {row.get('error')}")
                if consecutive_errors >= args.max_errors:
                    should_continue = wait_for_manual_takeover(
                        page.context,
                        args,
                        f"连续 {consecutive_errors} 条新标签页采集失败，已暂停任务。",
                        page=page,
                    )
                    consecutive_errors = 0
                    if not should_continue:
                        stats.stopped_by_user = True
                        break
                elif args.error_delay > 0:
                    time.sleep(args.error_delay)

            has_more_work = stats.written_count + stats.skipped_count < max_notes
            if args.rest_every > 0 and processed_since_rest >= args.rest_every and has_more_work:
                rest_seconds = max(0, args.rest_minutes * 60)
                processed_since_rest = 0
                if rest_seconds > 0:
                    log(f"已处理 {args.rest_every} 条新标签页笔记，休息 {args.rest_minutes} 分钟。")
                    time.sleep(rest_seconds)
            if has_more_work:
                sleep_random(args.min_delay, args.max_delay)

        if stats.written_count + stats.skipped_count >= max_notes or stats.stopped_by_checkpoint or stats.stopped_by_user:
            break

        stagnant_rounds = stagnant_rounds + 1 if len(seen_keys) == before and processed_this_round == 0 else 0
        if stagnant_rounds >= args.stagnant_limit:
            log("连续多轮没有发现新笔记，停止滚动。")
            break

        scroll_search_page_forward(page, args)
        page.wait_for_timeout(int(args.scroll_delay * 1000))
        if not ensure_not_checkpoint(page, args.ignore_checkpoint, "搜索页滚动后"):
            stats.stopped_by_checkpoint = True
            break

    return stats
