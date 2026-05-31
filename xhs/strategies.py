from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Protocol

from playwright.sync_api import Page

from .csv_store import ResumeIndex
from .modes import ScrapeMode
from .new_tab import NewTabScrapeStats, scrape_keyword_new_tabs
from .preview import PreviewScrapeStats, scrape_keyword_previews


SearchPageStats = PreviewScrapeStats | NewTabScrapeStats


class ScrapeStrategy(Protocol):
    mode: ScrapeMode
    display_name: str

    def run_keyword(
        self,
        page: Page,
        keyword: str,
        max_notes: int,
        args: argparse.Namespace,
        resume_index: ResumeIndex,
        resume_keyword_scoped: bool,
        write_row: Callable[[dict[str, object]], None],
    ) -> SearchPageStats:
        ...


@dataclass(frozen=True)
class PreviewOverlayStrategy:
    mode: ScrapeMode = ScrapeMode.PREVIEW_OVERLAY
    display_name: str = "预览层"

    def run_keyword(
        self,
        page: Page,
        keyword: str,
        max_notes: int,
        args: argparse.Namespace,
        resume_index: ResumeIndex,
        resume_keyword_scoped: bool,
        write_row: Callable[[dict[str, object]], None],
    ) -> PreviewScrapeStats:
        return scrape_keyword_previews(
            page,
            keyword=keyword,
            max_notes=max_notes,
            args=args,
            resume_index=resume_index,
            resume_keyword_scoped=resume_keyword_scoped,
            write_row=write_row,
        )


@dataclass(frozen=True)
class NewTabStrategy:
    mode: ScrapeMode = ScrapeMode.NEW_TAB
    display_name: str = "新标签页"

    def run_keyword(
        self,
        page: Page,
        keyword: str,
        max_notes: int,
        args: argparse.Namespace,
        resume_index: ResumeIndex,
        resume_keyword_scoped: bool,
        write_row: Callable[[dict[str, object]], None],
    ) -> NewTabScrapeStats:
        return scrape_keyword_new_tabs(
            page,
            keyword=keyword,
            max_notes=max_notes,
            args=args,
            resume_index=resume_index,
            resume_keyword_scoped=resume_keyword_scoped,
            write_row=write_row,
        )


def strategy_for_mode(mode: ScrapeMode) -> ScrapeStrategy:
    if mode == ScrapeMode.PREVIEW_OVERLAY:
        return PreviewOverlayStrategy()
    if mode == ScrapeMode.NEW_TAB:
        return NewTabStrategy()
    raise ValueError(f"{mode.value} does not use a search-page scrape strategy.")
