from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def parse_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("，", "").replace("+", "")
    text = re.sub(r"(点赞|赞|收藏|评论|条|次)", "", text).strip()
    if not text or text in {"-", "--"}:
        return None

    multiplier = 1
    if "亿" in text:
        multiplier = 100_000_000
    elif "万" in text or "w" in text.lower():
        multiplier = 10_000
    elif "千" in text or "k" in text.lower():
        multiplier = 1_000

    number_match = re.search(r"\d+(?:\.\d+)?", text)
    if not number_match:
        return None
    return int(float(number_match.group(0)) * multiplier)


def normalize_time(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        try:
            return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="seconds")
        except (OSError, ValueError):
            return str(value)
    return str(value).strip()


def split_time_and_ip(post_time: str, ip_location: str = "") -> tuple[str, str]:
    text = (post_time or "").strip()
    ip = (ip_location or "").strip()
    if "IP属地" in text:
        left, right = text.split("IP属地", 1)
        text = left.strip()
        ip = ip or right.strip(" ：:").strip()
    if not ip:
        match = re.match(r"^(?P<time>.+?)\s+(?P<ip>[\u4e00-\u9fffA-Za-z·]{2,20})$", text)
        if match:
            text = match.group("time").strip()
            ip = match.group("ip").strip()
    return text, ip


def compact_text(value: Any, max_len: int = 20000) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:max_len]
