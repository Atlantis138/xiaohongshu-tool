# 小红书关键词笔记采集工具

这是一个本地运行的 Python + Playwright 采集脚本，用于在你已登录的小红书网页版中搜索关键词，逐条打开笔记详情页，并把可见基础信息保存到本地 CSV。

## 合规边界

- 仅用于课程作业、个人学习、小规模数据分析。
- 不包含验证码绕过、接口签名逆向、代理池、账号池或高并发逻辑。
- 第一次运行需要你在弹出的浏览器窗口中手动扫码登录。
- 请降低采集频率，控制采集规模，并遵守平台规则。

## 安装

首次 clone 到一台新电脑后，在项目根目录运行：

```powershell
.\scripts\setup.ps1
```

也可以直接运行批处理包装脚本：

```powershell
.\scripts\setup.bat
```

安装脚本会做三件事：

- 检查本机是否有 Python 3.11 或更新版本。
- 在项目内创建 `.venv/`，并把 `requirements.txt` 里的 Python 依赖安装进去。
- 执行 `python -m playwright install chromium`，浏览器二进制仍安装到 Playwright 默认的用户缓存目录，不放进项目仓库。

如果 PowerShell 阻止脚本运行，可以用当前窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

后续运行脚本会固定使用项目内 `.venv\Scripts\python.exe`，不会再依赖全局 Python 包环境。

## 第一次登录

```powershell
.\scripts\run_scraper.bat --login-only
```

浏览器打开后，手动完成扫码登录，然后回到终端按 Enter。登录状态会保存在 `.xhs_browser/`，后续运行会复用。

## 图形界面

如果不想手动输入命令行参数，可以双击运行：

```text
scripts\run_gui.bat
```

图形界面顶部提供账号会话区，可以先打开登录窗口或检查当前登录状态。采集任务区提供三种任务类型：URL 流程、预览层、新标签页。URL 流程下可选择“完整执行”“仅收集链接”“链接 CSV”三个步骤；输入链接 CSV 只会在 URL 流程中显示。常用参数默认显示，高级参数可展开调整。

如果要一次采多个关键词，可以勾选“批量关键词”，然后在批量任务框中每行填写一个任务，例如 `城市露营,20`。所有关键词会按填写顺序执行，并写入同一个输出 CSV。

目标笔记数是主要规模参数；最大滚动轮数默认会按目标笔记数自动估算。只有需要精细调试时，才建议在高级参数里关闭自动估算并手动填写滚动轮数。

登录时，浏览器打开后先在页面里扫码登录，然后回到图形界面点击“我已完成登录”。运行时日志会实时显示在窗口下方。

## 采集示例

```powershell
.\scripts\run_scraper.bat --keyword "城市露营" --max-notes 50 --output .\data\xhs_notes.csv
```

常用参数：

```powershell
.\scripts\run_scraper.bat `
  --keyword "城市露营" `
  --max-notes 100 `
  --output .\data\xhs_notes.csv `
  --min-delay 3 `
  --max-delay 7 `
  --max-scrolls 30
```

只验证第一步搜索主页卡片采集，不进入帖子详情页：

```powershell
.\scripts\run_scraper.bat --keyword "城市露营" --max-notes 50 --search-only --overwrite --output .\data\xhs_search_only.csv
```

在搜索页内逐条点开笔记预览采详情，减少详情页 URL 跳转：

```powershell
.\scripts\run_scraper.bat --keyword "城市露营" --max-notes 50 --preview --overwrite --output .\data\xhs_preview_notes.csv
```

在搜索页内逐条用新标签页打开笔记并采详情：

```powershell
.\scripts\run_scraper.bat --keyword "城市露营" --max-notes 50 --new-tab --search-settle-ms 8000 --overwrite --output .\data\xhs_new_tab_notes.csv
```

一次任务按顺序采集多个关键词，并统一写入一个 CSV：

```powershell
.\scripts\run_scraper.bat `
  --keyword-task "城市露营=20" `
  --keyword-task "户外咖啡=10" `
  --keyword-task "周末露营=30" `
  --output .\data\xhs_multi_keywords.csv `
  --overwrite
```

`--keyword-task` 可重复使用，格式为 `关键词=数量`。不勾选“覆盖已有输出文件”时，输出 CSV 会按 `note_id` 全局去重；如果同一笔记出现在多个关键词结果里，只会保留首次写入的那一条。

## 长时间采集推荐流程

上千条数据建议拆成两步，避免详情页采集中断后还要重新滚动搜索页。

第一步：只收集搜索结果链接。

```powershell
.\scripts\run_scraper.bat `
  --keyword "城市露营" `
  --max-notes 1000 `
  --max-scrolls 500 `
  --search-only `
  --overwrite `
  --output .\data\xhs_links_城市露营.csv
```

第二步：从链接表逐条采详情。

```powershell
.\scripts\run_scraper.bat `
  --input-csv .\data\xhs_links_城市露营.csv `
  --max-notes 1000 `
  --output .\data\xhs_notes_城市露营.csv `
  --min-delay 5 `
  --max-delay 12 `
  --rest-every 100 `
  --rest-minutes 5 `
  --restart-every 200 `
  --max-errors 3 `
  --debug-on-error
```

断点续跑：详情结果 CSV 每成功或失败一条都会立即追加保存。不勾选“覆盖已有输出文件”时，脚本启动后会先读取输出 CSV 建立恢复索引；读取帖子前如果发现该笔记 `note_id` 已经存在，就会快速跳过，不触发随机延迟、定期休息或重启计数。所有采集模式都按 `note_id` 全局跳过；如果行内 `note_id` 为空但 URL 能提取出笔记 ID，也会自动补齐后参与去重。不要把 `--input-csv` 和 `--output` 指向同一个文件。

`--max-notes` 仍是本次最多处理条数的上限；如果要处理完整范围，请把它设置为不小于范围长度。不勾选“覆盖已有输出文件”时，会继续自动跳过输出 CSV 中已经存在的 `note_id`。

## CSV 字段

脚本会根据页面实际可见 DOM、meta 信息和页面内嵌状态数据做多层兜底提取，默认保存：

- `keyword`
- `note_id`
- `url`
- `search_index`
- `title`
- `content`
- `author_name`
- `post_time`
- `ip_location`
- `liked_count`
- `collected_count`
- `comment_count`
- `scraped_at`
- `status`
- `error`

其中 `liked_count`、`collected_count`、`comment_count` 会尽量转换为整数。

## 保守运行

- 默认详情页之间随机等待 3-7 秒。
- 搜索页检测到疑似登录、验证码、安全验证、访问异常、操作频繁等页面时会停止，避免继续触发限制。
- 连续详情或预览采集失败达到 `--max-errors` 后会暂停等待人工接管，避免持续请求异常页面。
- 如确认是误判，可加 `--ignore-checkpoint` 继续，但不建议在出现验证或限流时继续运行。
- `--rest-every` / `--rest-minutes` 可定期长时间休息，适合几小时任务。
- `--restart-every` 会定期重启浏览器上下文，减少长跑内存和页面状态积累。
- 预览模式依赖当前搜索页状态，暂不执行 `--restart-every`；如果传入该参数，脚本会提示并忽略。
- 新标签页模式同样依赖当前搜索页状态，暂不执行 `--restart-every`；如果传入该参数，脚本会提示并忽略。
- 预览模式和新标签页模式会按当前屏幕附近的卡片顺序处理，并用带重叠的小步滚动继续向下扫描，以减少瀑布流虚拟列表跳跃造成的漏采。
- `--max-runtime-minutes` 可设置最大运行时长，到时平稳停止。
- `--block-media` 可选地屏蔽图片、视频、字体请求以减少带宽；如发现页面加载异常，请去掉该参数。
- 运行日志默认追加到 `data/xhs_scraper.log`。
- 连续详情或预览采集失败达到 `--max-errors` 后，脚本会暂停并等待人工接管浏览器；处理完成后按 Enter，或在图形界面点击“继续运行”。如果要结束任务，在终端输入 `q` 回车，图形界面可直接点“停止”。

## 项目结构

项目已按“工具箱”方向做模块化，保留 `xhs_scraper.py` 作为兼容命令行入口，核心逻辑放在 `xhs/` 包内：

- `xhs/cli.py`：命令行参数解析、校验和 runner 调用。
- `xhs/runner.py`：应用层运行编排、CSV 续跑、采集模式调度和节奏控制。
- `xhs/modes.py`：采集模式、GUI 任务文案、关键词任务解析。
- `xhs/search_scan.py`：搜索页扫描、卡片定位、滚动恢复等共享逻辑。
- `xhs/strategies.py`：预览层和新标签页策略接口。
- `xhs/browser.py`：Playwright 浏览器启动、登录、登录状态检查和异常页面检测。
- `xhs/search.py`：关键词搜索页滚动和笔记链接收集。
- `xhs/detail.py`：详情页打开、字段提取、调试文件保存。
- `xhs/preview.py` / `xhs/new_tab.py`：搜索页预览层、新标签页两种差异化采集策略。
- `xhs/csv_store.py`：CSV 读写、断点续跑、搜索链接表读取。
- `xhs/config.py` / `xhs/models.py`：默认配置、CSV 字段和数据结构。
- `xhs_gui.py`：Tkinter 图形界面，仍通过 `xhs_scraper.py` 启动采集子进程。
- `scripts/`：Windows 启动脚本。
- `docs/`：项目结构、维护说明和功能路线图。
- `data/`：本地输出目录，CSV 和日志默认不上传 GitHub。
- `.xhs_browser/`：本地浏览器资料目录，可能包含登录态，默认不上传 GitHub。

## 注意事项

- 小红书页面结构可能变化；如果某些字段为空，优先打开 `--debug` 保存的 HTML 和 JSON 排查选择器。
- 搜索页卡片中可点击链接可能是 `/search_result/{note_id}?xsec_token=...`，脚本会规范化为 `/explore/{note_id}?xsec_token=...&xsec_source=pc_search` 后保存。
- 如果页面要求重新登录或出现验证，请手动处理；脚本不会绕过验证。
- 如果搜索结果链接收集不足，可以增大 `--max-scrolls` 或降低滚动速度。
