from __future__ import annotations

import argparse

from playwright.sync_api import Page

from .extractors import EXTRACT_SEARCH_ITEMS_JS
from .models import SearchItem
from .urls import extract_note_id, normalize_note_url


def css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def extract_current_search_items(page: Page, keyword: str) -> list[SearchItem]:
    found = page.evaluate(EXTRACT_SEARCH_ITEMS_JS)
    items: dict[str, SearchItem] = {}
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
            viewport_top=float(item.get("viewport_top") or 0),
            viewport_bottom=float(item.get("viewport_bottom") or 0),
            document_top=float(item.get("document_top") or 0),
            document_bottom=float(item.get("document_bottom") or 0),
            viewport_height=float(item.get("viewport_height") or 0),
        )
        if key not in items:
            items[key] = incoming
            continue
        merge_search_item(items[key], incoming)
    return sorted(items.values(), key=lambda item: (item.document_top or 0, item.search_index or ""))


def merge_search_item(current: SearchItem, incoming: SearchItem) -> None:
    current_has_token = "xsec_token=" in current.url
    incoming_has_token = "xsec_token=" in incoming.url
    if incoming_has_token and not current_has_token:
        current.url = incoming.url
    current.source_title = current.source_title or incoming.source_title
    current.source_author_name = current.source_author_name or incoming.source_author_name
    current.source_raw_liked_count = current.source_raw_liked_count or incoming.source_raw_liked_count
    current.search_index = current.search_index or incoming.search_index
    if incoming.document_top and (not current.document_top or incoming.document_top < current.document_top):
        current.viewport_top = incoming.viewport_top
        current.viewport_bottom = incoming.viewport_bottom
        current.document_top = incoming.document_top
        current.document_bottom = incoming.document_bottom
        current.viewport_height = incoming.viewport_height


def items_in_scan_band(items: list[SearchItem]) -> list[SearchItem]:
    if not items:
        return []
    viewport_height = max((item.viewport_height for item in items if item.viewport_height), default=0)
    if viewport_height <= 0:
        return items
    top_margin = 120
    below_viewport_margin = 180
    band = [
        item
        for item in items
        if item.viewport_bottom >= -top_margin and item.viewport_top <= viewport_height + below_viewport_margin
    ]
    return band or items[:1]


def capture_scroll_y(page: Page) -> float:
    try:
        return float(page.evaluate("() => window.scrollY || document.documentElement.scrollTop || 0"))
    except Exception:
        return 0.0


def restore_scroll_y(page: Page, scroll_y: float) -> None:
    try:
        page.evaluate("(y) => window.scrollTo(0, y)", scroll_y)
        page.wait_for_timeout(250)
    except Exception:
        pass


def scroll_search_page_forward(page: Page, args: argparse.Namespace) -> None:
    try:
        viewport_height = float(page.evaluate("() => window.innerHeight || document.documentElement.clientHeight || 900"))
    except Exception:
        viewport_height = 900.0
    requested = args.scroll_pixels if args.scroll_pixels > 0 else int(viewport_height * 0.65)
    delta = max(300, min(int(requested), int(viewport_height * 0.65)))
    page.evaluate("(dy) => window.scrollBy(0, dy)", delta)


def item_link_selectors(item: SearchItem) -> list[str]:
    note_id = item.note_id
    selectors: list[str] = []
    if item.search_index:
        index = css_string(item.search_index)
        if note_id:
            note = css_string(note_id)
            selectors.extend(
                [
                    f"section.note-item[data-index='{index}'] a.cover[href*='{note}']",
                    f"section.note-item[data-index='{index}'] a.title[href*='{note}']",
                    f"section[data-index='{index}'] a[href*='{note}']",
                ]
            )
        selectors.append(f"section.note-item[data-index='{index}'] a.cover")
    if note_id:
        note = css_string(note_id)
        selectors.extend(
            [
                f"a.cover[href*='{note}']",
                f"a.title[href*='{note}']",
                f"a[href*='/search_result/{note}']",
                f"a[href*='/explore/{note}']",
            ]
        )
    return selectors


def scroll_locator_into_view(locator) -> None:
    locator.evaluate(
        r"""
        (el) => {
          const rect = el.getBoundingClientRect();
          const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 900;
          if (rect.top < 80 || rect.bottom > viewportHeight - 80) {
            el.scrollIntoView({ block: "center", inline: "nearest" });
          }
        }
        """
    )


def click_search_item(page: Page, item: SearchItem) -> bool:
    for selector in item_link_selectors(item):
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            scroll_locator_into_view(locator)
            locator.click(timeout=5000)
            return True
        except Exception:
            continue
    return False
