import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication

from collage import TEMPLATES, collage_geometry, render_collage, CollageEditor
from store import History

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


def solid(color,width=120,height=80):
    image=QImage(width,height,QImage.Format_RGB32)
    image.fill(QColor(color))
    return image


class CollageRenderTests(unittest.TestCase):
    def test_every_template_contains_every_image_without_overlapping(self):
        images=[solid(color) for color in ('red','green','blue','yellow','purple')]
        for template,_ in TEMPLATES:
            with self.subTest(template=template):
                size,rects=collage_geometry(images,template,(640,480),12,16)
                self.assertEqual(len(rects),len(images))
                bounds=QRectF(0,0,640,480)
                self.assertTrue(all(bounds.contains(rect) for rect in rects))
                for i,rect in enumerate(rects):
                    self.assertFalse(any(rect.intersects(other) for other in rects[i+1:]))
                rendered=render_collage(images,template,(640,480),fit='cover',radius=0)
                self.assertEqual(rendered.size(),size)
                for image,rect in zip(images,rects):
                    self.assertEqual(rendered.pixelColor(rect.center().toPoint()),image.pixelColor(0,0))

    def test_automatic_long_strip_keeps_source_proportions(self):
        images=[solid('red',100,50),solid('blue',50,100)]
        image=render_collage(images,'vertical',gap=0,padding=0,radius=0)
        self.assertEqual((image.width(),image.height()),(1080,2700))
        self.assertEqual(image.pixelColor(500,100),QColor('red'))
        self.assertEqual(image.pixelColor(500,600),QColor('blue'))
        horizontal=render_collage(images,'horizontal',gap=0,padding=0,radius=0)
        self.assertEqual((horizontal.width(),horizontal.height()),(1800,720))

    def test_contain_cover_padding_and_transparency(self):
        image=solid('red',200,100)
        painter=QPainter(image)
        painter.fillRect(50,0,100,100,QColor('green'))
        painter.end()
        contained=render_collage([image],canvas=(100,100),gap=0,padding=0,radius=0,background='white')
        self.assertEqual(contained.pixelColor(50,5),QColor('white'))
        self.assertEqual(contained.pixelColor(50,50),QColor('green'))
        covered=render_collage([image],canvas=(100,100),padding=0,fit='cover',radius=0)
        self.assertEqual(covered.pixelColor(5,5),QColor('green'))
        transparent=render_collage([image],canvas=(100,100),padding=10,background=QColor(Qt.transparent),radius=12)
        self.assertEqual(transparent.pixelColor(0,0).alpha(),0)
        self.assertEqual(transparent.pixelColor(50,50),QColor('green'))

    def test_excessive_spacing_and_huge_export_are_actionable(self):
        images=[solid('red')]*12
        with self.assertRaisesRegex(ValueError,'间距'):
            render_collage(images,'vertical',(100,100),80,10)
        with self.assertRaisesRegex(ValueError,'成图过大'):
            render_collage([solid('red',10,1000)]*3,'vertical')
        preview=render_collage([solid('red',10,1000)]*3,'vertical',preview=True)
        self.assertLessEqual(max(preview.width(),preview.height()),900)


class CollageEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.history=History(Path(self.temp.name)/'history.db')
        self.editor=CollageEditor(self.history)

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        app.processEvents()
        self.history.close()
        self.temp.cleanup()

    def test_order_templates_export_and_removal(self):
        self.editor.add_images([(solid('red'),'第一张'),(solid('blue'),'第二张'),(QImage(),'无效')])
        self.assertEqual(self.editor.sources.count(),2)
        self.editor.sources.setCurrentRow(0)
        self.editor.move_source(1)
        self.assertEqual(self.editor.images()[0].pixelColor(0,0),QColor('blue'))
        for key,_ in TEMPLATES:
            self.editor.template_buttons[key].click()
            self.assertEqual(self.editor.template,key)
            self.assertFalse(self.editor.preview.image.isNull())
        self.editor.canvas_box.setCurrentIndex(1)
        self.editor.update_preview()
        received=[]
        self.editor.output_ready.connect(lambda image,action:received.append((image,action)))
        self.editor.export('copy')
        self.assertEqual(received[-1][1],'copy')
        self.assertEqual((received[-1][0].width(),received[-1][0].height()),(1080,1080))
        self.editor.remove_source()
        self.assertEqual(self.editor.sources.count(),1)
        self.assertTrue(all(not button.isEnabled() for button in self.editor.export_buttons))

    def test_save_png_and_jpeg_and_cancel(self):
        self.editor.add_images([(solid('red'),'红'),(solid('blue'),'蓝')])
        self.assertEqual(self.editor.background.alpha(),0)
        received=[]
        self.editor.output_ready.connect(lambda image,action:received.append(action))
        with patch('collage.QFileDialog.getSaveFileName',return_value=('','')):
            self.editor.export('save')
        self.assertFalse(received)
        for suffix in ('.png','.jpg'):
            path=Path(self.temp.name)/('拼图'+suffix)
            with patch('collage.QFileDialog.getSaveFileName',return_value=(str(path),'')):
                self.editor.export('save')
            saved=QImage(str(path))
            self.assertFalse(saved.isNull())
            self.assertEqual(received[-1],'save')
            if suffix=='.png':
                self.assertEqual(saved.pixelColor(0,0).alpha(),0)
            else:
                self.assertGreater(saved.pixelColor(0,0).red(),240)


if __name__=='__main__':
    unittest.main()
