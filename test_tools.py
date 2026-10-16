"""Run with the real Windows Qt platform; all persisted test data is temporary."""
import ctypes
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import uuid
import winreg
from unittest.mock import patch
import autostart

from PySide6.QtCore import Qt, QMimeData, QUrl, QRect, QRectF, QPoint, QPointF
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QLabel

from store import History, png_bytes, read_mime, make_mime
from capture import CaptureOverlay, SIZE_PRESETS
from clipboard_ui import ClipboardPanel
from scrolling import detect_overlap, detect_alignment, join_frames, ScrollSession
import native

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'history.db'
        self.store = History(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_dedup_keeps_favorite_and_tag_across_restart(self):
        item_id = self.store.add(('text', '可恢复内容', b''))
        self.store.update(item_id, starred=True, tag='工作')
        self.store.add(('text', '可恢复内容', b''))
        self.store.close()
        self.store = History(self.path)
        rows = self.store.items('恢复', 'starred', '工作')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], item_id)

    def test_limit_preserves_favorites_and_clear(self):
        favorite = self.store.add(('text', '收藏内容', b''))
        self.store.update(favorite, starred=True)
        for i in range(205):
            self.store.add(('text', f'内容 {i}', b''))
        self.assertEqual(len(self.store.items()), 201)
        self.store.clear()
        self.assertEqual([row['id'] for row in self.store.items()], [favorite])

    def test_mime_images_files_links_colors(self):
        image = QImage(130, 80, QImage.Format_RGB32)
        image.fill(QColor('#c96f41'))
        mime = QMimeData()
        mime.setImageData(image)
        payload = read_mime(mime)
        self.store.add(payload)
        restored = make_mime(self.store.items()[0])
        self.assertEqual(QImage(restored.imageData()).pixelColor(5, 5), QColor('#c96f41'))
        file = Path(self.temp.name)/'中文 文件.txt'
        file.write_text('test', encoding='utf-8')
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(file))])
        payload = read_mime(mime)
        self.store.add(payload)
        self.assertEqual(make_mime(self.store.items()[0]).urls()[0].toLocalFile(), str(file).replace('\\', '/'))
        for text, kind in [('https://example.com', 'link'), ('#6f9400','color'), ('正常文本','text')]:
            mime = QMimeData()
            mime.setText(text)
            self.assertEqual(read_mime(mime)[0], kind)

    def test_literal_search_not_sql_wildcard(self):
        self.store.add(('text', '100% 完成', b''))
        self.store.add(('text', '其他', b''))
        self.assertEqual(len(self.store.items('%')), 1)


class CanvasTests(unittest.TestCase):
    def test_preset_expands_tiny_crop_and_switching_does_not_shrink_it(self):
        self.overlay.selection=QRectF(350,200,30,40)
        self.overlay.set_size_preset('小红书 · 竖图',(1080,1440))
        expected=QRectF(self.overlay.selection)
        self.assertGreater(expected.height(),400)
        for _ in range(5):
            self.overlay.set_size_preset('抖音 · 横屏',(1920,1080))
            self.overlay.set_size_preset('小红书 · 竖图',(1080,1440))
            self.assertEqual(self.overlay.selection.size(),expected.size())
            self.assertTrue(QRectF(self.overlay.rect()).contains(self.overlay.selection))

    def test_social_presets_export_exact_sizes_and_keep_free_native_mode(self):
        self.overlay.selection=QRectF(100,100,500,300)
        for platform,entries in SIZE_PRESETS:
            for title,width,height in entries:
                with self.subTest(platform=platform,title=title):
                    self.overlay.selection=QRectF(100,100,500,300)
                    self.overlay.set_size_preset(platform+' · '+title,(width,height))
                    r=self.overlay.selection
                    self.assertAlmostEqual(r.width()/r.height(),width/height)
                    image=self.overlay.export_image()
                    self.assertEqual((image.width(),image.height()),(width,height))
                    native_image=self.overlay.export_image(use_preset=False)
                    self.assertEqual(native_image.width(),round(r.width()*self.overlay.sx))
                    self.assertEqual(native_image.height(),round(r.height()*self.overlay.sy))
        self.overlay.set_size_preset('',None)
        r=self.overlay.selection
        image=self.overlay.export_image()
        self.assertEqual(image.width(),round(r.width()*self.overlay.sx))
        self.assertEqual(image.height(),round(r.height()*self.overlay.sy))

    def test_preset_resizing_and_new_crop_preserve_ratio_and_screen_bounds(self):
        self.overlay.selection=QRectF(200,100,300,250)
        self.overlay.set_size_preset('小红书 · 竖图',(1080,1440))
        original=QRectF(self.overlay.selection)
        for index,point in enumerate(self.overlay.handles()):
            r=self.overlay.ratio_resize(index,original,point+QPointF(55,35))
            self.assertAlmostEqual(r.width()/r.height(),0.75)
            self.assertTrue(QRectF(self.overlay.rect()).contains(r))
        self.overlay.selection=QRectF()
        self.drag((300,200),(790,490))
        r=self.overlay.selection
        self.assertAlmostEqual(r.width()/r.height(),0.75)
        self.assertTrue(QRectF(self.overlay.rect()).contains(r))

    def setUp(self):
        image = QImage(1600, 1000, QImage.Format_RGB32)
        image.fill(QColor('#eef3e8'))
        p = QPainter(image)
        p.fillRect(QRect(400,300,400,300), QColor('#125783'))
        p.end()
        self.overlay = CaptureOverlay(image, QRect(0,0,800,500))
        self.overlay.show()
        self.overlay.activateWindow()
        QTest.qWait(100)

    def tearDown(self):
        self.overlay.close()
        self.overlay.deleteLater()
        app.processEvents()

    def drag(self, start, end):
        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(*start))
        QTest.mouseMove(self.overlay, QPoint(*end), delay=10)
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(*end))

    def test_crop_native_resolution_and_arrow_undo_redo(self):
        self.drag((100,100),(600,350))
        result = self.overlay.export_image()
        self.assertEqual((result.width(),result.height()), (1000,500))
        self.assertEqual(result.pixelColor(300,200), QColor('#125783'))
        self.overlay.set_tool('arrow')
        self.drag((150,130),(400,210))
        self.assertEqual(len(self.overlay.ops), 1)
        result = self.overlay.export_image()
        self.assertNotEqual(result.pixelColor(400,156), QColor('#125783'))
        self.overlay.undo()
        self.assertEqual(len(self.overlay.ops), 0)
        self.overlay.redo()
        self.assertEqual(len(self.overlay.ops), 1)

    def test_mosaic_changes_pixels_and_selection_resize(self):
        self.overlay.selection = QRectF(100,100,500,250)
        self.overlay.set_tool('mosaic')
        self.drag((190,140),(410,310))
        self.assertEqual(self.overlay.ops[0]['tool'], 'mosaic')
        self.assertFalse(self.overlay.export_image().isNull())
        self.overlay.set_tool('select')
        self.drag((100,100),(80,80))
        self.assertEqual(self.overlay.selection.topLeft().toPoint(), QPoint(80,80))

    def test_import_preserves_original_resolution_and_crop(self):
        image = QImage(3000,2000,QImage.Format_RGB32)
        image.fill(QColor('#915cc5'))
        editor = CaptureOverlay(image,QRect(0,0,1200,800),editing=True)
        self.assertEqual(editor.export_image().size(),image.size())
        r = QRectF(editor.selection)
        r.setWidth(r.width()/2)
        editor.selection = r
        self.assertEqual(editor.export_image().width(),1500)
        self.assertEqual(editor.export_image().pixelColor(0,0),QColor('#915cc5'))
        editor.close()

    def test_sticker_undo_works_with_qimage(self):
        self.overlay.selection = QRectF(50,50,500,300)
        sticker = QImage(20,20,QImage.Format_RGB32)
        sticker.fill(QColor('red'))
        self.overlay.remember()
        self.overlay.ops.append({'tool':'sticker','a':(100,100),'b':(140,140),'color':'#ff0000','width':3,'image':sticker})
        self.overlay.remember()
        self.overlay.ops.append({'tool':'step','a':(200,200),'b':(214,214),'color':'#ff0000','width':3,'number':1})
        self.overlay.undo()
        self.assertEqual(len(self.overlay.ops),1)
        self.assertEqual(self.overlay.export_image().pixelColor(140,140),QColor('red'))

    def test_inline_text_typing_commit_move_and_edit(self):
        o=self.overlay
        o.selection=QRectF(100,100,500,250)
        o.set_tool('text')
        QTest.mouseClick(o,Qt.LeftButton,pos=QPoint(200,170))
        editor=o.text_editor
        self.assertIsNotNone(editor)
        self.assertEqual(editor.edit_font_size,20)
        self.assertIsNone(app.activeModalWidget())
        QTest.keyClicks(editor,'pVAr text')
        ime=QInputMethodEvent()
        ime.setCommitString('直接输入')
        app.sendEvent(editor,ime)
        self.assertIn('直接输入',editor.toPlainText())
        self.assertEqual(o.tool_name,'text')
        QTest.keyClick(editor,Qt.Key_Return,Qt.ControlModifier)
        self.assertIsNone(o.text_editor)
        self.assertEqual(o.ops[0]['text'],'pVAr text直接输入')
        self.assertEqual(o.ops[0]['font_size'],20)
        o.set_tool('arrow')
        self.drag((210,180),(250,210))
        self.assertEqual(o.ops[0]['offset'],(40,30))
        o.undo()
        self.assertNotIn('offset',o.ops[0])
        o.redo()
        QTest.mouseDClick(o,Qt.LeftButton,pos=QPoint(250,210))
        self.assertIsNotNone(o.text_editor)
        o.text_editor.selectAll()
        o.text_editor.insertPlainText('修改文字')
        QTest.keyClick(o.text_editor,Qt.Key_Return,Qt.ControlModifier)
        self.assertEqual(o.ops[0]['text'],'修改文字')
        self.assertFalse(o.export_image().isNull())

    def test_escape_cancels_only_inline_text(self):
        o=self.overlay
        o.selection=QRectF(100,100,500,250)
        o.set_tool('text')
        QTest.mouseClick(o,Qt.LeftButton,pos=QPoint(200,170))
        o.text_editor.insertPlainText('不要保存')
        QTest.keyClick(o.text_editor,Qt.Key_Escape)
        self.assertIsNone(o.text_editor)
        self.assertEqual(o.ops,[])
        self.assertTrue(o.isVisible())

    def test_drag_crop_on_empty_area(self):
        self.overlay.selection=QRectF(100,100,500,250)
        self.overlay.set_tool('select')
        self.drag((500,280),(540,300))
        self.assertEqual(self.overlay.selection,QRectF(140,120,500,250))


class NativeTests(unittest.TestCase):
    def test_replace_clipboard_shortcut_and_preserve_on_conflict(self):
        keys=native.Hotkeys([('J','Ctrl+Alt+J',lambda:None),('K','Ctrl+Alt+K',lambda:None)])
        try:
            self.assertEqual(keys.failed,[])
            self.assertTrue(keys.replace_clipboard('Ctrl+Shift+F10')[0])
            current=keys.clipboard_id
            self.assertEqual(keys.bindings[current],native.hotkey_code('Ctrl+Shift+F10'))
            self.assertFalse(keys.replace_clipboard('Ctrl+Alt+K')[0])
            self.assertEqual(keys.clipboard_id,current)
            self.assertFalse(keys.replace_clipboard('V')[0])
            self.assertEqual(keys.clipboard_id,current)
        finally:
            keys.close()

    def test_swap_global_shortcuts_preserves_callbacks(self):
        first,second=lambda:None,lambda:None
        keys=native.Hotkeys([('J','Ctrl+Alt+J',first),('K','Ctrl+Alt+K',second)])
        try:
            self.assertEqual(keys.failed,[])
            old=list(keys.action_ids)
            self.assertTrue(keys.replace_all(['Ctrl+Alt+K','Ctrl+Alt+J'])[0])
            self.assertEqual(keys.action_ids,old[::-1])
            self.assertIs(keys.callbacks[keys.action_ids[0]],first)
            self.assertIs(keys.callbacks[keys.action_ids[1]],second)
        finally:
            keys.close()
    def test_paste_into_real_window(self):
        old = app.clipboard().mimeData()
        saved = QMimeData()
        for fmt in old.formats():
            saved.setData(fmt,old.data(fmt))
        editor=QPlainTextEdit()
        editor.resize(400,200)
        editor.show()
        editor.raise_()
        editor.activateWindow()
        editor.setFocus()
        QTest.qWait(250)
        try:
            app.clipboard().setText('轻匣粘贴验证')
            result=[]
            native.paste_to(int(editor.winId()),result.append)
            QTest.qWait(400)
            self.assertEqual(result,[True], f'target={int(editor.winId())} foreground={native.foreground()}')
            self.assertEqual(editor.toPlainText(),'轻匣粘贴验证')
            self.assertGreater(len(native.visible_windows()),0)
        finally:
            app.clipboard().setMimeData(saved)
            editor.close()

    def test_hotkey_registration_and_release(self):
        keys=native.Hotkeys([('J','Ctrl+Alt+J',lambda:None)])
        try:
            self.assertEqual(keys.failed,[])
            self.assertEqual(ctypes.sizeof(native.INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
        finally:
            keys.close()


class ScrollingTests(unittest.TestCase):
    def video_frame(self,offset,phase,side=False):
        source=self.source()
        image=source.copy(0,offset,240,400)
        painter=QPainter(image)
        for y in range(260 if not side else 400):
            for x in range(0,240 if not side else 155,12):
                painter.fillRect(x,y,12,1,QColor((x*13+y*7+phase*43)%256,
                    (x*5+y*29+phase*71)%256,(x*19+y*11+phase*31)%256))
        painter.end()
        return image

    def test_scrolling_with_playing_video_uses_static_page_content(self):
        for side in (False,True):
            with self.subTest(side=side):
                first=self.video_frame(0,1,side)
                second=self.video_frame(60,2,side)
                self.assertEqual(detect_overlap(first,second),340)

    def test_video_playback_without_scrolling_does_not_append(self):
        first=self.video_frame(0,1)
        session=ScrollSession(app.primaryScreen(),QRect(0,0,240,400),first)
        try:
            for phase in range(2,5):
                session.process_frame(self.video_frame(0,phase))
            self.assertEqual(session.count,1)
            self.assertEqual(session.result_height,400)
            self.assertNotIn('未找到',session.status.text())
        finally:
            session.close()

    def test_moving_object_inside_video_is_not_page_movement(self):
        def frame(phase):
            image=self.source().copy(0,0,240,400)
            painter=QPainter(image)
            painter.fillRect(0,40,240,260,QColor((phase*37)%256,50,(phase*73)%256))
            painter.fillRect((phase*13)%190,100,45,90,QColor('white'))
            painter.end()
            return image
        session=ScrollSession(app.primaryScreen(),QRect(0,0,240,400),frame(0))
        try:
            for phase in range(1,12):
                session.process_frame(frame(phase))
            self.assertEqual(session.result_height,400)
            self.assertEqual(session.count,1)
        finally:
            session.close()

    def test_full_video_selection_keeps_first_still_and_uses_surroundings(self):
        first=QImage(240,400,QImage.Format_RGB32)
        first.fill(QColor('red'))
        video=QImage(240,400,QImage.Format_RGB32)
        video.fill(QColor('blue'))
        source=self.source()
        session=ScrollSession(app.primaryScreen(),QRect(0,0,240,400),first)
        try:
            session.context_last=source.copy(0,0,240,600)
            session.process_frame(video,source.copy(0,60,240,600))
            self.assertEqual(session.result_height,460)
            self.assertEqual(session.result.copy(0,0,240,400).convertToFormat(QImage.Format_RGB32),first)
            self.assertEqual(session.result.pixelColor(100,430),QColor('blue'))
        finally:
            session.close()

    def source(self):
        image=QImage(240,1200,QImage.Format_RGB32)
        painter=QPainter(image)
        for y in range(image.height()):
            painter.fillRect(0,y,240,1,QColor((y*17)%256,(y*31)%256,(y*7)%256))
            painter.fillRect((y*11)%200,y,30,1,QColor('white'))
        painter.end()
        return image

    def test_fixed_header_footer_are_not_repeated(self):
        source=self.source()
        def frame(offset):
            image=QImage(240,400,QImage.Format_RGB32)
            image.fill(QColor('gray'))
            painter=QPainter(image)
            painter.drawImage(0,30,source.copy(0,offset,240,340))
            painter.end()
            return image
        first,second=frame(0),frame(150)
        overlap,top,bottom=detect_alignment(first,second)
        self.assertEqual((overlap,top,bottom),(250,30,30))
        joined=join_frames(first,second,overlap,bottom)
        expected=QImage(240,550,QImage.Format_RGB32)
        expected.fill(QColor('gray'))
        painter=QPainter(expected)
        painter.drawImage(0,30,source.copy(0,0,240,490))
        painter.end()
        self.assertEqual(joined.convertToFormat(QImage.Format_RGB32),expected)

    def test_live_capture_immediately_appends_and_skips_duplicates(self):
        source=self.source()
        first,second=source.copy(0,0,240,400),source.copy(0,150,240,400)
        session=ScrollSession(app.primaryScreen(),QRect(0,0,240,400),first)
        try:
            session.process_frame(second)
            self.assertEqual(session.count,2)
            session.process_frame(second)
            self.assertEqual(session.count,2)
            self.assertEqual(session.result.convertToFormat(QImage.Format_RGB32),source.copy(0,0,240,550))
            session.process_frame(first)
            session.process_frame(first)
            self.assertEqual(session.count,2)
        finally:
            session.close()
        self.assertFalse(session.timer.isActive())

    def test_continuous_scroll_needs_no_repeated_or_stable_frames(self):
        source=self.source()
        session=ScrollSession(app.primaryScreen(),QRect(0,0,240,400),source.copy(0,0,240,400))
        try:
            preview_size=session.preview.size()
            for step,offset in enumerate(range(10,301,10),2):
                session.process_frame(source.copy(0,offset,240,400))
                self.assertEqual(session.count,step)
                self.assertEqual(session.preview.size(),preview_size)
            self.assertEqual(session.result.convertToFormat(QImage.Format_RGB32),source.copy(0,0,240,700))
            self.assertGreater(session.canvas.height(),session.result_height)
        finally:
            session.close()

    def test_growing_buffer_replaces_fixed_footer(self):
        source=self.source()
        def frame(offset):
            image=QImage(240,400,QImage.Format_RGB32)
            image.fill(QColor('gray'))
            painter=QPainter(image)
            painter.drawImage(0,30,source.copy(0,offset,240,340))
            painter.end()
            return image
        session=ScrollSession(app.primaryScreen(),QRect(0,0,240,400),frame(0))
        try:
            for offset in (150,300,450,600):
                session.process_frame(frame(offset))
            expected=QImage(240,1000,QImage.Format_RGB32)
            expected.fill(QColor('gray'))
            painter=QPainter(expected)
            painter.drawImage(0,30,source.copy(0,0,240,940))
            painter.end()
            self.assertEqual(session.result.convertToFormat(QImage.Format_RGB32),expected)
        finally:
            session.close()

    def test_overlap_and_join_keep_content(self):
        source=QImage(240,800,QImage.Format_RGB32)
        p=QPainter(source)
        for y in range(800):
            p.fillRect(0,y,240,1,QColor((y*17)%256,(y*31)%256,(y*7)%256))
            p.fillRect((y*11)%200,y,30,1,QColor('#ffffff'))
        p.end()
        first=source.copy(0,0,240,400)
        second=source.copy(0,230,240,400)
        overlap=detect_overlap(first,second)
        self.assertEqual(overlap,170)
        joined=join_frames(first,second,overlap)
        self.assertEqual(joined.size(),source.copy(0,0,240,630).size())
        self.assertEqual(joined.pixelColor(100,500),source.pixelColor(100,500))

    def test_different_frames_require_manual_overlap(self):
        first=QImage(240,400,QImage.Format_RGB32)
        first.fill(QColor('red'))
        second=QImage(240,400,QImage.Format_RGB32)
        second.fill(QColor('blue'))
        self.assertIsNone(detect_overlap(first,second))
        self.assertEqual(join_frames(first,second,0).height(),800)


class ClipboardControllerTests(unittest.TestCase):
    def test_legacy_data_migrates_without_losing_settings(self):
        from main import resolve_data_dir
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            legacy=root/'FloatTools'/'data'
            legacy.mkdir(parents=True)
            (legacy/'settings.ini').write_text('[General]\nclipboard_shortcut=Ctrl+Shift+V\n',encoding='utf-8')
            (legacy/'history.sqlite3').write_bytes(b'preserved test data')
            with patch('main.QStandardPaths.writableLocation',return_value=folder):
                target=resolve_data_dir()
            self.assertEqual(target,root/'QingXia'/'data')
            self.assertEqual((target/'history.sqlite3').read_bytes(),b'preserved test data')
            self.assertIn('Ctrl+Shift+V',(target/'settings.ini').read_text(encoding='utf-8'))
            self.assertFalse(legacy.exists())

    def test_category_switch_reuses_cards_and_refreshes_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            history=History(Path(folder)/'history.db')
            text_id=history.add(('text','切换分类',b''))
            image=QImage(100,80,QImage.Format_RGB32)
            image.fill(QColor('red'))
            history.add(('image','100 × 80',png_bytes(image)))
            panel=ClipboardPanel(history)
            try:
                cards={card.item['id']:card for card in panel.cards}
                for category in ['text','image','all']*3:
                    panel.filter(category)
                    self.assertTrue(all(card is cards[card.item['id']] for card in panel.cards))
                    self.assertEqual([c.index_label.text() for c in panel.cards],
                                     [str(i) for i in range(1,len(panel.cards)+1)])
                history.update(text_id,starred=True,tag='工作')
                panel.filter('starred')
                self.assertEqual([row['id'] for row in panel.rows],[text_id])
                self.assertEqual(panel.cards[0].index_label.text(),'1 · 收藏')
                self.assertEqual(panel.cards[0].item['tag'],'工作')
                history.delete(text_id)
                panel.refresh()
                self.assertFalse(panel.cards)
            finally:
                panel.close()
                history.close()

    def test_open_data_uses_local_url_and_creates_missing_directory(self):
        from main import DesktopTools
        with tempfile.TemporaryDirectory() as folder:
            controller=DesktopTools.__new__(DesktopTools)
            controller.data_dir=Path(folder)/'中文 数据目录'
            with patch('main.QDesktopServices.openUrl',return_value=True) as opened:
                controller.open_data()
            self.assertTrue(controller.data_dir.is_dir())
            url=opened.call_args.args[0]
            self.assertTrue(url.isLocalFile())
            self.assertEqual(Path(url.toLocalFile()),controller.data_dir.resolve())

    def test_custom_shortcut_persists(self):
        from main import DesktopTools
        with tempfile.TemporaryDirectory() as folder:
            first=DesktopTools(app,Path(folder),register_hotkeys=False)
            values=first.preferences()
            values['clipboard_shortcut']='Ctrl+Shift+F10'
            values['capture_shortcut']='Ctrl+Shift+F11'
            values['image_shortcut']='Ctrl+Shift+F12'
            values['show_on_launch']=False
            values['dismiss_on_outside']=False
            self.assertTrue(first.apply_preferences(values)[0])
            first.shutdown()
            app.aboutToQuit.disconnect(first.shutdown)
            second=DesktopTools(app,Path(folder),register_hotkeys=False)
            try:
                self.assertEqual(second.clipboard_shortcut,'Ctrl+Shift+F10')
                self.assertIn('Ctrl+Shift+F10',second.clipboard_action.text())
                self.assertEqual(second.capture_shortcut,'Ctrl+Shift+F11')
                self.assertEqual(second.image_shortcut,'Ctrl+Shift+F12')
                self.assertFalse(second.preferences()['show_on_launch'])
                self.assertFalse(second.panel.dismiss_on_outside)
            finally:
                second.shutdown()
                app.aboutToQuit.disconnect(second.shutdown)

    def test_slide_and_real_outside_click(self):
        from main import DesktopTools
        original_cursor=app.primaryScreen().geometry().center()
        from PySide6.QtGui import QCursor
        original_cursor=QCursor.pos()
        with tempfile.TemporaryDirectory() as folder:
            controller=DesktopTools(app,Path(folder),register_hotkeys=False)
            target=QLabel('外部点击测试窗口',None,Qt.Tool | Qt.WindowStaysOnTopHint)
            target.setGeometry(50,50,400,200)
            target.show()
            try:
                controller.show_panel()
                start=controller.panel.y()
                self.assertEqual(controller.panel.motion,'opening')
                QTest.qWait(180)
                self.assertLess(controller.panel.y(),start)
                QTest.qWait(300)
                self.assertEqual(controller.panel.pos(),controller.panel.shown_pos)
                QTest.mouseClick(controller.panel.search,Qt.LeftButton)
                QTest.qWait(220)
                self.assertTrue(controller.panel.isVisible())
                # Native input exercises outside-click handling without touching other apps.
                native.user32.SetCursorPos(100,100)
                mouse=(native.INPUT*2)(native.INPUT(0,native.INPUTUNION(mi=native.MOUSEINPUT(0,0,0,2,0,0))),
                    native.INPUT(0,native.INPUTUNION(mi=native.MOUSEINPUT(0,0,0,4,0,0))))
                self.assertEqual(native.user32.SendInput(2,mouse,ctypes.sizeof(native.INPUT)),2)
                QTest.qWait(320)
                self.assertFalse(controller.panel.isVisible())
                controller.show_panel()
                QTest.qWait(80)
                controller.show_panel()
                QTest.qWait(240)
                self.assertFalse(controller.panel.isVisible())
            finally:
                native.user32.SetCursorPos(original_cursor.x(),original_cursor.y())
                target.close()
                controller.shutdown()
                app.aboutToQuit.disconnect(controller.shutdown)

    def test_external_copy_while_panel_hidden(self):
        from main import DesktopTools
        old=app.clipboard().mimeData()
        backup=QMimeData()
        for fmt in old.formats():
            backup.setData(fmt,old.data(fmt))
        with tempfile.TemporaryDirectory() as folder:
            controller=DesktopTools(app,Path(folder),register_hotkeys=False)
            try:
                controller.panel.hide()
                subprocess.run(['powershell','-NoProfile','-Command',"Set-Clipboard -Value 'qingxia-external-hidden-regression'"],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
                QTest.qWait(700)
                self.assertEqual(len(controller.history.items('qingxia-external-hidden-regression')),1)
                controller.panel.filter('image')
                controller.panel.search.setText('old-filter')
                controller.show_panel()
                self.assertEqual(controller.panel.category,'all')
                self.assertEqual(controller.panel.search.text(),'')
                self.assertEqual(controller.panel.rows[0]['text'],'qingxia-external-hidden-regression')
            finally:
                controller.shutdown()
                app.aboutToQuit.disconnect(controller.shutdown)
                app.clipboard().setMimeData(backup)


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.path=r'Software\QingXia\DevTests'+'\\'+uuid.uuid4().hex
        self.override=patch.object(autostart,'RUN_KEY',self.path)
        self.override.start()

    def tearDown(self):
        try:
            autostart.set_enabled(False)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,self.path)
        finally:
            self.override.stop()

    def test_current_user_startup_enable_and_disable(self):
        self.assertFalse(autostart.enabled())
        autostart.set_enabled(True)
        self.assertTrue(autostart.enabled())
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,self.path) as key:
            value,kind=winreg.QueryValueEx(key,autostart.VALUE_NAME)
        self.assertEqual(value,autostart.command())
        self.assertEqual(kind,winreg.REG_SZ)
        self.assertIn('--background',value)
        self.assertIn('"'+str(Path(autostart.__file__).with_name('main.py').resolve())+'"',value)
        autostart.set_enabled(False)
        self.assertFalse(autostart.enabled())

    def test_legacy_startup_is_renamed_only_for_this_application(self):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,self.path) as key:
            winreg.SetValueEx(key,'FloTools',0,winreg.REG_SZ,'other-app.exe')
        autostart.migrate_legacy()
        self.assertFalse(autostart.enabled())
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,self.path,0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,'FloTools',0,winreg.REG_SZ,autostart.command())
        autostart.migrate_legacy()
        self.assertTrue(autostart.enabled())
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,self.path) as key:
            self.assertEqual(winreg.QueryValueEx(key,autostart.VALUE_NAME)[0],autostart.command())
            with self.assertRaises(FileNotFoundError):
                winreg.QueryValueEx(key,'FloTools')

    def test_settings_apply_autostart_and_reject_duplicates(self):
        from main import DesktopTools
        with tempfile.TemporaryDirectory() as folder:
            controller=DesktopTools(app,Path(folder),register_hotkeys=False)
            try:
                values=controller.preferences()
                values['capture_shortcut']=values['clipboard_shortcut']
                values['autostart']=True
                self.assertFalse(controller.apply_preferences(values)[0])
                self.assertFalse(autostart.enabled())
                values['capture_shortcut']='Ctrl+Alt+S'
                values['record_clipboard']=False
                self.assertTrue(controller.apply_preferences(values)[0])
                self.assertTrue(autostart.enabled())
                self.assertTrue(controller.pause_action.isChecked())
            finally:
                controller.shutdown()
                app.aboutToQuit.disconnect(controller.shutdown)


if __name__ == '__main__':
    unittest.main(verbosity=2)
