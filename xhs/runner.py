from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from .browser import check_login_status, launch_context, run_login_only, wait_for_manual_takeover
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
from .logging_utils import log
from .modes import KeywordTask, ScrapeMode, build_run_config
from .models import SearchItem
from .runtime import sleep_random
from .search import collect_search_items
from .strategies import strategy_for_mode


def run(args: argparse.Namespace, keyword_tasks: list[KeywordTask]) -> int:
    run_config = build_run_config(args, keyword_tasks)
    mode = run_config.mode
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
        output_path = Path(run_config.output)
        input_path = Path(run_config.input_csv) if run_config.input_csv else None
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
            log(f"断点续跑：已从输出 CSV 读取 {resume_index.row_count} 条已有记录，按 note_id 全局匹配。")
        else:
            log("断点续跑：输出 CSV 中没有可用于跳过的已有记录。")

        def write_output_rows(rows: list[dict[str, Any]]) -> int:
            nonlocal wrote_output, skipped_count
            safe_rows: list[dict[str, Any]] = []
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
            keyword_batches = _load_input_csv_batch(args, input_path)
            if args.search_only:
                if not keyword_batches[0][1]:
                    log("没有从输入 CSV 读取到笔记链接。")
                    return 1
                rows = [search_item_to_row(args.keyword or "", item) for item in keyword_batches[0][1]]
                written = write_output_rows(rows)
                log(f"已完成链接 CSV 转存，写入 {written} 行。CSV 已保存到：{output_path.resolve()}")
                return 0
        elif mode in {ScrapeMode.PREVIEW_OVERLAY, ScrapeMode.NEW_TAB}:
            return _run_search_page_strategy(
                args=args,
                context=context,
                mode=mode,
                keyword_tasks=keyword_tasks,
                resume_index=resume_index,
                resume_keyword_scoped=resume_keyword_scoped,
                write_output_rows=write_output_rows,
                output_path=output_path,
                collected_any=collected_any,
                success_count=success_count,
                failed_count=failed_count,
                skipped_count=skipped_count,
            )
        else:
            keyword_batches, collected_any = _collect_url_pipeline_batches(
                args=args,
                context=context,
                keyword_tasks=keyword_tasks,
                write_output_rows=write_output_rows,
            )
            if args.search_only:
                if not collected_any:
                    log("没有收集到笔记链接。请确认已经登录，并检查搜索页是否正常显示结果。")
                    return 1
                log(f"已完成搜索页链接采集。CSV 已保存到：{output_path.resolve()}")
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
        log("收到中断信号，已停止。已经写入的 CSV 行会保留，可直接重新运行继续。")
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


def _load_input_csv_batch(args: argparse.Namespace, input_path: Path) -> list[tuple[str, list[SearchItem]]]:
    items = load_search_items_from_csv(
        input_path,
        args.max_notes,
    )
    log(f"从链接 CSV 读取 {len(items)} 条候选笔记：{input_path}")
    return [(args.keyword or "", items)]


def _run_search_page_strategy(
    *,
    args: argparse.Namespace,
    context,
    mode: ScrapeMode,
    keyword_tasks: list[KeywordTask],
    resume_index: ResumeIndex,
    resume_keyword_scoped: bool,
    write_output_rows,
    output_path: Path,
    collected_any: bool,
    success_count: int,
    failed_count: int,
    skipped_count: int,
) -> int:
    strategy = strategy_for_mode(mode)

    def write_search_page_detail_row(row: dict[str, object]) -> None:
        write_output_rows([row])

    for task_index, task in enumerate(keyword_tasks, start=1):
        log(f"开始关键词{strategy.display_name}任务 {task_index}/{len(keyword_tasks)}：{task.keyword}，目标 {task.max_notes} 条。")
        search_page = context.new_page()
        try:
            stats = strategy.run_keyword(
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
            f"关键词“{task.keyword}”{strategy.display_name}采集完成。"
            f"发现 {stats.discovered_count} 条，写入 {stats.written_count} 条，跳过 {stats.skipped_count} 条。"
        )
        if stats.stopped_by_checkpoint or stats.stopped_by_user:
            break

    if not collected_any:
        log(f"没有通过{strategy.display_name}采集到笔记。请确认已经登录，并检查搜索页是否正常显示结果。")
        return 1
    log(
        "完成。"
        f"成功 {success_count} 条，失败 {failed_count} 条，跳过 {skipped_count} 条。"
        f"CSV 已保存到：{output_path.resolve()}"
    )
    return 0


def _collect_url_pipeline_batches(
    *,
    args: argparse.Namespace,
    context,
    keyword_tasks: list[KeywordTask],
    write_output_rows,
) -> tuple[list[tuple[str, list[SearchItem]]], bool]:
    keyword_batches: list[tuple[str, list[SearchItem]]] = []
    collected_any = False
    for task_index, task in enumerate(keyword_tasks, start=1):
        log(f"开始关键词 URL 流程任务 {task_index}/{len(keyword_tasks)}：{task.keyword}，目标 {task.max_notes} 条。")
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
            log(f"关键词“{task.keyword}”搜索页链接采集完成，已写入 {written} 行。")
    return keyword_batches, collected_any
