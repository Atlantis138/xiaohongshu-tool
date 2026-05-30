from __future__ import annotations

from playwright.sync_api import Page

from .browser import ensure_not_checkpoint
from .extractors import EXTRACT_SEARCH_ITEMS_JS
from .logging_utils import log
from .models import SearchItem
from .urls import build_search_url, extract_note_id, normalize_note_url


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
        found = page.evaluate(EXTRACT_SEARCH_ITEMS_JS)

        before = len(items)
        for item in found:
            url = normalize_note_url(item.get("url", ""))
            note_id = extract_note_id(url)
            key = note_id or url
            if not key:
                continue

            incoming = SearchItem(
                url=url,
                note_id=note_id,
                source_keyword=keyword,
                source_title=item.get("title", ""),
                source_author_name=item.get("author_name", ""),
                source_raw_liked_count=item.get("raw_liked_count", ""),
                search_index=item.get("search_index", ""),
            )
            if key not in items:
                items[key] = incoming
                continue

            current = items[key]
            current_has_token = "xsec_token=" in current.url
            incoming_has_token = "xsec_token=" in incoming.url
            if incoming_has_token and not current_has_token:
                current.url = incoming.url
            current.source_title = current.source_title or incoming.source_title
            current.source_author_name = current.source_author_name or incoming.source_author_name
            current.source_raw_liked_count = current.source_raw_liked_count or incoming.source_raw_liked_count
            current.search_index = current.search_index or incoming.search_index

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
