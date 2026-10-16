# 代码结构

| 模块 | 职责 |
| --- | --- |
| main.py | 托盘、全局快捷键、窗口协调与数据迁移 |
| clipboard_win.py / native.py | Windows 剪贴板与原生窗口接口 |
| store.py | SQLite 历史、去重与筛选 |
| clipboard_ui.py | 剪贴板卡片面板 |
| capture.py | 框选、标注、导出与钉图 |
| scrolling.py | 连续捕获、重叠匹配与长图预览 |
| collage.py | 布局计算、拼图渲染与编辑界面 |
| settings_ui.py / autostart.py | 设置与当前用户自启动 |
| ui.py / assets | 公共样式、品牌与图标资源 |
| test_tools.py / test_collage.py | 回归测试 |
| scripts | 文档截图与版本构建 |

运行时数据与源码分离，保存在当前用户 LocalAppData 下。历史图片以 PNG 存入数据库，文件记录引用原路径。应用退出期间不会监听剪贴板。
