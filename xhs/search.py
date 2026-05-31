from __future__ import annotations

from playwright.sync_api import Page

from .browser import ensure_not_checkpoint
from .logging_utils import log
from .models import SearchItem
from .search_scan import extract_current_search_items, merge_search_item
from .urls import build_search_url


def collect_search_items(
    page: Page,
    keyword: str,
    max_notes: int,
    max_scrolls: int,
    scroll_delay: float,
    stagnant_limit: int,
    scroll_pixels: int,
    search_settle_ms: int,
    ignore_checkpoint: bool = False,
) -> list[SearchItem]:
    search_url = build_search_url(keyword)
    log(f"打开搜索页：{search_url}")
    page.goto(search_url, wait_until="domcontentloaded")
    page.wait_for_timeout(search_settle_ms)
    if not ensure_not_checkpoint(page, ignore_checkpoint, "搜索页"):
        return []

    items: dict[str, SearchItem] = {}
    stagnant_rounds = 0

    for round_index in range(1, max_scrolls + 1):
        before = len(items)
        for incoming in extract_current_search_items(page, keyword):
            key = incoming.note_id or incoming.url
            if not key:
                continue
            if key not in items:
                items[key] = incoming
                continue

            merge_search_item(items[key], incoming)

        after = len(items)
        log(f"搜索页滚动 {round_index}/{max_scrolls}，已发现 {after} 条笔记链接。")
        if after >= max_notes:
            break

        stagnant_rounds = stagnant_rounds + 1 if after == before else 0
        if stagnant_rounds >= stagnant_limit:
            log("连续多轮没有发现新链接，停止滚动。")
            break

        page.mouse.wheel(0, scroll_pixels)
        page.wait_for_timeout(int(scroll_delay * 1000))
        if not ensure_not_checkpoint(page, ignore_checkpoint, "搜索页滚动后"):
            break

    return list(items.values())[:max_notes]
