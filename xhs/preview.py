from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .browser import detect_checkpoint, ensure_not_checkpoint, wait_for_manual_takeover
from .csv_store import ResumeIndex
from .detail import build_base_note_row, click_expand_buttons, merge_extraction, save_debug_files
from .extractors import EXTRACT_NOTE_JS
from .logging_utils import log
from .models import SearchItem
from .parsing import parse_count
from .runtime import sleep_random
from .search_scan import (
    capture_scroll_y,
    click_search_item,
    extract_current_search_items,
    items_in_scan_band,
    restore_scroll_y,
    scroll_search_page_forward,
)
from .urls import build_search_url


@dataclass
class PreviewScrapeStats:
    discovered_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    written_count: int = 0
    stopped_by_checkpoint: bool = False
    stopped_by_user: bool = False


def _preview_visible(page: Page) -> bool:
    try:
        return bool(
            page.evaluate(
                r"""
                () => {
                  const nodes = Array.from(document.querySelectorAll("#detail-desc, .note-scroller"));
                  return nodes.some((node) => {
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== "none"
                      && style.visibility !== "hidden"
                      && rect.width > 0
                      && rect.height > 0;
                  });
                }
                """
            )
        )
    except Exception:
        return False


def _wait_for_preview(page: Page, timeout_ms: int) -> bool:
    try:
        page.wait_for_selector(
            "#detail-desc, .note-scroller",
            state="visible",
            timeout=min(timeout_ms, 15000),
        )
        page.wait_for_timeout(1200)
        return True
    except PlaywrightTimeoutError:
        return False


def _close_preview(page: Page, search_url: str) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        if not _preview_visible(page):
            return
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            r"""
            () => {
              const nodes = Array.from(document.querySelectorAll(
                "button, [role='button'], [aria-label], [class*='close'], [class*='Close']"
              ));
              const visible = (node) => {
                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== "none"
                  && style.visibility !== "hidden"
                  && rect.width > 0
                  && rect.height > 0;
              };
              for (const node of nodes) {
                const text = `${node.getAttribute("aria-label") || ""} ${node.className || ""} ${node.innerText || ""}`.toLowerCase();
                if (visible(node) && (text.includes("close") || text.includes("关闭"))) {
                  node.click();
                  return true;
                }
              }
              return false;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(500)
        if not _preview_visible(page):
            return
    except Exception:
        pass

    try:
        page.go_back(wait_until="domcontentloaded", timeout=5000)
        page.wait_for_timeout(800)
    except Exception:
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass


def _apply_detail_fallbacks(row: dict[str, Any], item: SearchItem, extracted: dict[str, Any]) -> None:
    if item.source_author_name:
        row["author_name"] = item.source_author_name
    extracted_dom = extracted.get("dom") or {}
    if item.source_title and (
        not row.get("title") or row.get("title") == extracted_dom.get("meta_title")
    ):
        row["title"] = item.source_title
    if item.source_raw_liked_count and not row.get("raw_liked_count"):
        row["raw_liked_count"] = item.source_raw_liked_count
        row["liked_count"] = parse_count(item.source_raw_liked_count)


def scrape_keyword_previews(
    page: Page,
    keyword: str,
    max_notes: int,
    args: argparse.Namespace,
    resume_index: ResumeIndex,
    resume_keyword_scoped: bool,
    write_row: Callable[[dict[str, Any]], None],
) -> PreviewScrapeStats:
    search_url = build_search_url(keyword)
    log(f"打开搜索页（预览采集）：{search_url}")
    page.goto(search_url, wait_until="domcontentloaded")
    page.wait_for_timeout(args.search_settle_ms)
    stats = PreviewScrapeStats()
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
            f"预览模式滚动 {round_index}/{args.max_scrolls}，"
            f"已发现 {stats.discovered_count} 条笔记，本屏待检查 {len(scan_items)} 条。"
        )

        for item in scan_items:
            if stats.written_count + stats.skipped_count >= max_notes:
                break
            key = item.note_id or item.url
            if not key or key in attempted_keys:
                continue
            attempted_keys.add(key)

            if resume_index.contains(keyword, item, keyword_scoped=resume_keyword_scoped):
                current_position = stats.written_count + stats.skipped_count + 1
                stats.skipped_count += 1
                processed_this_round += 1
                log(f"[{current_position}/{max_notes}] 跳过已存在：{key}")
                continue

            row = build_base_note_row(item, keyword)
            current_position = stats.written_count + stats.skipped_count + 1
            log(f"[{current_position}/{max_notes}] 预览采集：{item.url}")
            preview_opened = False
            saved_scroll_y = capture_scroll_y(page)
            try:
                if not click_search_item(page, item):
                    row["status"] = "error"
                    row["error"] = "未能在当前搜索页 DOM 中点击到对应笔记卡片。"
                elif not _wait_for_preview(page, args.timeout_ms):
                    preview_opened = True
                    row["status"] = "error"
                    row["error"] = "点击卡片后未等待到预览层。"
                else:
                    preview_opened = True
                    marker = detect_checkpoint(page)
                    if marker and not args.ignore_checkpoint:
                        row["status"] = "checkpoint"
                        row["error"] = f"Detected login/verification/access checkpoint: {marker}"
                    else:
                        click_expand_buttons(page)
                        extracted = page.evaluate(EXTRACT_NOTE_JS, item.note_id)
                        details = merge_extraction(extracted)
                        row.update(details)
                        _apply_detail_fallbacks(row, item, extracted)
                        if args.debug:
                            save_debug_files(Path(args.debug_dir), item.note_id, page, extracted, suffix="preview")
            except Exception as exc:
                row["status"] = "error"
                row["error"] = f"{type(exc).__name__}: {exc}"
                if args.debug_on_error:
                    try:
                        save_debug_files(Path(args.debug_dir), item.note_id, page, suffix="preview_error")
                    except Exception:
                        pass
            finally:
                if preview_opened:
                    _close_preview(page, search_url)
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
                log(f"预览采集异常：{row.get('status')} {row.get('error')}")
                if consecutive_errors >= args.max_errors:
                    should_continue = wait_for_manual_takeover(
                        page.context,
                        args,
                        f"连续 {consecutive_errors} 条预览采集失败，已暂停任务。",
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
                    log(f"已处理 {args.rest_every} 条预览笔记，休息 {args.rest_minutes} 分钟。")
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
