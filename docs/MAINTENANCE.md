# 维护备忘

## 清理缓存

如果项目目录再次变大，通常是 `.xhs_browser/Default/Cache` 或 `.xhs_browser/Default/Code Cache` 增长。可以在不运行采集器时删除这些目录；下次启动浏览器会自动重建。

## 重建项目 Python 环境

```powershell
.\scripts\setup.ps1 -Force
```

这会删除并重建 `.venv/`，然后重新安装 `requirements.txt`。Playwright Chromium 仍使用默认用户缓存目录。

## 彻底清除登录状态

删除 `.xhs_browser/` 会移除登录态和浏览器会话。之后第一次运行需要重新扫码登录。

## 上传 GitHub 前检查

```powershell
git status --short --ignored
```

确认 `.xhs_browser/`、`data/` 下的 CSV/log 文件显示为 ignored，而源码和文档显示为 tracked 或待提交。
