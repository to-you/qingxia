import logging
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QStandardPaths, QLockFile, QSettings, QUrl
from PySide6.QtGui import QCursor, QImage, QKeySequence, QDesktopServices
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QFileDialog, QMessageBox

import native
from capture import CaptureOverlay, PinWindow
from clipboard_ui import ClipboardPanel
from store import History, read_mime, make_mime, png_bytes
from ui import icon, STYLE, brand_icon
from scrolling import ScrollSession
from clipboard_win import read_snapshot
from collage import CollageEditor
from settings_ui import SettingsPanel,DEFAULTS
import autostart

SHORTCUT_KEYS=('clipboard_shortcut','capture_shortcut','image_shortcut')


class DesktopTools:
    def __init__(self, app, data_dir, register_hotkeys=True):
        self.app = app
        self.settings=QSettings(str(data_dir/'settings.ini'),QSettings.IniFormat)
        for key in SHORTCUT_KEYS:
            setattr(self,key,self.settings.value(key,DEFAULTS[key]))
        self.settings_window=None
        self.collage_window=None
        self.history = History(data_dir / 'history.sqlite3')
        self.panel = ClipboardPanel(self.history)
        self.panel.set_shortcuts(*(getattr(self,key) for key in SHORTCUT_KEYS))
        self.panel.dismiss_on_outside=self.settings.value('dismiss_on_outside',True,type=bool)
        self.panel.paste_requested.connect(self.paste)
        self.panel.copy_requested.connect(self.copy)
        self.panel.capture_requested.connect(self.capture)
        self.panel.open_requested.connect(self.open_image)
        self.panel.annotate_requested.connect(self.annotate_item)
        self.panel.settings_requested.connect(self.settings_dialog)
        self.panel.collage_requested.connect(self.open_collage)
        self.mouse_clicks=native.MouseClicks(self.panel.outside_click)
        self.panel.visibility_changed.connect(self.mouse_clicks.watching)
        self.overlays, self.pins = [], []
        self.scroll_session = None
        self.target = None
        self.suppressed = False
        self.ignore_sequence = None
        self.last_sequence = None
        self.read_failures = 0
        self.capture_pending = False
        self.clipboard_timer = QTimer()
        self.clipboard_timer.setSingleShot(True)
        self.clipboard_timer.setInterval(80)
        self.clipboard_timer.timeout.connect(self.record)
        self.app.clipboard().dataChanged.connect(self.clipboard_changed)
        self.sequence_timer = QTimer()
        self.sequence_timer.setInterval(250)
        self.sequence_timer.timeout.connect(self.check_clipboard)
        self.sequence_timer.start()
        self.tray = QSystemTrayIcon(brand_icon(), app)
        self.tray.setToolTip('轻匣 · 剪贴板与截图标注')
        menu = QMenu()
        menu.setStyleSheet(STYLE)
        self.clipboard_action=menu.addAction(icon('PASTE'), '剪贴板    '+self.clipboard_shortcut, self.show_panel)
        self.capture_action=menu.addAction(icon('CAMERA'), '截图标注  '+self.capture_shortcut, self.capture)
        self.image_action=menu.addAction(icon('EDIT'), '标注图片  '+self.image_shortcut, self.open_image)
        menu.addAction(icon('LAYOUT'),'多图拼接',self.open_collage)
        menu.addAction(icon('SETTING'),'设置…',self.settings_dialog)
        menu.addSeparator()
        self.pause_action = menu.addAction('暂停记录剪贴板')
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self.set_paused)
        self.pause_action.setChecked(not self.settings.value('record_clipboard',True,type=bool))
        menu.addAction('打开数据目录', self.open_data)
        menu.addAction('使用说明', self.help)
        menu.addSeparator()
        menu.addAction('退出', app.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_panel() if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        self.hotkeys = None
        if register_hotkeys:
            self.hotkeys = native.Hotkeys([
                ('V', self.clipboard_shortcut, self.show_panel), ('S', self.capture_shortcut, self.capture),
                ('E', self.image_shortcut, self.open_image)])
            app.installNativeEventFilter(self.hotkeys)
            if self.hotkeys.failed:
                QTimer.singleShot(500, lambda: self.notify('快捷键冲突：' + '、'.join(self.hotkeys.failed) + '。可从托盘菜单打开。'))
        self.data_dir = data_dir
        self.clipboard_timer.start(120)
        app.aboutToQuit.connect(self.shutdown)

    def notify(self, text):
        self.tray.showMessage('轻匣', text, QSystemTrayIcon.Information, 3500)

    def clipboard_changed(self):
        if not self.suppressed and not self.pause_action.isChecked():
            self.clipboard_timer.start()

    def check_clipboard(self):
        if native.user32.GetClipboardSequenceNumber() != self.last_sequence:
            self.record()

    def record(self):
        sequence = native.user32.GetClipboardSequenceNumber()
        if self.pause_action.isChecked() or sequence == self.ignore_sequence:
            return
        snapshot = read_snapshot()
        if snapshot is None:
            self.clipboard_timer.start(120)
            return
        sequence, payload = snapshot
        if payload is None:
            payload = read_mime(self.app.clipboard().mimeData())
        if payload is None and self.read_failures < 3:
            self.read_failures += 1
            self.clipboard_timer.start(120)
            return
        self.read_failures = 0
        self.last_sequence = sequence
        if payload:
            self.history.add(payload, native.source_name())
            if self.panel.isVisible():
                self.panel.refresh()

    def current_screen(self):
        return self.app.screenAt(QCursor.pos()) or self.app.primaryScreen()

    def show_panel(self):
        if self.overlays or self.capture_pending or self.scroll_session:
            return
        if self.panel.isVisible() and self.panel.motion!='closing':
            self.panel.dismiss()
            return
        if not self.panel.isVisible():
            self.target = native.foreground()
        self.record()
        self.panel.search.clear()
        self.panel.filter('all')
        self.panel.open_at(self.current_screen())
        native.user32.ShowWindow(int(self.panel.winId()),5)
        native.activate(int(self.panel.winId()))

    def preferences(self):
        values={key:getattr(self,key) for key in SHORTCUT_KEYS}
        values.update(autostart=autostart.enabled(),
            show_on_launch=self.settings.value('show_on_launch',True,type=bool),
            record_clipboard=not self.pause_action.isChecked(),
            dismiss_on_outside=self.panel.dismiss_on_outside)
        return values

    def apply_preferences(self,values):
        values=dict(values)
        sequences=[QKeySequence(values[key]).toString(QKeySequence.PortableText) for key in SHORTCUT_KEYS]
        try:
            codes=[native.hotkey_code(sequence) for sequence in sequences]
        except ValueError as error:
            return False,str(error)
        if len(set(codes))!=len(codes):
            return False,'全局快捷键不能重复，请换一组。'
        old=[getattr(self,key) for key in SHORTCUT_KEYS]
        if self.hotkeys:
            ok,error=self.hotkeys.replace_all(sequences)
            if not ok:
                return False,error
        try:
            if bool(values['autostart'])!=autostart.enabled():
                autostart.set_enabled(values['autostart'])
        except OSError as error:
            if self.hotkeys:
                self.hotkeys.replace_all(old)
            return False,'无法修改开机自启动：'+str(error)
        for key,sequence in zip(SHORTCUT_KEYS,sequences):
            setattr(self,key,sequence)
            values[key]=sequence
        self.panel.set_shortcuts(*sequences)
        self.clipboard_action.setText('剪贴板    '+self.clipboard_shortcut)
        self.capture_action.setText('截图标注  '+self.capture_shortcut)
        self.image_action.setText('标注图片  '+self.image_shortcut)
        self.pause_action.setChecked(not values['record_clipboard'])
        self.panel.dismiss_on_outside=bool(values['dismiss_on_outside'])
        for key,value in values.items():
            if key!='autostart':
                self.settings.setValue(key,value)
        self.settings.sync()
        return True,''

    def set_paused(self,paused):
        self.tray.setToolTip('轻匣 · 已暂停记录' if paused else '轻匣 · 剪贴板与截图标注')
        self.settings.setValue('record_clipboard',not paused)

    def settings_dialog(self):
        self.panel.hide()
        if self.settings_window is None:
            self.settings_window=SettingsPanel(self)
        elif not self.settings_window.isVisible():
            self.settings_window.load(self.preferences())
        self.settings_window.show()
        self.settings_window.raise_()
        native.user32.ShowWindow(int(self.settings_window.winId()),5)
        native.activate(int(self.settings_window.winId()))
        return self.settings_window

    def copy(self, item):
        self.clipboard_timer.stop()
        self.suppressed = True
        self.app.clipboard().setMimeData(make_mime(item))
        self.ignore_sequence = native.user32.GetClipboardSequenceNumber()
        self.last_sequence = self.ignore_sequence
        self.suppressed = False
        self.panel.hint.setText('已复制，可切换窗口后按 Ctrl+V 粘贴。')

    def paste(self, item):
        if item['kind'] == 'file':
            from PySide6.QtCore import QUrl
            import json
            if any(not Path(QUrl(url).toLocalFile()).exists() for url in json.loads(item['text'])):
                self.notify('原文件已移动或删除，请重新复制文件。')
                return
        self.copy(item)
        self.panel.hide()
        native.paste_to(self.target, lambda ok: None if ok else self.notify('已复制。未能自动粘贴，请在目标窗口按 Ctrl+V。'))

    def capture(self):
        if self.overlays or self.capture_pending or self.scroll_session:
            return
        self.panel.hide()
        self.capture_pending = True
        QTimer.singleShot(180, self.begin_capture)

    def begin_capture(self):
        self.capture_pending = False
        windows = native.visible_windows()
        # Freeze every display before showing any overlay, avoiding captured overlays.
        snapshots = [(s.grabWindow(0).toImage(), s.geometry()) for s in self.app.screens()]
        for image, geometry in snapshots:
            if image.isNull():
                continue
            overlay = CaptureOverlay(image, geometry, windows)
            self.connect_overlay(overlay)
            overlay.show()
        if not self.overlays:
            self.notify('无法获取屏幕画面，请检查远程桌面或系统截图限制。')
            return
        active = next((o for o in self.overlays if o.geometry().contains(QCursor.pos())), self.overlays[0])
        active.raise_()
        active.activateWindow()
        active.setFocus()

    def connect_overlay(self, overlay):
        self.overlays.append(overlay)
        overlay.finished.connect(self.capture_finished)
        overlay.canceled.connect(self.close_overlays)
        overlay.activated.connect(self.select_screen)
        overlay.scroll_requested.connect(self.start_scroll)

    def start_scroll(self,overlay):
        if overlay.ops:
            self.notify('请在长截图拼接完成后再添加标注。')
            return
        screen = self.app.screenAt(overlay.geometry().center())
        selection = overlay.selection.toRect().translated(overlay.geometry().topLeft())
        first_frame = overlay.export_image(use_preset=False)
        self.close_overlays()
        session = ScrollSession(screen,selection,first_frame)
        self.scroll_session = session
        session.finished.connect(self.finish_scroll)
        session.canceled.connect(self.cancel_scroll)
        session.show()
        native.user32.ShowWindow(int(session.winId()),5)

    def finish_scroll(self,image,action='edit'):
        session = self.scroll_session
        self.scroll_session = None
        if session:
            session.deleteLater()
        if action == 'edit':
            self.edit_image(image)
        else:
            self.capture_finished(image,action)

    def cancel_scroll(self):
        session = self.scroll_session
        self.scroll_session = None
        if session:
            session.deleteLater()

    def select_screen(self, chosen):
        for overlay in self.overlays:
            if overlay != chosen:
                overlay.hide()

    def close_overlays(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def capture_finished(self, image, action, source='截图标注'):
        self.close_overlays()
        self.history.add(('image', f'{image.width()} × {image.height()}', png_bytes(image)), source)
        if action == 'copy':
            self.suppressed = True
            self.app.clipboard().setImage(image)
            self.ignore_sequence = native.user32.GetClipboardSequenceNumber()
            self.last_sequence = self.ignore_sequence
            self.suppressed = False
        elif action == 'pin':
            pin = PinWindow(image)
            self.pins.append(pin)
            pin.setAttribute(Qt.WA_DeleteOnClose)
            pin.destroyed.connect(lambda: self.pins.remove(pin) if pin in self.pins else None)
            pin.show()
        elif action == 'save':
            self.notify('截图已保存，也已加入剪贴板历史。')

    def open_collage(self,items=None):
        if self.overlays or self.capture_pending or self.scroll_session:
            return
        self.panel.hide()
        if self.collage_window is None:
            self.collage_window=CollageEditor(self.history)
            self.collage_window.output_ready.connect(self.collage_finished)
        if isinstance(items,list) and items:
            self.collage_window.add_images([(QImage.fromData(item['image']),'剪贴板图片') for item in items if item['kind']=='image'])
        self.collage_window.update_preview()
        self.collage_window.show()
        native.user32.ShowWindow(int(self.collage_window.winId()),5)
        native.activate(int(self.collage_window.winId()))
        return self.collage_window

    def collage_finished(self,image,action):
        if action=='edit':
            self.edit_image(image)
        else:
            self.capture_finished(image,action,source='多图拼接')

    def open_image(self):
        if self.overlays or self.capture_pending or self.scroll_session:
            return
        self.panel.hide()
        path, _ = QFileDialog.getOpenFileName(None, '打开图片标注', '', '图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:
            image = QImage(path)
            if image.isNull():
                self.notify('无法读取这张图片。')
            else:
                self.edit_image(image)

    def annotate_item(self, item):
        self.panel.hide()
        self.edit_image(QImage.fromData(item['image']))

    def edit_image(self, image):
        overlay = CaptureOverlay(image, self.current_screen().geometry(), editing=True)
        self.connect_overlay(overlay)
        overlay.show()
        overlay.activateWindow()
        overlay.setFocus()

    def open_data(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_dir.resolve()))):
            self.notify('无法打开数据目录：'+str(self.data_dir))

    def help(self):
        QMessageBox.information(None, '轻匣 · 使用说明',
            self.clipboard_shortcut+'：剪贴板\n'+self.capture_shortcut+'：截图标注\n'+self.image_shortcut+'：标注已有图片\n\n'
            '剪贴板：双击 / Enter 粘贴；Alt+1–9 快速粘贴；右键收藏、标签、删除。\n'
            '多图拼接：按 Ctrl 单击多选图片，再点击“拼图”；也可从托盘打开并导入本地图片。\n'
            '截图：拖动框选或单击选择窗口；拖动边缘控制点调整选区。\n'
            '工具栏“尺寸”：选择小红书、抖音、微博、公众号、X 或 Instagram 模板，按比例构图并导出指定像素尺寸。\n'
            '标注：箭头、矩形、椭圆、文字、高亮、画笔、序号、马赛克及图片贴纸。\n'
            '点击截图直接输入文字；Ctrl+Enter 或点击空白完成，Enter 换行。\n'
            '已有标注可直接拖动；双击文字原位编辑；V 工具拖动空白区移动选区。\n'
            'Ctrl+Z / Ctrl+Y 撤销与重做；Ctrl+S 保存；Enter 复制完成；Esc 取消。\n\n'
            '历史仅保存在本机，未收藏记录最多 200 条。文件记录引用原路径，不备份文件。\n'
            '长截图：选区工具栏点击滚动图标，在原页面向下滚动，滚动过程中连续截取并实时预览。\n'
            '本版不含 OCR、录屏和云同步。')

    def shutdown(self):
        self.mouse_clicks.close()
        self.clipboard_timer.stop()
        self.sequence_timer.stop()
        self.app.clipboard().dataChanged.disconnect(self.clipboard_changed)
        if self.hotkeys:
            self.hotkeys.close()
            self.app.removeNativeEventFilter(self.hotkeys)
        self.close_overlays()
        if self.scroll_session:
            self.scroll_session.close()
        self.panel.close()
        if self.settings_window:
            self.settings_window.close()
        if self.collage_window:
            self.collage_window.close()
        for pin in list(self.pins):
            pin.close()
        self.tray.hide()
        self.history.close()


def resolve_data_dir():
    root=Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation))
    data_dir=root/'QingXia'/'data'
    data_dir.parent.mkdir(parents=True,exist_ok=True)
    # Compatibility paths contain only this application's earlier local data.
    for legacy in (root/'FloatTools'/'data',root/'FloatTools'/'浮贴'):
        if legacy.is_dir() and not data_dir.exists():
            legacy.rename(data_dir)
            break
    data_dir.mkdir(parents=True,exist_ok=True)
    return data_dir


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from release_check import run
        return run(sys.argv[2])
    app = QApplication(sys.argv)
    app.setApplicationName('轻匣')
    app.setApplicationVersion(Path(__file__).with_name('VERSION').read_text(encoding='utf-8').strip())
    app.setOrganizationName('QingXia')
    app.setWindowIcon(brand_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    data_dir = resolve_data_dir()
    logging.basicConfig(filename=data_dir/'error.log', level=logging.ERROR)

    def error_hook(kind, value, tb):
        logging.error('Unhandled exception', exc_info=(kind, value, tb))
        QMessageBox.warning(None, '轻匣', '操作未完成，错误已写入数据目录的 error.log。')
    sys.excepthook = error_hook
    lock = QLockFile(str(data_dir/'app.lock'))
    if not lock.tryLock(100):
        if '--background' not in sys.argv:
            QMessageBox.information(None, '轻匣', '程序已在运行，请使用已设置的快捷键或系统托盘打开。')
        return 0
    try:
        autostart.migrate_legacy()
    except OSError:
        logging.exception('Unable to migrate the existing sign-in startup entry')
    controller = DesktopTools(app, data_dir)
    if '--background' not in sys.argv and controller.settings.value('show_on_launch',True,type=bool):
        QTimer.singleShot(200, controller.show_panel)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
