"""Continuous scrolling capture with verified overlap matching."""
from collections import Counter
import zlib

from PySide6.QtCore import Qt, Signal, QTimer, QRect, QRectF, QSize
from PySide6.QtGui import QImage, QPainter, QColor, QPixmap, QPen, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QFileDialog, QMessageBox

from ui import STYLE
from pathlib import Path


def detect_alignment(previous,current):
    if previous.size()!=current.size() or previous==current:
        return None
    def rows(image):
        width=96
        image=image.scaled(width,image.height(),Qt.IgnoreAspectRatio,Qt.FastTransformation).convertToFormat(QImage.Format_Grayscale8)
        raw=bytes(image.constBits())
        stride=image.bytesPerLine()
        return [raw[y*stride+8:y*stride+width-8] for y in range(image.height())]
    old,new=rows(previous),rows(current)
    height=len(old)
    # Stationary page headers and footers must appear only once in the result.
    top=bottom=0
    limit=height//3
    while top<limit and old[top]==new[top]:
        top+=1
    while bottom<limit and old[height-bottom-1]==new[height-bottom-1]:
        bottom+=1
    positions={}
    for y in range(top,height-bottom):
        row=old[y]
        if max(row)-min(row)>10:
            positions.setdefault(zlib.crc32(row),[]).append(y)
    votes=Counter()
    for y in range(top,height-bottom):
        matches=positions.get(zlib.crc32(new[y]),())
        if len(matches)<=4:
            for old_y in matches:
                delta=old_y-y
                if 0<delta<height-top-bottom-24:
                    votes[delta]+=1
    for delta,count in votes.most_common(5):
        end=height-bottom-delta
        length=end-top
        if count<max(12,length//10):
            continue
        samples=range(top,end,max(1,length//80))
        scores=[sum(abs(a-b) for a,b in zip(old[y+delta],new[y]))/len(new[y]) for y in samples]
        if scores and sum(score<6 for score in scores)/len(scores)>=0.9:
            return height-delta,top,bottom
    # A playing video can invalidate most rows. Match independent horizontal
    # regions instead, so unchanged page content can still establish the shift.
    positions={}
    for y,row in enumerate(old):
        for column in range(4):
            cell=row[column*20:(column+1)*20]
            if max(cell)-min(cell)>10:
                positions.setdefault((column,zlib.crc32(cell)),[]).append(y)
    anchors={}
    for y,row in enumerate(new):
        for column in range(4):
            cell=row[column*20:(column+1)*20]
            matches=positions.get((column,zlib.crc32(cell)),())
            if len(matches)<=4:
                for old_y in matches:
                    delta=old_y-y
                    if 0<=delta<height-24:
                        anchors.setdefault(delta,set()).add((y,column))
    candidates=sorted(anchors,key=lambda delta:len(anchors[delta]),reverse=True)
    # Prefer real downward page movement over a stationary sidebar.
    candidates=[delta for delta in candidates if delta>0][:5]+([0] if 0 in anchors else [])
    for delta in candidates:
        points=anchors[delta]
        if delta>0 and len(points)<len(anchors.get(0,()))*0.7:
            continue
        supported_rows={y for y,column in points}
        length=height-delta
        if len(supported_rows)<12 or max(supported_rows)-min(supported_rows)<min(48,length//3):
            continue
        good_rows=[]
        for y in range(0,length,max(1,length//120)):
            for column in range(4):
                a=old[y+delta][column*20:(column+1)*20]
                b=new[y][column*20:(column+1)*20]
                if max(a)-min(a)>10 and sum(abs(x-z) for x,z in zip(a,b))/20<4:
                    good_rows.append(y)
                    break
        if len(good_rows)>=max(8,min(20,length//12)):
            return height-delta,top,bottom
    return None


def detect_overlap(previous,current):
    alignment=detect_alignment(previous,current)
    return alignment[0] if alignment else None


def join_frames(previous,current,overlap,bottom=0):
    result=QImage(previous.width(),previous.height()+current.height()-overlap,QImage.Format_ARGB32_Premultiplied)
    result.fill(Qt.white)
    p=QPainter(result)
    p.drawImage(0,0,previous)
    # Replace the old fixed footer, append only new page content, then keep the new footer.
    start=overlap-bottom
    p.drawImage(0,previous.height()-bottom,current.copy(0,start,current.width(),current.height()-start))
    p.end()
    return result


class ScrollOutline(QWidget):
    def __init__(self,selection):
        super().__init__(None,Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(selection.adjusted(-2,-2,2,2))

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setPen(QPen(QColor('#29b993'),2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(1,1,-2,-2))


class ScrollSession(QWidget):
    finished = Signal(QImage,str)
    canceled = Signal()

    def __init__(self, screen, selection, first_frame):
        super().__init__(None,Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('轻匣 · 滚动长截图')
        self.setStyleSheet(STYLE)
        self.screen,self.selection=screen,selection
        self.canvas=first_frame.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self.result_height=first_frame.height()
        self.last=first_frame
        self.context_last=None
        self.count=1
        self.done=False
        self.closed=False
        self.capture_excluded=False
        self.setStyleSheet(STYLE+'QWidget#scrollPreview {background: #f8faf7; border: 1px solid #dce4dc; border-radius: 8px;}')
        self.setObjectName('scrollPreview')
        root=QVBoxLayout(self)
        root.setContentsMargins(5,5,5,6)
        root.setSpacing(5)
        self.preview=QLabel()
        self.preview.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        root.addWidget(self.preview)
        self.dimensions=QLabel()
        self.dimensions.setAlignment(Qt.AlignCenter)
        self.dimensions.setStyleSheet('font-size: 11px; color: #718077;')
        root.addWidget(self.dimensions)
        self.status=QLabel('向下滚动，自动拼接')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setFixedHeight(32)
        self.status.setStyleSheet('font-size: 11px; color: #718077;')
        root.addWidget(self.status)
        self.outline=ScrollOutline(selection)
        self.toolbar=QWidget(None,Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.toolbar.setWindowTitle('轻匣 · 长截图操作')
        self.toolbar.setObjectName('scrollActions')
        self.toolbar.setStyleSheet(STYLE+"""
            QWidget#scrollActions {background: #fafcf9; border-radius: 10px;}
            QToolButton {border: 0; background: transparent; border-radius: 8px;}
            QToolButton:hover {background: #e5eee6;}
        """)
        actions=QHBoxLayout(self.toolbar)
        actions.setContentsMargins(7,5,7,5)
        actions.setSpacing(6)
        for name,tip,callback in [
            ('pencil_ink','完成并标注',lambda: self.finish('edit')),
            ('save','保存长截图',self.save),
            ('close','取消',self.close),
            ('accept','复制并完成',lambda: self.finish('copy'))]:
            button=QToolButton()
            button.setIcon(QIcon(str(Path(__file__).parent/'assets'/'annotation'/(name+'.svg'))))
            button.setIconSize(QSize(20,20))
            button.setFixedSize(36,36)
            button.setToolTip(tip)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.toolbar.adjustSize()
        geo=screen.availableGeometry()
        self.preview_width=min(240,max(160,selection.width()//3))
        self.preview_limit=max(100,min(selection.height(),geo.height()-85))
        self.setFixedWidth(self.preview_width+12)
        x=selection.right()+12
        if x+self.width()>geo.right():
            x=selection.left()-self.width()-12
        if x<geo.left():
            x=geo.right()-self.width()-8
        self.move(x,max(geo.top()+6,min(selection.top(),geo.bottom()-self.preview_limit)))
        bar_x=max(geo.left()+6,min(selection.right()-self.toolbar.width(),geo.right()-self.toolbar.width()-6))
        bar_y=selection.bottom()+10
        if bar_y+self.toolbar.height()>geo.bottom():
            bar_y=selection.bottom()-self.toolbar.height()-10
        self.toolbar.move(bar_x,max(geo.top()+6,bar_y))
        self.timer=QTimer(self)
        self.timer.setInterval(33)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.grab)
        self.update_preview()

    def showEvent(self,event):
        super().showEvent(event)
        # Keep the live preview visible without capturing it into the page.
        import ctypes
        from ctypes import wintypes
        self.outline.show()
        self.toolbar.show()
        windows=(self,self.outline,self.toolbar)
        self.capture_excluded=all(bool(ctypes.windll.user32.SetWindowDisplayAffinity(
            wintypes.HWND(int(window.winId())),wintypes.DWORD(0x11))) for window in windows)
        if self.capture_excluded:
            self.context_last=self.screen.grabWindow(0).toImage()
            self.context_last.setDevicePixelRatio(1)
            self.status.setText('向下滚动，自动拼接')
            self.timer.start()
        else:
            self.status.setText('系统无法排除预览窗口，请取消后重新启动截图。')

    @property
    def result(self):
        return self.canvas.copy(0,0,self.canvas.width(),self.result_height)

    def append_frame(self,frame,overlap,bottom):
        height=self.result_height+frame.height()-overlap
        if height>self.canvas.height():
            capacity=min(30000,max(height,self.canvas.height()*2))
            canvas=QImage(self.canvas.width(),capacity,QImage.Format_ARGB32_Premultiplied)
            painter=QPainter(canvas)
            painter.drawImage(0,0,self.canvas)
            painter.end()
            self.canvas=canvas
        painter=QPainter(self.canvas)
        start=overlap-bottom
        painter.drawImage(0,self.result_height-bottom,frame,0,start,frame.width(),frame.height()-start)
        painter.end()
        self.result_height=height

    def update_preview(self):
        width=self.preview_width
        viewport=max(60,self.preview_limit-65)
        self.preview.setFixedSize(width,viewport)
        # Draw only the visible tail; the long image is never rescaled in full.
        scale=width/self.canvas.width()
        visible_height=min(self.result_height,viewport/scale)
        top=max(0,self.result_height-visible_height)
        pixmap=QPixmap(width,viewport)
        pixmap.fill(QColor('#f8faf7'))
        painter=QPainter(pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(QRectF(0,0,width,visible_height*scale),self.canvas,
                          QRectF(0,top,self.canvas.width(),visible_height))
        painter.end()
        self.preview.setPixmap(pixmap)
        self.dimensions.setText(f'{self.canvas.width()} × {self.result_height}')
        self.adjustSize()

    def grab(self):
        if self.closed or self.done:
            return
        context=self.screen.grabWindow(0).toImage()
        context.setDevicePixelRatio(1)
        r=self.selection.translated(-self.screen.geometry().topLeft())
        sx=context.width()/self.screen.geometry().width()
        sy=context.height()/self.screen.geometry().height()
        frame=context.copy(round(r.x()*sx),round(r.y()*sy),round(r.width()*sx),round(r.height()*sy))
        frame.setDevicePixelRatio(1)
        self.process_frame(frame,context)

    def process_frame(self,frame,context=None):
        if frame.isNull() or frame.size()!=self.last.size():
            self.status.setText('选区尺寸发生变化，请取消后重新截图。')
            self.timer.stop()
            return
        if frame==self.last:
            return
        alignment=detect_alignment(self.last,frame)
        if (alignment is None or alignment[0]==frame.height()) and context is not None and self.context_last is not None:
            surrounding=detect_alignment(self.context_last,context)
            if surrounding is not None:
                delta=context.height()-surrounding[0]
                if 0<=delta<frame.height():
                    alignment=(frame.height()-delta,0,0)
        if alignment is None:
            self.status.setText('未找到可靠重叠，请稍微向上回滚，再缓慢向下滚动。')
            return
        overlap,top,bottom=alignment
        if overlap==frame.height():
            self.status.setText('向下滚动，自动拼接')
            return
        if self.result_height+frame.height()-overlap>30000:
            self.timer.stop()
            self.status.setText('已达到 30000 像素，请完成当前截图。')
            return
        self.append_frame(frame,overlap,bottom)
        self.last=frame
        if context is not None:
            self.context_last=context
        self.count+=1
        self.update_preview()
        self.status.setText('继续向下滚动 · ✓ 完成')

    def save(self):
        self.timer.stop()
        path,_=QFileDialog.getSaveFileName(self,'保存长截图','长截图.png','PNG 图片 (*.png)')
        if path:
            if self.result.save(path):
                self.finish('save')
                return
            QMessageBox.warning(self,'保存失败','无法写入所选文件。')
        if not self.closed:
            self.timer.start()

    def finish(self,action='copy'):
        self.timer.stop()
        # Include the final scroll position between capture ticks.
        if action != 'save':
            self.grab()
        self.done=True
        self.hide()
        self.toolbar.hide()
        self.outline.hide()
        self.finished.emit(self.result,action)
        self.close()

    def closeEvent(self,event):
        self.closed=True
        self.timer.stop()
        self.toolbar.close()
        self.outline.close()
        self.toolbar.deleteLater()
        self.outline.deleteLater()
        if not self.done:
            self.canceled.emit()
        event.accept()
