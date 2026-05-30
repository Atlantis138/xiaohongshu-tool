from __future__ import annotations

from datetime import datetime
from pathlib import Path


LOG_FILE: Path | None = None


def now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def setup_log(log_file: str | None) -> None:
    global LOG_FILE
    if not log_file:
        LOG_FILE = None
        return
    LOG_FILE = Path(log_file)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    text = f"[{now_text()}] {message}"
    print(message)
    if LOG_FILE is None:
        return
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
