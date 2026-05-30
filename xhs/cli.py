from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .browser import check_login_status, launch_context, run_login_only, wait_for_manual_takeover
from .config import DEFAULT_LOG_FILE, DEFAULT_OUTPUT, DEFAULT_PROFILE_DIR
from .csv_store import (
    ResumeIndex,
    append_rows,
    csv_header_matches,
    load_resume_index,
    load_search_items_from_csv,
    normalize_csv_row,
    row_has_content,
    row_resume_key,
    search_item_to_row,
)
from .detail import scrape_note_detail
from .logging_utils import log, setup_log
from .new_tab import scrape_keyword_new_tabs
from .preview import scrape_keyword_previews
from .runtime import sleep_random
from .search import collect_search_items


@dataclass
class KeywordTask:
    keyword: str
    max_notes: int


def parse_keyword_task(value: str) -> KeywordTask:
    text = value.strip()
    for separator in ["=", ":", "：", ",", "，"]:
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
    if args.input_start_row < 1:
        raise ValueError("--input-start-row 必须大于等于 1。")
    if args.input_end_row is not None and args.input_end_row < args.input_start_row:
        raise ValueError("--input-end-row 不能小于 --input-start-row。")
    if args.max_delay < args.min_delay:
        raise ValueError("--max-delay 不能小于 --min-delay。")
    if args.rest_every == 0 and args.rest_minutes > 0:
        warnings.append("--rest-every 为 0 时不会触发定期休息，--rest-minutes 将被忽略。")
    if args.rest_every > 0 and args.rest_minutes == 0:
        warnings.append("--rest-minutes 为 0 时不会真正休息，只会重置休息计数。")
    if args.max_runtime_minutes > 0 and args.rest_every > 0 and args.rest_minutes >= args.max_runtime_minutes:
        warnings.append("--rest-minutes 不小于 --max-runtime-minutes；一次定期休息可能覆盖整个运行时长。")
    if preview_mode and args.restart_every > 0:
        warnings.append("预览模式依赖当前搜索页状态，暂不执行 --restart-every；本次已忽略定期重启。")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Xiaohongshu keyword search note details into a local CSV."
    )
    parser.add_argument("--keyword", help="Search keyword, for example: 城市露营")
    parser.add_argument(
        "--keyword-task",
        action="append",
        type=parse_keyword_task,
        help="Repeatable multi-keyword task in KEYWORD=COUNT format, for example: --keyword-task 城市露营=50",
    )
    parser.add_argument("--max-notes", type=int, default=30, help="Maximum note detail pages to collect.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV path.")
    parser.add_argument("--input-csv", help="Read note URLs from a previous --search-only CSV instead of searching again.")
    parser.add_argument("--input-start-row", type=int, default=1, help="1-based first data row to read from --input-csv. Header is not counted.")
    parser.add_argument("--input-end-row", type=int, help="1-based last data row to read from --input-csv. Header is not counted.")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR, help="Persistent browser profile directory.")
    parser.add_argument("--login-only", action="store_true", help="Open browser for manual login and save session.")
    parser.add_argument("--check-login", action="store_true", help="Check whether the saved browser session appears usable.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode. Not recommended for login.")
    parser.add_argument("--slow-mo", type=int, default=0, help="Playwright slow motion in milliseconds.")
    parser.add_argument("--max-scrolls", type=int, default=25, help="Maximum scroll rounds on search page.")
    parser.add_argument("--stagnant-limit", type=int, default=8, help="Stop search scrolling after this many rounds without new links.")
    parser.add_argument("--scroll-pixels", type=int, default=2600, help="Pixels to scroll each search round.")
    parser.add_argument("--search-settle-ms", type=int, default=3000, help="Initial wait after opening the search page.")
    parser.add_argument("--scroll-delay", type=float, default=2.0, help="Delay after each search page scroll.")
    parser.add_argument("--search-only", action="store_true", help="Only collect search result cards and do not open detail pages.")
    parser.add_argument("--preview", action="store_true", help="Collect details by opening note previews on the search page instead of navigating to detail URLs.")
    parser.add_argument("--new-tab", action="store_true", help="Collect details by opening each search result card in a new tab and extracting the opened page.")
    parser.add_argument("--min-delay", type=float, default=3.0, help="Minimum delay between detail pages.")
    parser.add_argument("--max-delay", type=float, default=7.0, help="Maximum delay between detail pages.")
    parser.add_argument("--rest-every", type=int, default=100, help="Take a longer rest after this many detail pages. Use 0 to disable.")
    parser.add_argument("--rest-minutes", type=float, default=3.0, help="Long-rest duration in minutes.")
    parser.add_argument("--restart-every", type=int, default=200, help="Restart the browser context after this many detail pages. Use 0 to disable.")
    parser.add_argument("--max-runtime-minutes", type=float, default=0, help="Stop gracefully after this many minutes. Use 0 to disable.")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Page navigation timeout in milliseconds.")
    parser.add_argument("--max-errors", type=int, default=3, help="Pause for manual takeover after this many consecutive detail or preview errors.")
    parser.add_argument("--error-delay", type=float, default=20.0, help="Extra delay after a detail-page error.")
    parser.add_argument("--ignore-checkpoint", action="store_true", help="Continue even if a login, verification, or access checkpoint is detected.")
    parser.add_argument("--block-media", action="store_true", help="Block image, media, and font requests to reduce bandwidth.")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="Append run logs to this file. Use an empty string to disable.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing CSV instead of appending/resuming.")
    parser.add_argument("--debug", action="store_true", help="Save debug HTML and extraction JSON for each detail page.")
    parser.add_argument("--debug-on-error", action="store_true", help="Save debug HTML only for failed detail pages.")
    parser.add_argument("--debug-dir", default="data/debug", help="Directory for debug files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_log(args.log_file)
    keyword_tasks = keyword_tasks_from_args(args)
    if not args.login_only and not args.check_login and not keyword_tasks and not args.input_csv:
        print("请提供 --keyword、--keyword-task，或使用 --input-csv 读取已保存链接，或使用 --login-only 先完成登录。", file=sys.stderr)
        return 2
    try:
        runtime_warnings = validate_runtime_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for warning in runtime_warnings:
        log(f"参数提示：{warning}")

    playwright = None
    context = None
    start_time = time.monotonic()
    processed_since_restart = 0
    processed_since_rest = 0
    success_count = 0
    failed_count = 0
    skipped_count = 0
    stop_requested = False
    wrote_output = False
    collected_any = False
    try:
        output_path = Path(args.output)
        input_path = Path(args.input_csv) if args.input_csv else None
        if input_path and input_path.resolve() == output_path.resolve():
            print("--input-csv 和 --output 不能是同一个文件；请把搜索链接表和详情结果表分开。", file=sys.stderr)
            return 2
        if output_path.exists() and not args.overwrite and not csv_header_matches(output_path):
            print(f"输出 CSV 表头与当前版本不匹配：{output_path}。请使用 --overwrite 或换一个输出文件。", file=sys.stderr)
            return 2

        playwright, context = launch_context(args)
        if args.login_only:
            run_login_only(context)
            return 0
        if args.check_login:
            return 0 if check_login_status(context) else 1

        resume_index = ResumeIndex() if args.overwrite else load_resume_index(output_path)
        resume_keyword_scoped = False
        if args.overwrite:
            log("断点续跑：已关闭，因为启用了 --overwrite。")
        elif resume_index.row_count:
            log(f"断点续跑：已从输出 CSV 读取 {resume_index.row_count} 条已有记录，按 note_id 全局匹配，命中后将快速跳过。")
        else:
            log("断点续跑：输出 CSV 中没有可用于跳过的已有记录。")

        def write_output_rows(rows: list[dict[str, object]]) -> int:
            nonlocal wrote_output, skipped_count
            safe_rows: list[dict[str, object]] = []
            for raw_row in rows:
                safe_row = normalize_csv_row(raw_row)
                if not row_has_content(safe_row):
                    continue
                key = row_resume_key(safe_row)
                if key and not args.overwrite and resume_index.contains_row(safe_row):
                    skipped_count += 1
                    log(f"跳过重复输出：{key}")
                    continue
                safe_rows.append(safe_row)
                if key:
                    resume_index.add_row(safe_row)

            if not safe_rows:
                return 0
            written_count = append_rows(output_path, safe_rows, overwrite=args.overwrite and not wrote_output)
            wrote_output = True
            return written_count

        if input_path:
            items = load_search_items_from_csv(
                input_path,
                args.max_notes,
                start_row=args.input_start_row,
                end_row=args.input_end_row,
            )
            range_text = f"第 {args.input_start_row} 行起"
            if args.input_end_row is not None:
                range_text += f"至第 {args.input_end_row} 行"
            log(f"从链接 CSV {range_text}读取 {len(items)} 条候选笔记：{input_path}")
            if args.search_only:
                if not items:
                    log("没有从输入 CSV 读取到笔记链接。")
                    return 1
                rows = [search_item_to_row(args.keyword or "", item) for item in items]
                written = write_output_rows(rows)
                log(f"已完成链接 CSV 转存，写入 {written} 行。CSV 已保存到：{output_path.resolve()}")
                return 0
            keyword_batches = [(args.keyword or "", items)]
        else:
            keyword_batches = []
            if args.preview or args.new_tab:
                def write_search_page_detail_row(row: dict[str, object]) -> None:
                    write_output_rows([row])

                for task_index, task in enumerate(keyword_tasks, start=1):
                    mode_text = "预览" if args.preview else "新标签页"
                    log(f"开始关键词{mode_text}任务 {task_index}/{len(keyword_tasks)}：{task.keyword}，目标 {task.max_notes} 条。")
                    search_page = context.new_page()
                    try:
                        if args.preview:
                            stats = scrape_keyword_previews(
                                search_page,
                                keyword=task.keyword,
                                max_notes=task.max_notes,
                                args=args,
                                resume_index=resume_index,
                                resume_keyword_scoped=resume_keyword_scoped,
                                write_row=write_search_page_detail_row,
                            )
                        else:
                            stats = scrape_keyword_new_tabs(
                                search_page,
                                keyword=task.keyword,
                                max_notes=task.max_notes,
                                args=args,
                                resume_index=resume_index,
                                resume_keyword_scoped=resume_keyword_scoped,
                                write_row=write_search_page_detail_row,
                            )
                    finally:
                        search_page.close()
                    if stats.discovered_count > 0 or stats.written_count > 0 or stats.skipped_count > 0:
                        collected_any = True
                    success_count += stats.success_count
                    failed_count += stats.failed_count
                    skipped_count += stats.skipped_count
                    log(
                        f"关键词“{task.keyword}”{mode_text}采集完成。"
                        f"发现 {stats.discovered_count} 条，写入 {stats.written_count} 条，跳过 {stats.skipped_count} 条。"
                    )
                    if stats.stopped_by_checkpoint or stats.stopped_by_user:
                        break

                if not collected_any:
                    mode_text = "预览" if args.preview else "新标签页"
                    log(f"没有通过{mode_text}采集到笔记。请确认已经登录，并检查搜索页是否正常显示结果。")
                    return 1
                log(
                    "完成。"
                    f"成功 {success_count} 条，失败 {failed_count} 条，跳过 {skipped_count} 条。"
                    f"CSV 已保存到：{output_path.resolve()}"
                )
                return 0
            else:
                for task_index, task in enumerate(keyword_tasks, start=1):
                    log(f"开始关键词任务 {task_index}/{len(keyword_tasks)}：{task.keyword}，目标 {task.max_notes} 条。")
                    search_page = context.new_page()
                    try:
                        items = collect_search_items(
                            search_page,
                            keyword=task.keyword,
                            max_notes=task.max_notes,
                            max_scrolls=args.max_scrolls,
                            scroll_delay=args.scroll_delay,
                            stagnant_limit=args.stagnant_limit,
                            scroll_pixels=args.scroll_pixels,
                            search_settle_ms=args.search_settle_ms,
                            ignore_checkpoint=args.ignore_checkpoint,
                        )
                    finally:
                        search_page.close()
                    keyword_batches.append((task.keyword, items))

                    if args.search_only:
                        if not items:
                            log(f"关键词“{task.keyword}”没有收集到笔记链接。")
                            continue
                        collected_any = True
                        rows = [search_item_to_row(task.keyword, item) for item in items]
                        written = write_output_rows(rows)
                        log(f"关键词“{task.keyword}”搜索页采集完成，已写入 {written} 行。")

                if args.search_only:
                    if not collected_any:
                        log("没有收集到笔记链接。请确认已经登录，并检查搜索页是否正常显示结果。")
                        return 1
                    log(f"已完成搜索页采集。CSV 已保存到：{output_path.resolve()}")
                    return 0

        consecutive_errors = 0
        for batch_index, (keyword, items) in enumerate(keyword_batches, start=1):
            if not items:
                log(f"关键词“{keyword}”没有收集到笔记链接。")
                continue
            collected_any = True
            log(f"开始采集关键词“{keyword}”的详情，共 {len(items)} 条候选笔记。")
            for index, item in enumerate(items, start=1):
                if args.max_runtime_minutes > 0:
                    elapsed_minutes = (time.monotonic() - start_time) / 60
                    if elapsed_minutes >= args.max_runtime_minutes:
                        log(f"达到最大运行时长 {args.max_runtime_minutes} 分钟，已平稳停止。")
                        stop_requested = True
                        break

                key = item.note_id or item.url
                if resume_index.contains(keyword, item, keyword_scoped=resume_keyword_scoped):
                    skipped_count += 1
                    log(f"[{index}/{len(items)}] 跳过已存在：{key}")
                    continue

                log(f"[{index}/{len(items)}] 采集详情：{item.url}")
                row = scrape_note_detail(context, item, keyword, args)
                write_output_rows([row])
                resume_index.add(keyword, item)
                processed_since_restart += 1
                processed_since_rest += 1

                if row.get("status") == "ok":
                    consecutive_errors = 0
                    success_count += 1
                else:
                    consecutive_errors += 1
                    failed_count += 1
                    log(f"详情页采集异常：{row.get('status')} {row.get('error')}")
                    if consecutive_errors >= args.max_errors:
                        should_continue = wait_for_manual_takeover(
                            context,
                            args,
                            f"连续 {consecutive_errors} 条详情页失败，已暂停任务。",
                        )
                        consecutive_errors = 0
                        if not should_continue:
                            stop_requested = True
                            break
                    elif args.error_delay > 0:
                        time.sleep(args.error_delay)

                has_more_work = index < len(items) or batch_index < len(keyword_batches)
                if args.restart_every > 0 and processed_since_restart >= args.restart_every and has_more_work:
                    log(f"已处理 {args.restart_every} 条详情页，重启浏览器上下文以释放资源。")
                    context.close()
                    playwright.stop()
                    playwright, context = launch_context(args)
                    processed_since_restart = 0

                if args.rest_every > 0 and processed_since_rest >= args.rest_every and has_more_work:
                    rest_seconds = max(0, args.rest_minutes * 60)
                    processed_since_rest = 0
                    if rest_seconds > 0:
                        log(f"已处理 {args.rest_every} 条详情页，休息 {args.rest_minutes} 分钟。")
                        time.sleep(rest_seconds)

                if has_more_work:
                    sleep_random(args.min_delay, args.max_delay)

            if stop_requested:
                break

        if not collected_any:
            log("没有收集到笔记链接。请确认已经登录，并检查搜索页是否正常显示结果。")
            return 1

        log(
            "完成。"
            f"成功 {success_count} 条，失败 {failed_count} 条，跳过 {skipped_count} 条。"
            f"CSV 已保存到：{output_path.resolve()}"
        )
        return 0
    except KeyboardInterrupt:
        log("收到中断信号，已停止。已写入的 CSV 行会保留，可直接重新运行继续。")
        return 130
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
