"""Render public documentation with synthetic data; never capture the desktop."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtWidgets import QApplication
from capture import CaptureOverlay
from clipboard_ui import ClipboardPanel
from collage import CollageEditor
from qa_fixtures import make_scene
from store import History, png_bytes
from ui import STYLE
from settings_ui import SettingsPanel, DEFAULTS


def main():
    app = QApplication([])
    app.setStyleSheet(STYLE)
    output = ROOT / 'docs' / 'screenshots'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        history = History(Path(folder) / 'demo.sqlite3')
        scene = make_scene()
        examples = [
            ('text', '把灵感留住，把重点说清。\n\n轻匣 · 你的本地工作台', b''),
            ('image', '演示图片', png_bytes(scene)),
            ('link', 'https://example.com/notes', b''),
            ('color', '#2F8E7A', b''),
            ('text', '今日待办\n整理资料 · 截图说明 · 拼图分享', b'')]
        for entry in reversed(examples):
            history.add(entry, '演示内容')
        panel = ClipboardPanel(history)
        panel.resize(1440, 324)
        panel.refresh()
        panel.ensurePolished()
        panel.layout().activate()
        assert panel.grab().save(str(output / 'clipboard.png'))

        overlay = CaptureOverlay(scene, QRect(0, 0, 1470, 956))
        overlay.selection = QRectF(54, 175, 1360, 450)
        overlay.ops = [
            {'tool': 'rect', 'a': (520, 297), 'b': (914, 468), 'color': '#2F8E7A', 'width': 3},
            {'tool': 'arrow', 'a': (1030, 565), 'b': (915, 460), 'color': '#2F8E7A', 'width': 3},
            {'tool': 'text', 'a': (720, 550), 'b': (1030, 595), 'color': '#2F8E7A', 'width': 3,
             'font_size': 22, 'text': '直接标注，清楚表达'}]
        overlay.update_toolbar()
        assert overlay.grab().save(str(output / 'annotation.png'))

        collage = CollageEditor(history)
        collage.add_images([(scene.copy(x, 380, w, 690), title) for x, w, title in
                            [(128, 840, '随手收集'), (1020, 840, '清晰表达'), (1912, 900, '本地整理')]])
        collage.set_template('hero_left')
        collage.ensurePolished()
        collage.layout().activate()
        app.processEvents()
        assert collage.grab().save(str(output / 'collage.png'))
        settings = SettingsPanel(SimpleNamespace(preferences=lambda: dict(DEFAULTS),
                                                 open_data=lambda: None, history=history, panel=panel))
        settings.nav.setCurrentRow(1)
        settings.ensurePolished()
        settings.layout().activate()
        assert settings.grab().save(str(output / 'settings.png'))
        for widget in (panel, overlay, collage, settings):
            widget.close()
        history.close()
    print('Rendered four public-safe application screenshots.')


if __name__ == '__main__':
    main()
