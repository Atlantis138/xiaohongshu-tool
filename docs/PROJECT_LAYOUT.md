# 项目结构

```text
xiaohongshu-tool/
  xhs/                 核心采集逻辑包
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
