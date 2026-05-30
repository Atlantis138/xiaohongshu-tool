from __future__ import annotations

import re
from urllib.parse import quote, urlparse, urlunparse

from .config import BASE_URL


def build_search_url(keyword: str) -> str:
    return f"{BASE_URL}/search_result?keyword={quote(keyword)}&source=web_search_result_notes"


def extract_note_id(url: str) -> str:
    parsed = urlparse(url)
    patterns = [
        r"/explore/([A-Za-z0-9]+)",
        r"/search_result/([A-Za-z0-9]+)",
        r"/discovery/item/([A-Za-z0-9]+)",
        r"/items/([A-Za-z0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, parsed.path)
        if match:
            return match.group(1)
    query_match = re.search(r"(?:note_id|noteId)=([A-Za-z0-9]+)", parsed.query)
    return query_match.group(1) if query_match else ""


def normalize_note_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/"):
        url = BASE_URL + url
    parsed = urlparse(url)
    match = re.search(r"^/search_result/([A-Za-z0-9]+)$", parsed.path)
    if match:
        query_text = parsed.query
        if "xsec_token=" in query_text:
            if re.search(r"(^|&)xsec_source=(&|$)", query_text):
                query_text = re.sub(r"(^|&)xsec_source=(&|$)", r"\1xsec_source=pc_search\2", query_text)
            elif "xsec_source=" not in query_text:
                query_text = f"{query_text}&xsec_source=pc_search" if query_text else "xsec_source=pc_search"
            return urlunparse((parsed.scheme, parsed.netloc, f"/explore/{match.group(1)}", "", query_text, ""))
    return url
