from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from subprocess import list2cmdline
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from xhs.modes import GUI_TASK_LABELS, GUI_URL_PIPELINE_STEP_LABELS


PROJECT_DIR = Path(__file__).resolve().parent
SCRAPER_PATH = PROJECT_DIR / "xhs_scraper.py"
SETTINGS_PATH = PROJECT_DIR / "data" / "gui_settings.json"

MODE_LABELS = GUI_TASK_LABELS
MODE_CODES = {label: code for code, label in MODE_LABELS.items()}
URL_STEP_LABELS = GUI_URL_PIPELINE_STEP_LABELS
URL_STEP_CODES = {label: code for code, label in URL_STEP_LABELS.items()}

DEFAULTS = {
    "mode": "url_pipeline",
    "url_pipeline_step": "full",
    "keyword": "",
    "max_notes": "30",
    "use_keyword_tasks": False,
    "keyword_tasks_text": "",
    "auto_scrolls": True,
    "output": "data/xhs_notes.csv",
    "input_csv": "",
    "overwrite": False,
    "profile_dir": ".xhs_browser",
    "headless": False,
    "slow_mo": "0",
    "max_scrolls": "25",
    "stagnant_limit": "8",
    "scroll_pixels": "2600",
    "search_settle_ms": "3000",
    "scroll_delay": "2.0",
    "min_delay": "3.0",
    "max_delay": "7.0",
    "rest_every": "100",
    "rest_minutes": "3.0",
    "restart_every": "200",
    "max_runtime_minutes": "0",
    "timeout_ms": "30000",
    "max_errors": "3",
    "error_delay": "20.0",
    "ignore_checkpoint": False,
    "block_media": False,
    "log_file": "data/xhs_scraper.log",
    "debug": False,
    "debug_on_error": False,
    "debug_dir": "data/debug",
}

INT_RULES = {
    "max_notes": (1, None),
    "slow_mo": (0, None),
    "max_scrolls": (0, None),
    "stagnant_limit": (0, None),
    "scroll_pixels": (0, None),
    "search_settle_ms": (0, None),
    "rest_every": (0, None),
    "restart_every": (0, None),
    "timeout_ms": (1, None),
    "max_errors": (1, None),
}

FLOAT_RULES = {
    "scroll_delay": (0, None),
    "min_delay": (0, None),
    "max_delay": (0, None),
    "rest_minutes": (0, None),
    "max_runtime_minutes": (0, None),
    "error_delay": (0, None),
}

ARG_FIELDS = [
    ("profile_dir", "--profile-dir"),
    ("slow_mo", "--slow-mo"),
    ("max_scrolls", "--max-scrolls"),
    ("stagnant_limit", "--stagnant-limit"),
    ("scroll_pixels", "--scroll-pixels"),
    ("search_settle_ms", "--search-settle-ms"),
    ("scroll_delay", "--scroll-delay"),
    ("min_delay", "--min-delay"),
    ("max_delay", "--max-delay"),
    ("rest_every", "--rest-every"),
    ("rest_minutes", "--rest-minutes"),
    ("restart_every", "--restart-every"),
    ("max_runtime_minutes", "--max-runtime-minutes"),
    ("timeout_ms", "--timeout-ms"),
    ("max_errors", "--max-errors"),
    ("error_delay", "--error-delay"),
    ("log_file", "--log-file"),
    ("debug_dir", "--debug-dir"),
]

BOOL_ARGS = [
    ("headless", "--headless"),
    ("ignore_checkpoint", "--ignore-checkpoint"),
    ("block_media", "--block-media"),
    ("debug", "--debug"),
    ("debug_on_error", "--debug-on-error"),
]


class XhsScraperGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("小红书采集器")
        self.geometry("1020x760")
        self.minsize(900, 680)
        self.configure(bg="#f5f1e8")

        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.log_queue: queue.Queue[tuple[str, str | int]] = queue.Queue()
        self.advanced_visible = tk.BooleanVar(value=False)
        self.current_run_kind = "idle"

        self.settings = self.load_settings()
        self.vars: dict[str, tk.StringVar | tk.BooleanVar] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.entry_widgets: dict[str, list[tk.Widget]] = {}
        self.url_step_widgets: list[tk.Widget] = []
        self.keyword_tasks_text: tk.Text | None = None
        self.mode_label_var = tk.StringVar(
            value=MODE_LABELS.get(self.settings.get("mode", "url_pipeline"), MODE_LABELS["url_pipeline"])
        )
        self.url_step_label_var = tk.StringVar(
            value=URL_STEP_LABELS.get(self.settings.get("url_pipeline_step", "full"), URL_STEP_LABELS["full"])
        )
        self.login_status_var = tk.StringVar(value="登录状态：未检查")
        self.computed_scrolls_var = tk.StringVar(value="")

        self.create_variables()
        self.create_styles()
        self.create_widgets()
        self.vars["max_notes"].trace_add("write", lambda *_args: self.update_scroll_strategy())
        self.vars["use_keyword_tasks"].trace_add("write", lambda *_args: self.update_mode_state())
        self.vars["auto_scrolls"].trace_add("write", lambda *_args: self.update_scroll_strategy())
        self.vars["profile_dir"].trace_add("write", lambda *_args: self.refresh_profile_hint())
        self.update_mode_state()
        self.update_scroll_strategy()
        self.refresh_profile_hint()
        self.after(100, self.drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f5f1e8")
        style.configure("Card.TFrame", background="#fffaf0", relief="flat")
        style.configure("TLabel", background="#f5f1e8", font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background="#fffaf0", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background="#f5f1e8", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Hint.TLabel", background="#f5f1e8", foreground="#6b6254", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TLabelframe", background="#f5f1e8")
        style.configure("TLabelframe.Label", background="#f5f1e8", font=("Microsoft YaHei UI", 10, "bold"))

    def create_variables(self) -> None:
        for key, default in DEFAULTS.items():
            if key == "mode":
                continue
            value = self.settings.get(key, default)
            if isinstance(default, bool):
                self.vars[key] = tk.BooleanVar(value=bool(value))
            else:
                self.vars[key] = tk.StringVar(value=str(value))

    def create_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        shell = ttk.Frame(self)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        self.main_canvas = tk.Canvas(shell, bg="#f5f1e8", highlightthickness=0)
        self.main_canvas.grid(row=0, column=0, sticky="nsew")
        main_scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.main_canvas.yview)
        main_scrollbar.grid(row=0, column=1, sticky="ns")
        self.main_canvas.configure(yscrollcommand=main_scrollbar.set)

        scroll_content = ttk.Frame(self.main_canvas)
        self.scroll_window_id = self.main_canvas.create_window((0, 0), window=scroll_content, anchor="nw")
        scroll_content.bind(
            "<Configure>",
            lambda _event: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")),
        )
        self.main_canvas.bind(
            "<Configure>",
            lambda event: self.main_canvas.itemconfigure(self.scroll_window_id, width=event.width),
        )
        self.bind_mousewheel(self.main_canvas)

        scroll_content.columnconfigure(0, weight=1)

        header = ttk.Frame(scroll_content, padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="小红书推文内容抓取器", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="先确认登录状态，再选择采集任务。运行日志会实时显示在下方。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        content = ttk.Frame(scroll_content, padding=(18, 4, 18, 8))
        content.grid(row=1, column=0, sticky="ew")
        content.columnconfigure(0, weight=1)

        account = ttk.LabelFrame(content, text="账号与浏览器会话", padding=(14, 10, 14, 12))
        account.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        account.columnconfigure(3, weight=1)
        ttk.Label(account, textvariable=self.login_status_var).grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.check_login_button = ttk.Button(account, text="检查登录状态", command=self.check_login_status)
        self.check_login_button.grid(row=0, column=1, padx=(0, 8))
        self.login_button = ttk.Button(account, text="打开登录窗口", command=self.start_login)
        self.login_button.grid(row=0, column=2, padx=(0, 8))
        self.login_done_button = ttk.Button(
            account,
            text="我已完成登录",
            command=self.send_login_done,
            state="disabled",
        )
        self.login_done_button.grid(row=0, column=3, sticky="w")

        basic = ttk.LabelFrame(content, text="采集任务", padding=(14, 10, 14, 12))
        basic.grid(row=1, column=0, sticky="ew")
        basic.columnconfigure(1, weight=1)
        basic.columnconfigure(4, weight=1)

        ttk.Label(basic, text="任务类型").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        self.mode_combo = ttk.Combobox(
            basic,
            textvariable=self.mode_label_var,
            values=list(MODE_CODES.keys()),
            state="readonly",
            width=26,
        )
        self.mode_combo.grid(row=0, column=1, sticky="w", pady=5)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_mode_state())

        url_step_label = ttk.Label(basic, text="URL流程步骤")
        url_step_label.grid(row=0, column=3, sticky="w", padx=(0, 8), pady=5)
        self.url_step_combo = ttk.Combobox(
            basic,
            textvariable=self.url_step_label_var,
            values=list(URL_STEP_CODES.keys()),
            state="readonly",
            width=26,
        )
        self.url_step_combo.grid(row=0, column=4, sticky="w", pady=5)
        self.url_step_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_mode_state())
        self.url_step_widgets = [url_step_label, self.url_step_combo]

        self.add_entry(basic, 1, "关键词", "keyword", column=0, width=38)
        self.add_entry(basic, 1, "目标笔记数", "max_notes", column=3, width=12)
        self.add_entry(basic, 2, "输出 CSV", "output", column=0, width=56, browse="save")
        self.add_entry(basic, 3, "输入链接 CSV", "input_csv", column=0, width=56, browse="open")

        self.overwrite_check = ttk.Checkbutton(
            basic,
            text="覆盖已有输出文件",
            variable=self.vars["overwrite"],
        )
        self.overwrite_check.grid(row=2, column=5, sticky="w", padx=(10, 0))

        self.keyword_tasks_check = ttk.Checkbutton(
            basic,
            text="批量关键词",
            variable=self.vars["use_keyword_tasks"],
            command=self.update_mode_state,
        )
        self.keyword_tasks_check.grid(row=3, column=5, sticky="w", padx=(10, 0))

        keyword_tasks_frame = ttk.Frame(basic)
        keyword_tasks_frame.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        keyword_tasks_frame.columnconfigure(1, weight=1)
        ttk.Label(keyword_tasks_frame, text="批量任务").grid(row=0, column=0, sticky="nw", padx=(0, 8))
        self.keyword_tasks_text = tk.Text(
            keyword_tasks_frame,
            height=4,
            width=72,
            wrap="word",
            bg="#fffdf6",
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 10),
        )
        self.keyword_tasks_text.grid(row=0, column=1, sticky="ew")
        self.keyword_tasks_text.insert("1.0", str(self.settings.get("keyword_tasks_text", "")))
        ttk.Label(
            keyword_tasks_frame,
            text="每行一个任务，例如：城市露营,5",
            style="Hint.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(4, 0))

        actions = ttk.Frame(content, padding=(0, 10, 0, 0))
        actions.grid(row=2, column=0, sticky="ew")
        actions.columnconfigure(4, weight=1)
        self.start_button = ttk.Button(actions, text="开始采集", style="Accent.TButton", command=self.start_run)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop_run, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(0, 8))
        self.advanced_button = ttk.Button(actions, text="显示高级参数", command=self.toggle_advanced)
        self.advanced_button.grid(row=0, column=2, padx=(0, 8))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(actions, textvariable=self.status_var, style="Hint.TLabel").grid(row=0, column=4, sticky="e")

        self.advanced_frame = ttk.LabelFrame(content, text="高级参数", padding=(14, 10, 14, 12))
        self.advanced_frame.columnconfigure(1, weight=1)
        self.advanced_frame.columnconfigure(4, weight=1)
        self.create_advanced_fields(self.advanced_frame)
        self.advanced_frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.advanced_frame.grid_remove()

        log_frame = ttk.LabelFrame(scroll_content, text="运行日志", padding=(10, 8, 10, 10))
        log_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            height=18,
            bg="#1f2528",
            fg="#f4f1e8",
            insertbackground="#f4f1e8",
            relief="flat",
            font=("Consolas", 10),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        log_actions = ttk.Frame(log_frame)
        log_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(log_actions, text="清空日志", command=self.clear_log).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(log_actions, text="打开输出目录", command=self.open_output_dir).grid(row=0, column=1)

    def bind_mousewheel(self, widget: tk.Widget) -> None:
        widget.bind_all("<MouseWheel>", self.on_main_mousewheel)
        widget.bind_all("<Button-4>", self.on_main_mousewheel)
        widget.bind_all("<Button-5>", self.on_main_mousewheel)

    def on_main_mousewheel(self, event: tk.Event) -> None:
        focus = self.focus_get()
        if focus is self.log_text or focus is self.keyword_tasks_text:
            return
        if getattr(event, "num", None) == 4:
            self.main_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.main_canvas.yview_scroll(1, "units")
        else:
            self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def create_advanced_fields(self, parent: ttk.LabelFrame) -> None:
        self.add_entry(parent, 0, "浏览器资料目录", "profile_dir", column=0, width=34, browse="dir")
        self.add_entry(parent, 0, "日志文件", "log_file", column=3, width=34, browse="save_log")
        self.add_entry(parent, 1, "最小延迟秒", "min_delay", column=0, width=12)
        self.add_entry(parent, 1, "最大延迟秒", "max_delay", column=3, width=12)
        ttk.Checkbutton(
            parent,
            text="按目标笔记数自动估算滚动轮数",
            variable=self.vars["auto_scrolls"],
            command=self.update_scroll_strategy,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=5)
        ttk.Label(parent, textvariable=self.computed_scrolls_var, style="Hint.TLabel").grid(
            row=2,
            column=3,
            columnspan=3,
            sticky="w",
            pady=5,
        )
        self.add_entry(parent, 3, "手动最大滚动轮数", "max_scrolls", column=0, width=12)
        self.add_entry(parent, 3, "滚动等待秒", "scroll_delay", column=3, width=12)
        self.add_entry(parent, 4, "无新增停止轮数", "stagnant_limit", column=0, width=12)
        self.add_entry(parent, 4, "每次滚动像素", "scroll_pixels", column=3, width=12)
        self.add_entry(parent, 5, "搜索页等待毫秒", "search_settle_ms", column=0, width=12)
        self.add_entry(parent, 5, "页面超时毫秒", "timeout_ms", column=3, width=12)
        self.add_entry(parent, 6, "每 N 条休息", "rest_every", column=0, width=12)
        self.add_entry(parent, 6, "休息分钟", "rest_minutes", column=3, width=12)
        self.add_entry(parent, 7, "每 N 条重启", "restart_every", column=0, width=12)
        self.add_entry(parent, 7, "最大运行分钟", "max_runtime_minutes", column=3, width=12)
        self.add_entry(parent, 8, "最大连续错误", "max_errors", column=0, width=12)
        self.add_entry(parent, 8, "错误后等待秒", "error_delay", column=3, width=12)
        self.add_entry(parent, 9, "Playwright 慢动作毫秒", "slow_mo", column=0, width=12)
        self.add_entry(parent, 9, "Debug 目录", "debug_dir", column=3, width=34, browse="dir")

        checks = ttk.Frame(parent)
        checks.grid(row=10, column=0, columnspan=6, sticky="w", pady=(8, 0))
        for index, (key, text) in enumerate(
            [
                ("headless", "无头模式"),
                ("ignore_checkpoint", "忽略验证/登录检查点"),
                ("block_media", "屏蔽图片视频字体"),
                ("debug", "保存每页调试文件"),
                ("debug_on_error", "仅错误时保存调试文件"),
            ]
        ):
            ttk.Checkbutton(checks, text=text, variable=self.vars[key]).grid(
                row=0,
                column=index,
                padx=(0, 14),
                sticky="w",
            )

        ttk.Label(parent, text="提示：日志文件留空可禁用文件日志。", style="Hint.TLabel").grid(
            row=11,
            column=0,
            columnspan=6,
            sticky="w",
            pady=(8, 0),
        )

    def add_entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        key: str,
        *,
        column: int,
        width: int,
        browse: str | None = None,
    ) -> None:
        widgets: list[tk.Widget] = []
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=column, sticky="w", padx=(0, 8), pady=5)
        widgets.append(label_widget)
        entry = ttk.Entry(parent, textvariable=self.vars[key], width=width)
        entry.grid(row=row, column=column + 1, sticky="ew", pady=5)
        self.entries[key] = entry
        widgets.append(entry)
        if browse:
            button = ttk.Button(parent, text="选择", command=lambda: self.browse_path(key, browse))
            button.grid(
                row=row,
                column=column + 2,
                padx=(6, 12),
                pady=5,
            )
            widgets.append(button)
        self.entry_widgets[key] = widgets

    def browse_path(self, key: str, browse: str) -> None:
        current = self.get_string(key)
        initial_dir = PROJECT_DIR
        if current:
            candidate = Path(current)
            if not candidate.is_absolute():
                candidate = PROJECT_DIR / candidate
            initial_dir = candidate if candidate.is_dir() else candidate.parent

        if browse == "open":
            path = filedialog.askopenfilename(
                title="选择输入 CSV",
                initialdir=str(initial_dir),
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            )
        elif browse == "save":
            path = filedialog.asksaveasfilename(
                title="选择输出 CSV",
                initialdir=str(initial_dir),
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            )
        elif browse == "save_log":
            path = filedialog.asksaveasfilename(
                title="选择日志文件",
                initialdir=str(initial_dir),
                defaultextension=".log",
                filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt"), ("所有文件", "*.*")],
            )
        else:
            path = filedialog.askdirectory(title="选择目录", initialdir=str(initial_dir))

        if path:
            self.vars[key].set(self.display_path(Path(path)))

    def display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(PROJECT_DIR.resolve()))
        except ValueError:
            return str(path)

    def current_mode(self) -> str:
        return MODE_CODES.get(self.mode_label_var.get(), "url_pipeline")

    def current_url_pipeline_step(self) -> str:
        return URL_STEP_CODES.get(self.url_step_label_var.get(), "full")

    def effective_task_mode(self) -> str:
        mode = self.current_mode()
        if mode == "url_pipeline":
            return self.current_url_pipeline_step()
        return mode

    def update_mode_state(self) -> None:
        mode = self.current_mode()
        task_mode = self.effective_task_mode()
        is_url_pipeline = mode == "url_pipeline"
        from_csv = task_mode == "from_csv"
        use_keyword_tasks = bool(self.vars["use_keyword_tasks"].get()) and not from_csv
        for widget in self.url_step_widgets:
            if is_url_pipeline:
                widget.grid()
            else:
                widget.grid_remove()
        self.url_step_combo.configure(state="readonly" if is_url_pipeline else "disabled")
        self.set_entry_enabled("keyword", not use_keyword_tasks)
        self.set_entry_visible("input_csv", is_url_pipeline)
        self.set_entry_enabled("input_csv", from_csv)
        self.set_entry_enabled("output", True)
        self.set_entry_enabled("max_notes", not use_keyword_tasks)
        self.keyword_tasks_check.configure(state="disabled" if from_csv else "normal")
        self.set_keyword_tasks_text_enabled(use_keyword_tasks)
        self.overwrite_check.configure(state="normal")
        if from_csv:
            self.status_var.set("从链接表采详情时，关键词可留空，优先使用链接表内关键词。")
        elif task_mode == "preview":
            self.status_var.set("在搜索页内逐条点开预览采详情，减少详情页跳转。")
        elif task_mode == "new_tab":
            self.status_var.set("在搜索页中用新标签页打开笔记并采集详情。")
        elif task_mode == "search_only":
            self.status_var.set("只保存搜索链接，不打开详情页；适合大批量任务第一步。")
        elif task_mode == "full":
            self.status_var.set("URL流程完整执行：先收集搜索链接，再逐条访问详情页。")
        else:
            self.status_var.set("就绪")
        self.update_scroll_strategy()

    def set_entry_enabled(self, key: str, enabled: bool) -> None:
        if key in self.entries:
            self.entries[key].configure(state="normal" if enabled else "disabled")

    def set_entry_visible(self, key: str, visible: bool) -> None:
        for widget in self.entry_widgets.get(key, []):
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def set_keyword_tasks_text_enabled(self, enabled: bool) -> None:
        if self.keyword_tasks_text is not None:
            self.keyword_tasks_text.configure(state="normal" if enabled else "disabled")

    def set_busy_state(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.start_button.configure(state=state)
        self.check_login_button.configure(state=state)
        self.login_button.configure(state=state)
        self.mode_combo.configure(state="disabled" if busy else "readonly")
        self.url_step_combo.configure(state="disabled" if busy else "readonly")
        if not busy:
            self.update_mode_state()

    def estimate_max_scrolls(self) -> int:
        if self.vars["use_keyword_tasks"].get() and self.effective_task_mode() != "from_csv":
            try:
                max_notes = max(count for _keyword, count in self.parse_keyword_tasks_text())
            except ValueError:
                max_notes = int(DEFAULTS["max_notes"])
            return max(25, int(max_notes / 2) + 10)
        try:
            max_notes = int(self.get_string("max_notes"))
        except ValueError:
            return int(DEFAULTS["max_scrolls"])
        # Search result density varies a lot. This conservative estimate matches
        # the existing long-run guidance: about 500 scrolls for 1000 target notes.
        return max(25, int(max_notes / 2) + 10)

    def update_scroll_strategy(self) -> None:
        auto_scrolls = bool(self.vars["auto_scrolls"].get())
        if auto_scrolls:
            estimate = self.estimate_max_scrolls()
            self.computed_scrolls_var.set(f"当前会自动使用约 {estimate} 轮滚动")
            self.set_entry_enabled("max_scrolls", False)
        else:
            self.computed_scrolls_var.set("使用手动最大滚动轮数")
            self.set_entry_enabled("max_scrolls", True)

    def refresh_profile_hint(self) -> None:
        profile_dir = self.resolve_path(self.get_string("profile_dir"))
        if profile_dir.exists():
            self.login_status_var.set("登录状态：发现本地会话，建议检查")
        else:
            self.login_status_var.set("登录状态：未发现本地会话，请先登录")

    def toggle_advanced(self) -> None:
        visible = not self.advanced_visible.get()
        self.advanced_visible.set(visible)
        if visible:
            self.advanced_frame.grid()
            self.advanced_button.configure(text="隐藏高级参数")
        else:
            self.advanced_frame.grid_remove()
            self.advanced_button.configure(text="显示高级参数")
        self.after_idle(self.refresh_scroll_region)

    def refresh_scroll_region(self) -> None:
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def start_login(self) -> None:
        if self.process is not None:
            return
        try:
            self.validate_session_inputs()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if self.vars["headless"].get():
            messagebox.showerror("参数错误", "登录需要显示浏览器窗口，请先取消“无头模式”。")
            return
        cmd = self.base_command()
        cmd.extend(["--login-only", "--output", "data/_login_only_unused.csv"])
        cmd.extend(self.session_command_args())
        self.save_settings()
        self.append_log("")
        self.append_log(">>> 打开登录窗口。扫码完成后点击“我已完成登录”。")
        self.start_process(cmd, "login")

    def check_login_status(self) -> None:
        if self.process is not None:
            return
        try:
            self.validate_session_inputs()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        cmd = self.base_command()
        cmd.extend(["--check-login", "--output", "data/_login_check_unused.csv", "--headless"])
        cmd.extend(self.session_command_args())
        self.save_settings()
        self.login_status_var.set("登录状态：正在检查...")
        self.append_log("")
        self.append_log(">>> 正在检查登录状态...")
        self.start_process(cmd, "check_login")

    def start_run(self) -> None:
        if self.process is not None:
            return

        try:
            cmd = self.build_command()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.save_settings()
        self.append_log("")
        self.append_log(">>> " + list2cmdline(cmd))
        self.start_process(cmd, "scrape")

    def start_process(self, cmd: list[str], kind: str) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = 0
        if os.name == "nt":
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_DIR),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=creationflags,
            )
        except OSError as exc:
            self.process = None
            messagebox.showerror("启动失败", f"无法启动采集脚本：{exc}")
            return

        self.current_run_kind = kind
        self.set_busy_state(True)
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        if kind == "login":
            self.login_done_button.configure(text="我已完成登录", state="normal")
        else:
            self.login_done_button.configure(text="继续运行", state="disabled")
        self.status_var.set("运行中")

        self.reader_thread = threading.Thread(target=self.read_process_output, daemon=True)
        self.reader_thread.start()

    def base_command(self) -> list[str]:
        return [self.python_executable(), "-u", str(SCRAPER_PATH)]

    def session_command_args(self) -> list[str]:
        args = [
            "--profile-dir",
            self.get_string("profile_dir"),
            "--slow-mo",
            self.get_string("slow_mo"),
            "--timeout-ms",
            self.get_string("timeout_ms"),
        ]
        log_file = self.get_string("log_file")
        if log_file:
            args.extend(["--log-file", log_file])
        else:
            args.extend(["--log-file", ""])
        return args

    def build_command(self) -> list[str]:
        self.validate_inputs()
        cmd = self.base_command()
        mode = self.effective_task_mode()

        if mode == "from_csv":
            cmd.extend(["--input-csv", self.get_string("input_csv")])
            keyword = self.get_string("keyword")
            if keyword:
                cmd.extend(["--keyword", keyword])
            cmd.extend(["--max-notes", self.get_string("max_notes")])
            cmd.extend(["--output", self.get_string("output")])
        elif self.vars["use_keyword_tasks"].get():
            for keyword, count in self.parse_keyword_tasks_text():
                cmd.extend(["--keyword-task", f"{keyword}={count}"])
            cmd.extend(["--output", self.get_string("output")])
            if mode == "search_only":
                cmd.append("--search-only")
            elif mode == "preview":
                cmd.append("--preview")
            elif mode == "new_tab":
                cmd.append("--new-tab")
        else:
            cmd.extend(["--keyword", self.get_string("keyword")])
            cmd.extend(["--max-notes", self.get_string("max_notes")])
            cmd.extend(["--output", self.get_string("output")])
            if mode == "search_only":
                cmd.append("--search-only")
            elif mode == "preview":
                cmd.append("--preview")
            elif mode == "new_tab":
                cmd.append("--new-tab")

        if self.vars["overwrite"].get():
            cmd.append("--overwrite")

        for key, arg in ARG_FIELDS:
            if key == "max_scrolls" and self.vars["auto_scrolls"].get():
                cmd.extend([arg, str(self.estimate_max_scrolls())])
                continue
            value = self.get_string(key)
            if value or key == "log_file":
                cmd.extend([arg, value])

        for key, arg in BOOL_ARGS:
            if self.vars[key].get():
                cmd.append(arg)

        return cmd

    def validate_inputs(self) -> None:
        if not SCRAPER_PATH.exists():
            raise ValueError(f"找不到采集脚本：{SCRAPER_PATH}")

        mode = self.effective_task_mode()
        use_keyword_tasks = bool(self.vars["use_keyword_tasks"].get()) and mode != "from_csv"
        if mode in {"full", "preview", "new_tab", "search_only"}:
            if use_keyword_tasks:
                self.parse_keyword_tasks_text()
            elif not self.get_string("keyword"):
                raise ValueError("关键词不能为空。")
        if mode == "from_csv":
            input_csv = self.get_string("input_csv")
            if not input_csv:
                raise ValueError("从链接 CSV 采详情时必须选择输入 CSV。")
            input_path = self.resolve_path(input_csv)
            if not input_path.exists():
                raise ValueError(f"输入 CSV 不存在：{input_path}")
            if self.resolve_path(input_csv) == self.resolve_path(self.get_string("output")):
                raise ValueError("输入 CSV 和输出 CSV 不能是同一个文件。")
        if not self.get_string("output"):
            raise ValueError("输出 CSV 不能为空。")

        for key, (min_value, max_value) in INT_RULES.items():
            if key == "max_scrolls" and self.vars["auto_scrolls"].get():
                continue
            if key == "max_notes" and use_keyword_tasks:
                continue
            value = self.get_string(key)
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError(f"{key} 必须是整数。") from exc
            self.check_range(key, parsed, min_value, max_value)

        for key, (min_value, max_value) in FLOAT_RULES.items():
            value = self.get_string(key)
            try:
                parsed = float(value)
            except ValueError as exc:
                raise ValueError(f"{key} 必须是数字。") from exc
            self.check_range(key, parsed, min_value, max_value)

        if float(self.get_string("max_delay")) < float(self.get_string("min_delay")):
            raise ValueError("最大延迟秒不能小于最小延迟秒。")

    def validate_session_inputs(self) -> None:
        if not SCRAPER_PATH.exists():
            raise ValueError(f"找不到采集脚本：{SCRAPER_PATH}")
        if not self.get_string("profile_dir"):
            raise ValueError("浏览器资料目录不能为空。")
        for key in ["slow_mo", "timeout_ms"]:
            min_value, max_value = INT_RULES[key]
            value = self.get_string(key)
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError(f"{key} 必须是整数。") from exc
            self.check_range(key, parsed, min_value, max_value)

    def check_range(self, key: str, value: float, min_value: float | None, max_value: float | None) -> None:
        if min_value is not None and value < min_value:
            raise ValueError(f"{key} 不能小于 {min_value}。")
        if max_value is not None and value > max_value:
            raise ValueError(f"{key} 不能大于 {max_value}。")

    def parse_positive_int(self, key: str) -> int:
        value = self.get_string(key)
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{key} 必须是整数。") from exc
        if parsed < 1:
            raise ValueError(f"{key} 不能小于 1。")
        return parsed

    def read_process_output(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.log_queue.put(("log", line.rstrip("\n")))
        return_code = self.process.wait()
        self.log_queue.put(("done", return_code))

    def drain_log_queue(self) -> None:
        while True:
            try:
                event, payload = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                text = str(payload)
                self.append_log(text)
                if self.current_run_kind == "scrape" and "等待人工接管：" in text:
                    self.login_done_button.configure(text="继续运行", state="normal")
                    self.status_var.set("等待人工接管")
            elif event == "done":
                self.on_process_done(int(payload))
        self.after(100, self.drain_log_queue)

    def on_process_done(self, return_code: int) -> None:
        self.append_log(f">>> 进程已结束，退出码：{return_code}")
        finished_kind = self.current_run_kind
        self.process = None
        self.reader_thread = None
        self.current_run_kind = "idle"
        self.set_busy_state(False)
        self.stop_button.configure(state="disabled")
        self.login_done_button.configure(text="我已完成登录", state="disabled")
        if finished_kind == "check_login":
            if return_code == 0:
                self.login_status_var.set("登录状态：可用")
            else:
                self.login_status_var.set("登录状态：需要重新登录或遇到验证")
        elif finished_kind == "login" and return_code == 0:
            self.login_status_var.set("登录状态：已完成登录，请再检查一次确认")
        self.status_var.set("已完成" if return_code == 0 else f"已结束，退出码 {return_code}")

    def stop_run(self) -> None:
        if self.process is None:
            return
        self.append_log(">>> 正在请求停止进程...")
        self.status_var.set("正在停止")
        self.stop_button.configure(state="disabled")
        try:
            self.process.terminate()
        except OSError as exc:
            self.append_log(f">>> 停止失败：{exc}")
        self.after(3000, self.force_kill_if_needed)

    def force_kill_if_needed(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.append_log(">>> 进程未及时退出，强制结束。")
            try:
                self.process.kill()
            except OSError as exc:
                self.append_log(f">>> 强制结束失败：{exc}")

    def send_login_done(self) -> None:
        if self.process is None or self.process.stdin is None:
            return
        try:
            self.process.stdin.write("\n")
            self.process.stdin.flush()
            if self.current_run_kind == "scrape":
                self.append_log(">>> 已发送继续运行确认。")
                self.login_done_button.configure(state="disabled")
                self.status_var.set("运行中")
            else:
                self.append_log(">>> 已发送登录完成确认。")
        except OSError as exc:
            self.append_log(f">>> 发送登录确认失败：{exc}")

    def append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="normal")

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def open_output_dir(self) -> None:
        output = self.get_string("output")
        directory = self.resolve_path(output).parent if output else PROJECT_DIR / "data"
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(directory))
        else:
            messagebox.showinfo("输出目录", str(directory))

    def get_string(self, key: str) -> str:
        value = self.vars[key].get()
        return str(value).strip()

    def get_keyword_tasks_text(self) -> str:
        if self.keyword_tasks_text is None:
            return ""
        return self.keyword_tasks_text.get("1.0", "end").strip()

    def parse_keyword_tasks_text(self) -> list[tuple[str, int]]:
        tasks: list[tuple[str, int]] = []
        for line_number, raw_line in enumerate(self.get_keyword_tasks_text().splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r"^(?P<keyword>.+?)\s*[=,:：，]\s*(?P<count>\d+)\s*$", line)
            if match:
                keyword = match.group("keyword").strip()
                count_text = match.group("count")
            else:
                parts = line.rsplit(None, 1)
                if len(parts) != 2:
                    raise ValueError(f"批量任务第 {line_number} 行格式错误，应为：关键词,数量。")
                keyword, count_text = parts[0].strip(), parts[1].strip()
            if not keyword:
                raise ValueError(f"批量任务第 {line_number} 行关键词不能为空。")
            try:
                count = int(count_text)
            except ValueError as exc:
                raise ValueError(f"批量任务第 {line_number} 行数量必须是整数。") from exc
            if count <= 0:
                raise ValueError(f"批量任务第 {line_number} 行数量必须大于 0。")
            tasks.append((keyword, count))
        if not tasks:
            raise ValueError("请至少填写一个批量关键词任务。")
        return tasks

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return path.resolve()

    def python_executable(self) -> str:
        preferred = Path(r"C:\Python\Python311\python.exe")
        if preferred.exists():
            return str(preferred)

        current = Path(sys.executable)
        if current.name.lower() == "pythonw.exe":
            sibling = current.with_name("python.exe")
            if sibling.exists():
                return str(sibling)
        return str(current)

    def load_settings(self) -> dict[str, object]:
        if not SETTINGS_PATH.exists():
            return DEFAULTS.copy()
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return DEFAULTS.copy()
        settings = DEFAULTS.copy()
        if isinstance(data, dict):
            settings.update({key: value for key, value in data.items() if key in DEFAULTS})
        old_mode = str(data.get("mode", "")) if isinstance(data, dict) else ""
        if old_mode in {"keyword", "search_only", "from_csv"}:
            settings["mode"] = "url_pipeline"
            settings["url_pipeline_step"] = "full" if old_mode == "keyword" else old_mode
        return settings

    def collect_settings(self) -> dict[str, object]:
        settings: dict[str, object] = {"mode": self.current_mode()}
        settings["url_pipeline_step"] = self.current_url_pipeline_step()
        for key, var in self.vars.items():
            settings[key] = var.get()
        settings["keyword_tasks_text"] = self.get_keyword_tasks_text()
        return settings

    def save_settings(self) -> None:
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with SETTINGS_PATH.open("w", encoding="utf-8") as f:
                json.dump(self.collect_settings(), f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def on_close(self) -> None:
        if self.process is not None:
            should_close = messagebox.askyesno("确认退出", "采集仍在运行，退出会停止当前进程。是否继续？")
            if not should_close:
                return
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self.process.kill()
                except OSError:
                    pass
        self.save_settings()
        self.destroy()


def main() -> None:
    app = XhsScraperGui()
    app.mainloop()


if __name__ == "__main__":
    main()
