from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .config import BASE_URL
from .logging_utils import log


def launch_context(args: argparse.Namespace) -> tuple[Any, BrowserContext]:
    playwright = sync_playwright().start()
    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=args.headless,
        slow_mo=args.slow_mo,
        viewport={"width": 1440, "height": 1000},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    context.set_default_timeout(args.timeout_ms)
    if args.block_media:
        def route_handler(route):
            if route.request.resource_type in {"image", "media", "font"}:
                route.abort()
            else:
                route.continue_()

        context.route("**/*", route_handler)
    return playwright, context


def run_login_only(context: BrowserContext) -> None:
    page = context.new_page()
    page.goto(BASE_URL, wait_until="domcontentloaded")
    log("浏览器已打开。请在页面中手动扫码登录小红书，登录完成后回到终端或图形界面确认。")
    input()
    page.close()


def wait_for_manual_takeover(
    context: BrowserContext,
    args: argparse.Namespace,
    reason: str,
    page: Page | None = None,
) -> bool:
    recovery_page = page
    created_page = False
    log(f"等待人工接管：{reason}")
    if args.headless:
        log("当前启用了 --headless，无法看到浏览器页面；建议输入 q 结束后去掉 --headless 重新运行。")
    else:
        try:
            if recovery_page is None or recovery_page.is_closed():
                recovery_page = context.new_page()
                created_page = True
                recovery_page.goto(BASE_URL, wait_until="domcontentloaded", timeout=args.timeout_ms)
            recovery_page.bring_to_front()
        except Exception as exc:
            log(f"打开人工接管页面失败：{type(exc).__name__}: {exc}")

    log("请在浏览器中处理登录、验证或异常页面后，回到终端按 Enter 继续；输入 q 回车结束。图形界面请点击“继续运行”。")
    try:
        answer = input().strip().lower()
    except EOFError:
        log("标准输入已关闭，无法等待人工确认；停止当前任务。")
        answer = "q"

    if answer in {"q", "quit", "exit", "stop"}:
        log("已按人工接管确认结束当前任务。")
        return False

    log("已收到继续确认，将重置连续错误计数并继续。")
    if created_page and recovery_page is not None:
        try:
            recovery_page.close()
        except Exception:
            pass
    return True


def check_login_status(context: BrowserContext) -> bool:
    page = context.new_page()
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(1500)
        marker = detect_checkpoint(page)
        if marker:
            log(f"登录状态检查：检测到可能的登录/验证/访问异常页面：{marker}")
            return False
        log("登录状态检查：未发现登录/验证提示，当前浏览器会话看起来可用。")
        return True
    finally:
        page.close()


def detect_checkpoint(page: Page) -> str:
    try:
        data = page.evaluate(
            r"""
            () => {
              const text = (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim();
              const title = document.title || "";
              const url = location.href;
              return { text: text.slice(0, 5000), title, url };
            }
            """
        )
    except Exception:
        return ""

    haystack = f"{data.get('title', '')} {data.get('url', '')} {data.get('text', '')}"
    patterns = [
        "请登录",
        "扫码登录",
        "登录后查看更多",
        "验证码",
        "安全验证",
        "访问异常",
        "操作频繁",
        "请稍后再试",
        "请完成验证",
        "拖动滑块",
        "当前环境异常",
    ]
    for pattern in patterns:
        if pattern in haystack:
            return pattern
    return ""


def ensure_not_checkpoint(page: Page, ignore_checkpoint: bool, stage: str) -> bool:
    marker = detect_checkpoint(page)
    if not marker:
        return True
    message = f"{stage} 检测到可能的登录/验证/访问异常页面：{marker}"
    if ignore_checkpoint:
        log(message + "；已按 --ignore-checkpoint 继续。")
        return True
    log(message + "；为避免继续触发限制，脚本停止。")
    return False
