# 官网维护

官网地址：https://to-you.github.io/qingxia/

GitHub Pages 从 `main` 分支的 `/docs` 目录发布。页面使用原生 HTML、CSS 和少量 JavaScript，无需安装前端依赖或执行构建。`.nojekyll` 用于直接发布静态文件。

- `index.html`：页面结构、产品文案、下载与文档链接。
- `style.css`：桌面与手机布局。
- `site.js`：界面预览标签切换，支持键盘方向键。
- `screenshots/`：应用演示截图，与仓库文档共用。
- `assets/qingxia.svg`：官网使用的品牌图标。

本地预览：在仓库目录执行 `python -m http.server 8791 --directory docs`，然后访问 `http://localhost:8791/`。

更新后提交并推送至 `main`，GitHub Pages 会自动重新发布。下载链接使用 `/releases/latest`，会指向最新正式发布；新版本功能变化时仍需同步修改页面文案。官网本身不收集表单信息、不设置统计脚本或跟踪 Cookie；访问请求由 GitHub Pages 托管处理。
