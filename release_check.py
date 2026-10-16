"""Isolated packaged-runtime check, without clipboard or startup changes."""
import json
from pathlib import Path
import tempfile

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QToolButton

from capture import CaptureOverlay
from clipboard_ui import ClipboardPanel
from collage import CollageEditor, TEMPLATES, render_collage
from store import History
from ui import STYLE, brand_icon


def run(output):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    checks = {}
    with tempfile.TemporaryDirectory() as folder:
        history = History(Path(folder) / 'history.sqlite3')
        history.add(('text', 'QingXia release check', b''))
        panel = ClipboardPanel(history)
        panel.refresh()
        checks['clipboard_panel'] = len(panel.rows) == 1 and not panel.grab().isNull()
        checks['brand_asset'] = not brand_icon().isNull()
        image = QImage(640, 480, QImage.Format_ARGB32)
        image.fill(QColor('#2F8E7A'))
        overlay = CaptureOverlay(image, QRect(0, 0, 640, 480))
        overlay.selection = QRectF(0, 0, 640, 480)
        checks['capture_export'] = overlay.export_image().size() == image.size()
        checks['annotation_assets'] = not overlay.toolbar.findChildren(QToolButton)[0].icon().isNull()
        collage = CollageEditor(history)
        collage.add_images([(image, 'Demo A'), (image, 'Demo B')])
        checks['collage_window'] = not collage.grab().isNull()
        checks['collage_templates'] = all(not render_collage([image, image], key).isNull()
                                          for key, _ in TEMPLATES)
        for widget in (panel, overlay, collage):
            widget.close()
        history.close()
    Path(output).write_text(json.dumps(checks, indent=2), encoding='utf-8')
    return 0 if all(checks.values()) else 1
