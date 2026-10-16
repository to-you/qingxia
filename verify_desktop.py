"""Deterministic visual fixtures and a real clipboard/capture smoke test."""
import json
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, QRect, QRectF, QMimeData, QUrl, QTimer
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QKeySequenceEdit, QDialogButtonBox
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

from main import DesktopTools
from capture import CaptureOverlay
from store import png_bytes, read_mime, make_mime
from ui import STYLE
from qa_fixtures import make_scene
import native

root = Path(__file__).resolve().parent
artifacts = root/'artifacts'
artifacts.mkdir(exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setStyleSheet(STYLE)
original = app.clipboard().mimeData()
backup = QMimeData()
for fmt in original.formats():
    backup.setData(fmt,original.data(fmt))
temp = tempfile.TemporaryDirectory()
controller = DesktopTools(app,Path(temp.name),register_hotkeys=False)
failures = []
errors = []
import sys
sys.excepthook = lambda kind,value,tb: errors.append(str(value))

def check(condition, label):
    if not condition:
        failures.append(label)
    print(('PASS ' if condition else 'FAIL ') + label,flush=True)

try:
    app.clipboard().setText('剪贴板真实监听验证')
    QTest.qWait(400)
    check(any(i['text']=='剪贴板真实监听验证' for i in controller.history.items()),'system clipboard text recorded')
    image = QImage(320,180,QImage.Format_RGB32)
    image.fill(QColor('#4a90ca'))
    app.clipboard().setImage(image)
    QTest.qWait(400)
    check(controller.history.items()[0]['kind']=='image','system clipboard image recorded')
    path = Path(temp.name)/'验证文件.txt'
    path.write_text('sample',encoding='utf-8')
    mime=QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    app.clipboard().setMimeData(mime)
    QTest.qWait(400)
    check(controller.history.items()[0]['kind']=='file','system clipboard file recorded')
    controller.history.clear()
    scene=make_scene()
    thumb=scene.copy(1020,380,840,690)
    examples=[
        ('file',json.dumps([QUrl.fromLocalFile(str(Path(temp.name)/'download.zip')).toString()]),b''),
        ('image','840 × 690',png_bytes(thumb)),
        ('link','https://example.com/notes',b''),
        ('color','#2F8E7A',b''),
        ('color','#E9D6A3',b''),
        ('text','轻匣收集随手复制的内容。\n\n把图片整理成拼图，用标注说明重点。',b'')]
    for payload in reversed(examples):
        controller.history.add(payload, 'Chrome' if payload[0] in ('image','link') else '资源管理器')
    # A controlled background fixture, used only for visual QA, never shipped as app UI.
    background=QLabel(None,Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    background.setGeometry(0,0,1470,956)
    wallpaper=scene.scaled(1470,956,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    background.setPixmap(QPixmap.fromImage(wallpaper))
    background.show()
    background.activateWindow()
    native.user32.ShowWindow(int(background.winId()),5)
    QTest.qWait(150)
    native.activate(int(background.winId()))
    controller.panel.setGeometry(12,622,1446,324)
    controller.panel.refresh()
    controller.panel.select(1)
    controller.panel.show()
    controller.panel.activateWindow()
    native.activate(int(controller.panel.winId()))
    QTest.qWait(300)
    app.primaryScreen().grabWindow(0,0,0,1470,956).save(str(artifacts/'clipboard-desktop.png'))
    app.primaryScreen().grabWindow(0,12,622,1446,324).save(str(artifacts/'clipboard-panel.png'))
    controller.panel.search.setText('#2F8')
    QTest.qWait(80)
    check(len(controller.panel.rows)==1 and controller.panel.rows[0]['kind']=='color','search filters actual cards')
    controller.panel.search.clear()
    controller.panel.filter('image')
    check(len(controller.panel.rows)==1,'type filter')
    item=controller.panel.rows[0]
    controller.panel.star(item)
    controller.panel.filter('starred')
    check(len(controller.panel.rows)==1,'favorite filter')
    controller.panel.hide()

    # Render selection and annotations at the same logical scale as the source.
    overlay=CaptureOverlay(scene,QRect(0,0,1470,956))
    overlay.selection=QRectF(333,183,717,379)
    overlay.update_toolbar()
    overlay.show()
    overlay.activateWindow()
    QTest.qWait(150)
    app.primaryScreen().grabWindow(0,0,0,1470,956).save(str(artifacts/'screenshot-desktop.png'))
    overlay.set_tool('arrow')
    QTest.mousePress(overlay,Qt.LeftButton,pos=__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(450,300))
    QTest.mouseMove(overlay,__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(760,240),delay=20)
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(760,240))
    overlay.set_tool('rect')
    from PySide6.QtCore import QPoint
    QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(410,330))
    QTest.mouseMove(overlay,QPoint(550,450),delay=20)
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(550,450))
    overlay.set_tool('step')
    QTest.mouseClick(overlay,Qt.LeftButton,pos=QPoint(700,400))
    result=overlay.export_image()
    check(len(overlay.ops)==3,'arrow rectangle and step tools create annotations')
    check(result.size().width()==1434 and result.height()==758,'native resolution export')
    overlay.set_tool('text')
    QTest.mouseClick(overlay,Qt.LeftButton,pos=QPoint(700,440))
    check(overlay.text_editor is not None and app.activeModalWidget() is None,'inline text editor without dialog')
    overlay.text_editor.insertPlainText('直接在截图上输入文字')
    QTest.qWait(100)
    app.primaryScreen().grabWindow(0,0,0,1470,956).save(str(artifacts/'inline-text-desktop.png'))
    QTest.keyClick(overlay.text_editor,Qt.Key_Return,Qt.ControlModifier)
    check(overlay.ops[-1]['text']=='直接在截图上输入文字','inline text committed')
    QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(710,450))
    QTest.mouseMove(overlay,QPoint(740,470),delay=20)
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(740,470))
    check(overlay.ops[-1].get('offset')==(30,20),'text annotation moved by direct drag')
    result=overlay.export_image()
    result.save(str(artifacts/'annotated-output.png'))
    overlay.set_tool('select')
    QTest.qWait(150)
    app.primaryScreen().grabWindow(0,0,0,1470,956).save(str(artifacts/'annotation-desktop.png'))
    overlay.close()
    overlay.deleteLater()
    background.hide()

    # Verify actual desktop capture service, not a generated canvas alone.
    target=QPlainTextEdit()
    target.setPlainText('轻匣 · Windows 截图与剪贴板验证\n\n这是真实窗口，用于验证截图和自动粘贴。')
    target.setGeometry(200,150,800,500)
    target.show()
    target.activateWindow()
    target.setFocus()
    QTest.qWait(150)
    controller.capture()
    QTest.qWait(350)
    check(len(controller.overlays)==len(app.screens()),'real screen capture per display')
    live=controller.overlays[0]
    live.selection=QRectF(220,180,600,300)
    live.update_toolbar()
    live.finished.emit(live.export_image(),'copy')
    QTest.qWait(120)
    check(app.clipboard().image().width()==600,'capture finished into system clipboard')
    check(controller.history.items()[0]['source']=='截图标注','screenshot persisted in history')
    target.activateWindow()
    target.setFocus()
    QTest.qWait(250)
    controller.target=int(target.winId())
    controller.history.add(('text','自动贴回真实窗口',b''))
    item=controller.history.items()[0]
    target.clear()
    controller.paste(item)
    QTest.qWait(500)
    check(target.toPlainText()=='自动贴回真实窗口','history pasted into real target window')
    target.close()
    settings=controller.settings_dialog()
    QTest.qWait(120)
    for page,name in enumerate(('general','shortcuts','clipboard')):
        settings.nav.setCurrentRow(page)
        QTest.qWait(40)
        settings.grab().save(str(artifacts/f'settings-{name}.png'))
    settings.nav.setCurrentRow(1)
    settings.edits['clipboard_shortcut'].setKeySequence(QKeySequence('Ctrl+Shift+F10'))
    settings.edits['capture_shortcut'].setKeySequence(QKeySequence('Ctrl+Shift+F11'))
    settings.edits['image_shortcut'].setKeySequence(QKeySequence('Ctrl+Shift+F12'))
    QTest.mouseClick(settings.apply_button,Qt.LeftButton)
    check(controller.clipboard_shortcut=='Ctrl+Shift+F10' and controller.capture_shortcut=='Ctrl+Shift+F11','global shortcuts saved from settings panel')
    settings.close()
    check(not errors,'no unhandled Qt callbacks: '+repr(errors))
finally:
    controller.shutdown()
    app.clipboard().setMimeData(backup)
    app.processEvents()
    temp.cleanup()
report={'failed':failures,'callback_errors':errors,'platform':app.platformName(),'screens':[(s.geometry().getRect(),s.devicePixelRatio()) for s in app.screens()]}
(artifacts/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(1 if failures or errors else 0)
