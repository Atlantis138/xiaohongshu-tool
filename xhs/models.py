from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchItem:
    url: str
    note_id: str
    source_keyword: str = ""
    source_title: str = ""
    source_author_name: str = ""
    source_raw_liked_count: str = ""
    search_index: str = ""
    viewport_top: float = 0.0
    viewport_bottom: float = 0.0
    document_top: float = 0.0
    document_bottom: float = 0.0
    viewport_height: float = 0.0
