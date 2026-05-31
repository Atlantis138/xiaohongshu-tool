# 项目结构

```text
xiaohongshu-tool/
  xhs/                 核心工具箱逻辑包
  xhs_scraper.py       命令行兼容入口
  xhs_gui.py           Tkinter 图形界面入口
  scripts/             Windows 启动脚本
  data/                本地输出目录，仅保留 .gitkeep 入库
  docs/                维护说明
  .venv/               项目本地 Python 虚拟环境，不入库
  .xhs_browser/        Playwright 浏览器资料目录，不入库
```

## 本地数据说明

- `.xhs_browser/` 保存 Chromium 登录状态、Cookie、Local Storage、历史记录和缓存。它可能含账号会话信息，不能上传 GitHub。
- `.venv/` 保存项目 Python 依赖，由 `scripts/setup.ps1` 创建，不能上传 GitHub。
- `data/` 保存抓取结果 CSV、日志和调试文件。默认不上传 GitHub。
- `__pycache__/`、Playwright 缓存、浏览器 Cache/Code Cache 都是可再生成文件。

## 适合入库的内容

- 源码：`xhs/`、`xhs_scraper.py`、`xhs_gui.py`
- 启动脚本：`scripts/`
- 文档：`README.md`、`docs/`
- 依赖声明：`requirements.txt`、`pyproject.toml`
- 安装入口：`scripts/setup.ps1`、`scripts/setup.bat`

## 核心模块边界

- `xhs/cli.py`：只负责命令行参数解析、参数校验和调用 runner。
- `xhs/runner.py`：应用层编排，负责登录检查、CSV 续跑、模式调度、节奏控制和最终统计。
- `xhs/modes.py`：采集模式、GUI 任务文案、关键词任务解析和运行参数校验。
- `xhs/search_scan.py`：搜索页扫描、卡片定位、滚动恢复等共享浏览器操作。
- `xhs/strategies.py`：预览层和新标签页策略接口，屏蔽不同打开方式的差异。
- `xhs/search.py` / `xhs/detail.py`：URL 流程的搜索链接采集和详情页抽取。
- `xhs/preview.py` / `xhs/new_tab.py`：只保留各自模式的差异行为。

## 入口文件约定

- `xhs_gui.py` 和 `xhs_scraper.py` 保留在项目根目录，作为用户双击、命令行和旧脚本兼容入口。
- `scripts/` 只放 Windows 启动和安装辅助脚本。这样入口路径稳定，也符合 Python 项目常见的“包代码在 `xhs/`，兼容入口在根目录，辅助脚本在 `scripts/`”布局。
