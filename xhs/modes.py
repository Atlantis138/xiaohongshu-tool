from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum


class ScrapeMode(str, Enum):
    URL_PIPELINE = "url_pipeline"
    PREVIEW_OVERLAY = "preview_overlay"
    NEW_TAB = "new_tab"


GUI_TASK_LABELS = {
    "url_pipeline": "URL流程",
    "preview": "预览层",
    "new_tab": "新标签页",
}


GUI_URL_PIPELINE_STEP_LABELS = {
    "full": "完整执行：搜索并采详情",
    "search_only": "仅收集链接：搜索结果写入CSV",
    "from_csv": "链接CSV：逐条访问详情页",
}


@dataclass
class KeywordTask:
    keyword: str
    max_notes: int


@dataclass
class RunStats:
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    collected_any: bool = False
    stop_requested: bool = False


@dataclass(frozen=True)
class RunConfig:
    mode: ScrapeMode
    keyword_tasks: list[KeywordTask]
    output: str
    input_csv: str | None
    search_only: bool


def resolve_scrape_mode(args: argparse.Namespace) -> ScrapeMode:
    if getattr(args, "preview", False):
        return ScrapeMode.PREVIEW_OVERLAY
    if getattr(args, "new_tab", False):
        return ScrapeMode.NEW_TAB
    return ScrapeMode.URL_PIPELINE


def build_run_config(args: argparse.Namespace, keyword_tasks: list[KeywordTask]) -> RunConfig:
    return RunConfig(
        mode=resolve_scrape_mode(args),
        keyword_tasks=keyword_tasks,
        output=args.output,
        input_csv=args.input_csv,
        search_only=args.search_only,
    )


def parse_keyword_task(value: str) -> KeywordTask:
    text = value.strip()
    for separator in ["=", ":", "，", ",", "："]:
        if separator in text:
            keyword, count_text = text.rsplit(separator, 1)
            keyword = keyword.strip()
            count_text = count_text.strip()
            break
    else:
        raise argparse.ArgumentTypeError("关键词任务格式应为：关键词=数量，例如：城市露营=50")

    if not keyword:
        raise argparse.ArgumentTypeError("关键词任务中的关键词不能为空。")
    try:
        max_notes = int(count_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("关键词任务中的数量必须是整数。") from exc
    if max_notes <= 0:
        raise argparse.ArgumentTypeError("关键词任务中的数量必须大于 0。")
    return KeywordTask(keyword=keyword, max_notes=max_notes)


def keyword_tasks_from_args(args: argparse.Namespace) -> list[KeywordTask]:
    tasks = list(args.keyword_task or [])
    if tasks:
        return tasks
    if args.keyword:
        return [KeywordTask(keyword=args.keyword, max_notes=args.max_notes)]
    return []


def validate_runtime_args(args: argparse.Namespace) -> list[str]:
    warnings: list[str] = []
    preview_mode = bool(getattr(args, "preview", False))
    new_tab_mode = bool(getattr(args, "new_tab", False))
    if args.keyword_task and args.input_csv:
        raise ValueError("--keyword-task 不能与 --input-csv 同时使用；多关键词任务需要从搜索页开始。")
    if preview_mode and args.input_csv:
        raise ValueError("--preview 只能从搜索页点击预览采集，不能与 --input-csv 同时使用。")
    if new_tab_mode and args.input_csv:
        raise ValueError("--new-tab 只能从搜索页打开新标签页采集，不能与 --input-csv 同时使用。")
    if preview_mode and args.search_only:
        raise ValueError("--preview 不能与 --search-only 同时使用。")
    if new_tab_mode and args.search_only:
        raise ValueError("--new-tab 不能与 --search-only 同时使用。")
    if preview_mode and new_tab_mode:
        raise ValueError("--preview 不能与 --new-tab 同时使用。")
    if args.max_delay < args.min_delay:
        raise ValueError("--max-delay 不能小于 --min-delay。")
    if args.rest_every == 0 and args.rest_minutes > 0:
        warnings.append("--rest-every 为 0 时不会触发定期休息，--rest-minutes 将被忽略。")
    if args.rest_every > 0 and args.rest_minutes == 0:
        warnings.append("--rest-minutes 为 0 时不会真正休息，只会重置休息计数。")
    if args.max_runtime_minutes > 0 and args.rest_every > 0 and args.rest_minutes >= args.max_runtime_minutes:
        warnings.append("--rest-minutes 不小于 --max-runtime-minutes；一次定期休息可能覆盖整个运行时长。")
    if preview_mode and args.restart_every > 0:
        warnings.append("预览层模式依赖当前搜索页状态，暂不执行 --restart-every；本次已忽略定期重启。")
        args.restart_every = 0
    if new_tab_mode and args.restart_every > 0:
        warnings.append("新标签页模式依赖当前搜索页状态，暂不执行 --restart-every；本次已忽略定期重启。")
        args.restart_every = 0
    if args.search_only:
        ignored = []
        if args.rest_every > 0:
            ignored.append("--rest-every/--rest-minutes")
        if args.restart_every > 0:
            ignored.append("--restart-every")
        if args.max_runtime_minutes > 0:
            ignored.append("--max-runtime-minutes")
        if ignored:
            warnings.append("--search-only 只采搜索页链接，不进入详情循环；" + "、".join(ignored) + " 不会生效。")
    if args.headless:
        warnings.append("--headless 下连续错误暂停仍会等待确认，但无法人工接管可视浏览器。")
    return warnings
