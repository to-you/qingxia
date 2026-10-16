# 贡献指南

先创建 Issue 描述问题或修改范围。请保持修改集中，不提交本机剪贴板、数据库、密钥、日志或个人截图。

## 开发

Windows 64 位 Python 3.13；先按 README 创建项目虚拟环境，然后：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest test_tools test_collage -v
```

原生快捷键、截图与剪贴板测试需要交互式 Windows 桌面。`verify_desktop.py` 会短暂显示窗口并操作剪贴板，结束后恢复原有内容；请在空闲时运行。

```powershell
.\.venv\Scripts\python.exe verify_desktop.py
.\.venv\Scripts\python.exe scripts/generate_screenshots.py
.\.venv\Scripts\python.exe scripts/build_release.py
```

构建输出为 `dist/QingXia/` 和 `dist/QingXia-<版本>-windows-x64.zip`。这是完整目录便携版，不能只复制 EXE。`SHA256SUMS.txt` 用于核对下载文件。

## 发布流程

1. 完成修改并通过测试，人工验证托盘、快捷键、截图标注、长图、拼图和退出。
2. 更新 `VERSION` 与 `CHANGELOG.md`，兼容数据格式变更时先补迁移与回归测试。
3. 运行构建脚本，在 Windows 上验证解压后的程序。
4. 提交源码，创建对应 `vX.Y.Z` 标签；创建 GitHub Release 并上传 ZIP 和 SHA256SUMS.txt，填写用户可读的更新说明。
5. 有问题先修复并发布新的修订版本，不覆盖已有版本附件。

每次提交 main 或 Pull Request 会在 Windows runner 上运行 20 项适合无界面的测试并构建 EXE，再运行打包自检；Actions 中的构建附件保留 14 天。原生鼠标、全局快捷键和桌面截图仍需本机人工验证。正式 Release 由维护者检查并发布，不会自动覆盖附件。此项目没有云端服务或必填密钥。
