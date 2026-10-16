import math
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QPoint, QPointF, QRect, QRectF, QSize, QEvent
from PySide6.QtGui import (QImage, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath,
    QPolygonF, QFont, QFontMetrics, QKeySequence, QShortcut, QTextCursor, QIcon)
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QFileDialog, QPlainTextEdit, QMessageBox, QColorDialog, QMenu)

from ui import Glass, STYLE, tool, icon


SIZE_PRESETS = (
    ('小红书', (('竖图',1080,1440),('方图',1080,1080))),
    ('抖音', (('竖屏',1080,1920),('横屏',1920,1080))),
    ('微博', (('方图',1080,1080),('竖图',1080,1440))),
    ('微信公众号', (('头条封面',900,383),('次条封面',500,500))),
    ('X / 推特', (('横图',1600,900),('主页封面',1500,500))),
    ('Instagram', (('竖图',1080,1440),('经典竖图',1080,1350),
                   ('方图',1080,1080),('限时动态',1080,1920))),
)


def annotation_tool(name, tip, callback, **kwargs):
    button = tool(name, tip, callback, **kwargs)
    button.setIcon(QIcon(str(Path(__file__).parent/'assets'/'annotation'/(name.lower()+'.svg'))))
    button.setIconSize(QSize(20, 20))
    return button


def clone_ops(ops):
    # QImage is implicitly shared and is not pickleable; only points are mutable.
    return [{**op, **({'points': list(op['points'])} if 'points' in op else {})} for op in ops]


def op_rect(op):
    if op['tool'] == 'pen':
        xs = [p[0] for p in op['points']]
        ys = [p[1] for p in op['points']]
        r = QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys))
    else:
        r = QRectF(QPointF(*op['a']), QPointF(*op['b'])).normalized()
    return r.translated(*op.get('offset', (0, 0))).adjusted(-8, -8, 8, 8)


def hit_op(op, point):
    offset = QPointF(*op.get('offset', (0,0)))
    point = point-offset
    a,b = QPointF(*op['a']),QPointF(*op['b'])
    r=QRectF(a,b).normalized()
    def near_segment(start,end):
        dx,dy=end.x()-start.x(),end.y()-start.y()
        length=dx*dx+dy*dy
        t=max(0,min(1,((point.x()-start.x())*dx+(point.y()-start.y())*dy)/length)) if length else 0
        return math.hypot(point.x()-start.x()-t*dx,point.y()-start.y()-t*dy) <= max(8,op['width']+3)
    kind=op['tool']
    if kind=='arrow':
        return near_segment(a,b)
    if kind=='pen':
        return any(near_segment(QPointF(*start),QPointF(*end)) for start,end in zip(op['points'],op['points'][1:]))
    if kind=='rect':
        return r.adjusted(-8,-8,8,8).contains(point) and not r.adjusted(8,8,-8,-8).contains(point)
    if kind=='ellipse' and r.width() and r.height():
        distance=math.hypot((point.x()-r.center().x())/(r.width()/2),(point.y()-r.center().y())/(r.height()/2))
        return abs(distance-1)*min(r.width(),r.height())/2 < 9
    if kind=='step':
        return math.hypot(point.x()-a.x(),point.y()-a.y()) < max(12,op['width']*4)+6
    return r.adjusted(-5,-5,5,5).contains(point)


class InlineText(QPlainTextEdit):
    committed = Signal()
    canceled = Signal()

    def event(self,event):
        if event.type()==QEvent.ShortcutOverride:
            if not (event.key()==Qt.Key_S and event.modifiers() & Qt.ControlModifier):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:
            self.canceled.emit()
        elif event.key() in (Qt.Key_Return,Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self.committed.emit()
        else:
            super().keyPressEvent(event)

def draw_op(p, op, base, sx, sy):
    p.save()
    p.translate(*op.get('offset', (0, 0)))
    color = QColor(op['color'])
    width = op['width']
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    a, b = QPointF(*op['a']), QPointF(*op['b'])
    rect = QRectF(a, b).normalized()
    kind = op['tool']
    if kind == 'rect':
        p.drawRoundedRect(rect, 3, 3)
    elif kind == 'ellipse':
        p.drawEllipse(rect)
    elif kind == 'arrow':
        dx, dy = b.x()-a.x(), b.y()-a.y()
        length = math.hypot(dx, dy)
        if length:
            ux, uy = dx/length, dy/length
            size = min(length, max(12, width*4))
            end = QPointF(b.x()-ux*size*.65, b.y()-uy*size*.65)
            p.drawLine(a, end)
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([b, QPointF(b.x()-ux*size-uy*size*.45, b.y()-uy*size+ux*size*.45),
                                     QPointF(b.x()-ux*size+uy*size*.45, b.y()-uy*size-ux*size*.45)]))
    elif kind == 'highlight':
        color.setAlpha(85)
        p.fillRect(rect, color)
    elif kind == 'pen':
        path = QPainterPath(QPointF(*op['points'][0]))
        for point in op['points'][1:]:
            path.lineTo(QPointF(*point))
        p.drawPath(path)
    elif kind == 'text':
        p.setFont(QFont('Microsoft YaHei UI', op['font_size']))
        p.drawText(rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, op['text'])
    elif kind == 'step':
        radius = max(12, width*4)
        p.setPen(QPen(Qt.white, 2))
        p.setBrush(color)
        p.drawEllipse(a, radius, radius)
        p.setPen(Qt.white)
        p.setFont(QFont('Segoe UI', 11, QFont.Bold))
        p.drawText(QRectF(a.x()-radius, a.y()-radius, radius*2, radius*2), Qt.AlignCenter, str(op['number']))
    elif kind == 'mosaic':
        dx, dy = op.get('offset', (0, 0))
        region = QRect(round((rect.x()+dx)*sx), round((rect.y()+dy)*sy), round(rect.width()*sx), round(rect.height()*sy)).intersected(base.rect())
        if not region.isEmpty():
            patch = base.copy(region)
            patch = patch.scaled(max(1, patch.width()//14), max(1, patch.height()//14), Qt.IgnoreAspectRatio, Qt.FastTransformation)
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.drawImage(rect, patch)
    elif kind == 'sticker':
        p.drawImage(rect, op['image'])
    p.restore()


class CaptureOverlay(QWidget):
    finished = Signal(QImage, str)
    canceled = Signal()
    activated = Signal(object)
    scroll_requested = Signal(object)

    def __init__(self, image, geometry, window_rects=(), editing=False):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('轻匣 · 截图与标注')
        self.setStyleSheet(STYLE)
        self.base = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self.base.setDevicePixelRatio(1)
        self.setGeometry(geometry)
        self.sx, self.sy = image.width()/geometry.width(), image.height()/geometry.height()
        self.windows = [QRect(*r).translated(-geometry.topLeft()).intersected(self.rect()) for r in window_rects]
        self.selection = QRectF()
        self.output_size = None
        self.preset_name = ''
        if editing:
            margin = 50
            ratio = min((self.width()-100)/image.width(), (self.height()-150)/image.height(), 1.0)
            width, height = image.width()*ratio, image.height()*ratio
            # Put the imported image on a neutral desktop-sized canvas at its display scale.
            canvas = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
            canvas.fill(QColor('#e8ece5'))
            p = QPainter(canvas)
            target = QRectF((self.width()-width)/2, (self.height()-height)/2-20, width, height)
            p.drawImage(target, image)
            p.end()
            self.base = canvas
            self.sx = self.sy = 1.0
            self.selection = target
            self.imported_rect = QRectF(target)
            self.imported_original = image
        self.tool_name = 'select'
        self.color = '#ff4b3e'
        self.stroke = 3
        self.font_size = 20
        self.ops, self.redo_ops = [], []
        self.pending, self.drag_mode, self.start = None, None, None
        self.hover = QRect()
        self.selected_op = None
        self.text_editor = None
        self.text_index = None
        self.drag_before = None
        self.undo_states, self.redo_states = [], []
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.toolbar = Glass(self)
        self.toolbar.radius = 12
        self.toolbar.setStyleSheet(STYLE + '''
            QToolButton {border: 0; border-radius: 9px; padding: 6px; background: transparent;}
            QToolButton:hover {background: rgba(81,112,95,23);}
            QToolButton:checked {background: #d8e6dc;}
        ''')
        layout = QVBoxLayout(self.toolbar)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(1)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.size_button=annotation_tool('FIT_PAGE','常用尺寸 / 自由选区',self.show_size_presets)
        self.size_button.setText('尺寸')
        self.size_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.size_button.setFixedWidth(78)
        row.addWidget(self.size_button)
        row.addSpacing(4)
        self.buttons = {}
        tools = [('select', 'MOVE', '移动选区 / 标注  V'), ('step', 'INFO', '步骤序号  N'),
                 ('rect', 'CHECKBOX', '矩形  R'), ('ellipse', 'PIE_SINGLE', '椭圆  O'),
                 ('arrow', 'RIGHT_ARROW', '箭头  A'), ('text', 'FONT', '文字  T'),
                 ('highlight', 'HIGHTLIGHT', '高亮  H'), ('pen', 'PENCIL_INK', '画笔  P'),
                 ('mosaic', 'TILES', '马赛克  M'), ('sticker', 'PHOTO', '导入贴纸图片')]
        for name, ico, tip in tools:
            button = annotation_tool(ico, tip, lambda checked=False, n=name: self.set_tool(n), checkable=True)
            row.addWidget(button)
            self.buttons[name] = button
        row.addSpacing(6)
        if not editing:
            row.addWidget(annotation_tool('SCROLL', '滚动长截图', lambda: self.scroll_requested.emit(self)))
        self.undo_button = annotation_tool('RETURN', '撤销  Ctrl+Z', self.undo)
        self.redo_button = annotation_tool('SYNC', '重做  Ctrl+Y', self.redo)
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        row.addWidget(annotation_tool('CLOSE', '取消  Esc', self.canceled.emit))
        row.addWidget(annotation_tool('PIN', '钉在桌面', lambda: self.finish('pin')))
        row.addWidget(annotation_tool('SAVE', '保存图片  Ctrl+S', lambda: self.finish('save')))
        done = annotation_tool('ACCEPT', '复制并完成  Enter', lambda: self.finish('copy'))
        row.addWidget(done)
        layout.addLayout(row)
        for i in range(row.count()):
            if row.itemAt(i).widget():
                row.itemAt(i).widget().setFixedHeight(32)
        self.options_widget = QWidget()
        options = QHBoxLayout(self.options_widget)
        options.setContentsMargins(9, 0, 9, 0)
        options.setSpacing(6)
        self.color_buttons = []
        for value in ['#ff4b3e', '#ffb52e', '#ffe84a', '#36c78b', '#3d9aff', '#ae77ef', '#ffffff', '#303632']:
            button = tool('PALETTE', value, lambda checked=False, c=value: self.set_color(c))
            button.setFixedSize(21, 21)
            button.setIconSize(QSize(17, 17))
            button.setIcon(icon('PALETTE', value))
            options.addWidget(button)
            self.color_buttons.append((value, button))
        options.addWidget(tool('ADD', '自定义颜色', self.choose_color))
        options.addWidget(QLabel('粗细'))
        self.width_box = QComboBox()
        self.width_box.addItems(['2', '3', '5', '8', '12'])
        self.width_box.setCurrentText('3')
        self.width_box.currentTextChanged.connect(lambda text: setattr(self, 'stroke', int(text)))
        options.addWidget(self.width_box)
        options.addWidget(QLabel('字号'))
        font_box = QComboBox()
        font_box.addItems(['14', '16', '20', '24', '32', '48'])
        font_box.setCurrentText('20')
        font_box.currentTextChanged.connect(self.set_font_size)
        options.addWidget(font_box)
        options.addStretch()
        self.size_label = QLabel()
        self.size_label.setStyleSheet('font-size: 11px; color: #7a8375;')
        options.addWidget(self.size_label)
        layout.addWidget(self.options_widget)
        self.toolbar.adjustSize()
        self.toolbar.hide()
        self.help_label = QLabel('拖动框选 · 单击选择窗口 · 双击复制 · Esc 取消', self)
        self.help_label.setStyleSheet('background: rgba(30,37,32,190); color: white; border-radius: 8px; padding: 10px 16px;')
        self.help_label.adjustSize()
        self.help_label.move((self.width()-self.help_label.width())//2, 20)
        self.set_tool('select')
        self.update_toolbar()
        QShortcut(QKeySequence('Escape'), self, self.canceled.emit)
        QShortcut(QKeySequence('Return'), self, lambda: self.finish('copy'))
        QShortcut(QKeySequence('Ctrl+S'), self, lambda: self.finish('save'))
        QShortcut(QKeySequence('Ctrl+Z'), self, self.undo)
        QShortcut(QKeySequence('Ctrl+Y'), self, self.redo)
        QShortcut(QKeySequence('Delete'), self, self.delete_selected)
        for key, name in [('V','select'),('N','step'),('R','rect'),('O','ellipse'),('A','arrow'),('T','text'),('H','highlight'),('P','pen'),('M','mosaic')]:
            QShortcut(QKeySequence(key), self, lambda n=name: self.set_tool(n))

    def show_size_presets(self):
        menu=QMenu(self)
        free=menu.addAction('自由选区 · 原始分辨率',lambda: self.set_size_preset('',None))
        free.setCheckable(True)
        free.setChecked(self.output_size is None)
        menu.addSeparator()
        for platform,entries in SIZE_PRESETS:
            group=menu.addMenu(platform)
            for title,width,height in entries:
                name=platform+' · '+title
                action=group.addAction(f'{title}    {width} × {height}',
                    lambda checked=False,n=name,s=(width,height): self.set_size_preset(n,s))
                action.setCheckable(True)
                action.setChecked(self.preset_name==name)
        menu.addSeparator()
        menu.addAction('按比例调整选区，导出为所选像素尺寸').setEnabled(False)
        menu.exec(self.size_button.mapToGlobal(self.size_button.rect().bottomLeft()))

    def set_size_preset(self,name,size):
        self.commit_text()
        self.preset_name,self.output_size=name,size
        self.size_button.setText('尺寸')
        self.size_button.setToolTip('常用尺寸 / 自由选区')
        if size is not None:
            width,height=size
            divisor=math.gcd(width,height)
            ratio_text=f'{width//divisor}:{height//divisor}' if height//divisor<20 else f'{width/height:.2f}:1'
            self.size_button.setText(ratio_text)
            self.size_button.setToolTip(f'{name} · 导出 {width} × {height} 像素')
            bounds=QRectF(self.imported_rect if hasattr(self,'imported_rect') else self.rect().adjusted(24,24,-24,-24))
            center=self.selection.center() if not self.selection.isEmpty() else bounds.center()
            ratio=self.preset_ratio()
            fitted_width=min(width/self.sx,bounds.width(),bounds.height()*ratio)
            fitted_height=fitted_width/ratio
            left=max(bounds.left(),min(center.x()-fitted_width/2,bounds.right()-fitted_width))
            top=max(bounds.top(),min(center.y()-fitted_height/2,bounds.bottom()-fitted_height))
            self.selection=QRectF(left,top,fitted_width,fitted_height)
        self.set_tool('select')

    def preset_ratio(self):
        return self.output_size[0]/self.output_size[1]*self.sy/self.sx

    def ratio_crop(self,anchor,point):
        ratio=self.preset_ratio()
        dx,dy=point.x()-anchor.x(),point.y()-anchor.y()
        width=max(abs(dx),abs(dy)*ratio,2)
        height=width/ratio
        max_width=anchor.x() if dx<0 else self.width()-anchor.x()
        max_height=anchor.y() if dy<0 else self.height()-anchor.y()
        scale=min(1,max_width/width,max_height/height)
        width,height=width*scale,height*scale
        return QRectF(anchor.x()-width if dx<0 else anchor.x(),
                      anchor.y()-height if dy<0 else anchor.y(),width,height)

    def ratio_resize(self,index,original,point):
        ratio=self.preset_ratio()
        if index%2==0:
            anchor=(original.bottomRight(),original.bottomLeft(),original.topLeft(),original.topRight())[index//2]
            return self.ratio_crop(anchor,point)
        center=original.center()
        if index in (3,7):
            anchor=original.left() if index==3 else original.right()
            dx=point.x()-anchor
            limit=anchor if dx<0 else self.width()-anchor
            width=min(max(2,abs(dx)),limit,2*min(center.y(),self.height()-center.y())*ratio)
            height=width/ratio
            return QRectF(anchor-width if dx<0 else anchor,center.y()-height/2,width,height)
        anchor=original.bottom() if index==1 else original.top()
        dy=point.y()-anchor
        limit=anchor if dy<0 else self.height()-anchor
        height=min(max(2,abs(dy)),limit,2*min(center.x(),self.width()-center.x())/ratio)
        width=height*ratio
        return QRectF(center.x()-width/2,anchor-height if dy<0 else anchor,width,height)

    def set_tool(self, name):
        self.commit_text()
        self.tool_name = name
        self.options_widget.setVisible(name != 'select')
        self.toolbar.adjustSize()
        for key, button in self.buttons.items():
            button.setChecked(key == name)
        self.selected_op = None
        self.setCursor(Qt.SizeAllCursor if name == 'select' and not self.selection.isEmpty() else Qt.CrossCursor)
        self.update_toolbar()
        self.update()

    def set_color(self, color):
        self.color = color
        if self.text_editor:
            self.style_text_editor()
        for value, button in self.color_buttons:
            button.setStyleSheet('background: rgba(100,120,100,50);' if value == color else '')

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, '标注颜色')
        if color.isValid():
            self.set_color(color.name())

    def style_text_editor(self):
        size=self.text_editor.edit_font_size
        self.text_editor.setStyleSheet(f'QPlainTextEdit {{background: rgba(255,255,255,15); border: 1px dashed #76a5ef; color: {self.color}; font-family: "Microsoft YaHei UI"; font-size: {size}pt; padding: 3px; selection-background-color: #88b5ec;}}')

    def begin_text(self,point,index=None):
        self.commit_text()
        self.text_index=index
        op=self.ops[index] if index is not None else None
        if op:
            point=QPointF(*op['a'])+QPointF(*op.get('offset',(0,0)))
            self.color=op['color']
        self.text_editor=InlineText(self)
        editor=self.text_editor
        editor.edit_font_size=op['font_size'] if op else self.font_size
        editor.setPlaceholderText('直接输入文字')
        editor.document().setDocumentMargin(0)
        editor.setFont(QFont('Microsoft YaHei UI',editor.edit_font_size))
        self.style_text_editor()
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.move(round(point.x())-4,round(point.y())-4)
        if op:
            editor.setPlainText(op['text'])
        editor.textChanged.connect(self.resize_text_editor)
        editor.committed.connect(self.commit_text)
        editor.canceled.connect(self.cancel_text)
        self.resize_text_editor()
        for shortcut in self.findChildren(QShortcut):
            if shortcut.key()!=QKeySequence('Ctrl+S'):
                shortcut.setEnabled(False)
        editor.show()
        editor.raise_()
        editor.setFocus()
        editor.moveCursor(QTextCursor.End)
        self.update()

    def resize_text_editor(self):
        editor=self.text_editor
        if editor is None:
            return
        text=editor.toPlainText()
        editor.ensurePolished()
        metrics=QFontMetrics(editor.font())
        max_width=max(50,int(self.selection.right()-editor.x()))
        width=min(max_width,max(160,max((metrics.horizontalAdvance(line) for line in text.split('\n')),default=0)+18))
        bound=metrics.boundingRect(QRect(0,0,max(1,width-10),10000),Qt.TextWordWrap,text or '输入文字')
        height=min(max(32,int(self.selection.bottom()-editor.y())),max(38,bound.height()+12))
        editor.resize(width,height)

    def commit_text(self):
        if self.text_editor is None:
            return
        editor,index=self.text_editor,self.text_index
        self.text_editor,self.text_index=None,None
        editor.committed.disconnect(self.commit_text)
        editor.canceled.disconnect(self.cancel_text)
        text=editor.toPlainText()
        if text.strip():
            op={'tool':'text','a':(editor.x()+4,editor.y()+4),'b':(editor.x()+editor.width()-4,editor.y()+editor.height()-4),
                'color':self.color,'width':self.stroke,'font_size':editor.edit_font_size,'text':text}
            self.remember()
            if index is None:
                self.ops.append(op)
            else:
                self.ops[index]=op
            self.selected_op=len(self.ops)-1 if index is None else index
        elif index is not None:
            self.remember()
            self.ops.pop(index)
            self.selected_op=None
        editor.hide()
        editor.deleteLater()
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(True)
        self.update_toolbar()
        self.set_tool('select')
        if text.strip():
            self.selected_op=len(self.ops)-1 if index is None else index
        self.update()

    def set_font_size(self,text):
        self.font_size=int(text)
        if self.text_editor is not None:
            self.text_editor.edit_font_size=self.font_size
            self.style_text_editor()
            self.resize_text_editor()

    def cancel_text(self):
        if self.text_editor is None:
            return
        editor=self.text_editor
        self.text_editor,self.text_index=None,None
        editor.committed.disconnect(self.commit_text)
        editor.canceled.disconnect(self.cancel_text)
        editor.hide()
        editor.deleteLater()
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(True)
        self.setFocus()
        self.update()

    def remember(self):
        self.undo_states.append(clone_ops(self.ops))
        self.redo_states.clear()

    def undo(self):
        if self.undo_states:
            self.redo_states.append(clone_ops(self.ops))
            self.ops = self.undo_states.pop()
            self.selected_op = None
            self.update_toolbar()
            self.update()

    def redo(self):
        if self.redo_states:
            self.undo_states.append(clone_ops(self.ops))
            self.ops = self.redo_states.pop()
            self.selected_op = None
            self.update_toolbar()
            self.update()

    def delete_selected(self):
        if self.selected_op is not None:
            self.remember()
            self.ops.pop(self.selected_op)
            self.selected_op = None
            self.update_toolbar()
            self.update()

    def update_toolbar(self):
        if self.selection.isEmpty():
            self.toolbar.hide()
            return
        self.help_label.hide()
        self.toolbar.show()
        self.toolbar.adjustSize()
        x = max(8, min(int(self.selection.center().x()-self.toolbar.width()/2), self.width()-self.toolbar.width()-8))
        y = int(self.selection.bottom()+12)
        if y+self.toolbar.height() > self.height()-8:
            above=int(self.selection.top()-self.toolbar.height()-12)
            y=above if above>=8 else max(8,int(self.selection.bottom()-self.toolbar.height()-12))
        self.toolbar.move(x, y)
        self.size_label.setText(f'{round(self.selection.width()*self.sx)} × {round(self.selection.height()*self.sy)}')
        if self.output_size:
            self.size_label.setText(f'导出 {self.output_size[0]} × {self.output_size[1]}')
        self.undo_button.setEnabled(bool(self.undo_states))
        self.redo_button.setEnabled(bool(self.redo_states))

    def handles(self):
        r = self.selection
        return [r.topLeft(), QPointF(r.center().x(), r.top()), r.topRight(),
                QPointF(r.right(), r.center().y()), r.bottomRight(),
                QPointF(r.center().x(), r.bottom()), r.bottomLeft(), QPointF(r.left(), r.center().y())]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawImage(QRectF(self.rect()), self.base)
        p.fillRect(self.rect(), QColor(10, 20, 18, 110))
        r = self.selection if not self.selection.isEmpty() else QRectF(self.hover)
        if not r.isEmpty():
            p.save()
            p.setClipRect(r)
            p.drawImage(QRectF(self.rect()), self.base)
            for index,op in enumerate(self.ops):
                if self.text_editor is None or index!=self.text_index:
                    draw_op(p, op, self.base, self.sx, self.sy)
            if self.pending:
                draw_op(p, self.pending, self.base, self.sx, self.sy)
            p.restore()
            p.setPen(QPen(QColor('#ffffff'), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            if self.output_size:
                sx,sy=self.sx,self.sy
                if hasattr(self,'imported_original'):
                    sx=self.imported_original.width()/self.imported_rect.width()
                    sy=self.imported_original.height()/self.imported_rect.height()
                caption=f'{self.preset_name}  原图 {round(r.width()*sx)} × {round(r.height()*sy)} → 导出 {self.output_size[0]} × {self.output_size[1]}'
                font=QFont(self.font())
                font.setPixelSize(12)
                p.setFont(font)
                width=QFontMetrics(font).horizontalAdvance(caption)+16
                left=max(4,min(r.left(),self.width()-width-4))
                top=max(4,r.top()-28)
                p.fillRect(QRectF(left,top,width,22),QColor(25,35,29,205))
                p.setPen(Qt.white)
                p.drawText(QPointF(left+8,top+15),caption)
            if not self.selection.isEmpty():
                p.setBrush(Qt.white)
                p.setPen(QPen(QColor('#cdd6d0'), .8))
                for point in self.handles():
                    p.drawEllipse(point, 3.5, 3.5)
            if self.selected_op is not None:
                p.setPen(QPen(QColor('#45a6ff'), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(op_rect(self.ops[self.selected_op]))
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.canceled.emit()
            return
        if event.button() != Qt.LeftButton:
            return
        point = event.position()
        self.commit_text()
        self.start = point
        self.activated.emit(self)
        if self.selection.isEmpty():
            self.drag_mode = 'crop'
            return
        if self.tool_name == 'select':
            for index, handle in enumerate(self.handles()):
                if (point-handle).manhattanLength() < 12:
                    self.drag_mode = ('resize', index, QRectF(self.selection))
                    self.setCursor(self.resize_cursor(index))
                    self.toolbar.hide()
                    return
        if not event.modifiers() & Qt.ShiftModifier:
            for index in range(len(self.ops)-1,-1,-1):
                if hit_op(self.ops[index],point):
                    if self.tool_name=='text' and self.ops[index]['tool']=='text':
                        self.begin_text(point,index)
                        return
                    self.selected_op=index
                    self.drag_before=clone_ops(self.ops)
                    self.drag_mode=('move',self.ops[index].get('offset',(0,0)))
                    self.setCursor(Qt.SizeAllCursor)
                    self.update()
                    return
        if self.tool_name == 'select':
            self.selected_op = None
            if self.selection.contains(point):
                self.drag_mode=('crop_move',QRectF(self.selection),
                    QRectF(self.imported_rect) if hasattr(self,'imported_rect') else None,clone_ops(self.ops))
                self.toolbar.hide()
                self.setCursor(Qt.SizeAllCursor)
                return
            if not self.selection.contains(point) and not self.ops:
                self.selection = QRectF()
                self.drag_mode = 'crop'
                self.toolbar.hide()
            self.update()
            return
        if not self.selection.contains(point):
            return
        op = {'tool': self.tool_name, 'a': (point.x(),point.y()), 'b': (point.x(),point.y()),
              'color': self.color, 'width': self.stroke}
        if self.tool_name == 'text':
            self.begin_text(point)
            return
        if self.tool_name == 'step':
            op['number'] = sum(o['tool'] == 'step' for o in self.ops)+1
            op['b'] = (point.x()+14,point.y()+14)
            self.remember()
            self.ops.append(op)
            self.update_toolbar()
            self.update()
            return
        if self.tool_name == 'sticker':
            path, _ = QFileDialog.getOpenFileName(self, '导入贴纸', '', '图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
            image = QImage(path) if path else QImage()
            if not image.isNull():
                op['image'] = image
                width = min(150, self.selection.right()-point.x())
                op['b'] = (point.x()+width,point.y()+min(width*image.height()/image.width(), self.selection.bottom()-point.y()))
                self.remember()
                self.ops.append(op)
                self.update_toolbar()
                self.update()
            return
        if self.tool_name == 'pen':
            op['points'] = [op['a']]
        self.pending = op
        self.drag_mode = 'draw'

    def mouseMoveEvent(self, event):
        point = event.position()
        if self.drag_mode == 'crop':
            self.selection = self.ratio_crop(self.start,point) if self.output_size else QRectF(self.start, point).normalized().intersected(QRectF(self.rect()))
            self.update()
        elif self.drag_mode == 'draw' and self.pending:
            point.setX(max(self.selection.left(), min(point.x(),self.selection.right())))
            point.setY(max(self.selection.top(), min(point.y(),self.selection.bottom())))
            self.pending['b'] = (point.x(),point.y())
            if self.pending['tool'] == 'pen':
                self.pending['points'].append(self.pending['b'])
            self.update()
        elif isinstance(self.drag_mode, tuple) and self.drag_mode[0] == 'move':
            offset = self.drag_mode[1]
            self.ops[self.selected_op]['offset'] = (offset[0]+point.x()-self.start.x(), offset[1]+point.y()-self.start.y())
            self.update()
        elif isinstance(self.drag_mode, tuple) and self.drag_mode[0] == 'resize':
            _, index, original = self.drag_mode
            r = QRectF(original)
            if index in (0, 6, 7): r.setLeft(point.x())
            if index in (2, 3, 4): r.setRight(point.x())
            if index in (0, 1, 2): r.setTop(point.y())
            if index in (4, 5, 6): r.setBottom(point.y())
            self.selection = self.ratio_resize(index,original,point) if self.output_size else r.normalized().intersected(QRectF(self.rect()))
            self.update()
        elif isinstance(self.drag_mode,tuple) and self.drag_mode[0]=='crop_move':
            original=self.drag_mode[1]
            delta=point-self.start
            dx=max(-original.left(),min(delta.x(),self.width()-original.right()))
            dy=max(-original.top(),min(delta.y(),self.height()-original.bottom()))
            self.selection=original.translated(dx,dy)
            if self.drag_mode[2] is not None:
                self.imported_rect=self.drag_mode[2].translated(dx,dy)
                self.ops=clone_ops(self.drag_mode[3])
                for op in self.ops:
                    ox,oy=op.get('offset',(0,0))
                    op['offset']=(ox+dx,oy+dy)
                self.base.fill(QColor('#e8ece5'))
                painter=QPainter(self.base)
                painter.drawImage(self.imported_rect,self.imported_original)
                painter.end()
            self.update()
        elif self.selection.isEmpty():
            self.hover = next((r for r in self.windows if r.contains(point.toPoint())), self.rect())
            self.update()
        else:
            self.update_canvas_cursor(point)

    @staticmethod
    def resize_cursor(index):
        return (Qt.SizeFDiagCursor,Qt.SizeVerCursor,Qt.SizeBDiagCursor,Qt.SizeHorCursor,
                Qt.SizeFDiagCursor,Qt.SizeVerCursor,Qt.SizeBDiagCursor,Qt.SizeHorCursor)[index]

    def update_canvas_cursor(self,point):
        if self.tool_name=='select' and not self.selection.isEmpty():
            for index,handle in enumerate(self.handles()):
                if (point-handle).manhattanLength()<12:
                    self.setCursor(self.resize_cursor(index))
                    return
        movable=any(hit_op(op,point) for op in self.ops)
        self.setCursor(Qt.SizeAllCursor if movable or (self.tool_name=='select' and self.selection.contains(point)) else Qt.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.drag_mode == 'crop':
            if self.selection.width() < 5 or self.selection.height() < 5:
                self.selection = QRectF(self.hover if not self.hover.isEmpty() else self.rect())
                if self.output_size:
                    self.set_size_preset(self.preset_name,self.output_size)
        elif self.drag_mode == 'draw' and self.pending:
            if (QPointF(*self.pending['a'])-QPointF(*self.pending['b'])).manhattanLength() >= 3:
                self.remember()
                self.ops.append(self.pending)
            self.pending = None
        elif isinstance(self.drag_mode, tuple) and self.drag_mode[0] == 'move':
            if (event.position()-self.start).manhattanLength() > 1:
                self.undo_states.append(self.drag_before)
                self.redo_states.clear()
        self.drag_mode = None
        self.update_canvas_cursor(event.position())
        self.update_toolbar()
        self.update()

    def mouseDoubleClickEvent(self, event):
        for index in range(len(self.ops)-1,-1,-1):
            if self.ops[index]['tool']=='text' and hit_op(self.ops[index],event.position()):
                self.begin_text(event.position(),index)
                self.drag_mode=None
                return
        if self.tool_name == 'select' and self.selection.contains(event.position()):
            self.finish('copy')

    def export_image(self,use_preset=True):
        self.commit_text()
        r = self.selection
        if r.isEmpty():
            return QImage()
        # Imported images retain original resolution even when fitted on the desktop.
        sx, sy = self.sx, self.sy
        if hasattr(self, 'imported_original'):
            sx = self.imported_original.width()/self.imported_rect.width()
            sy = self.imported_original.height()/self.imported_rect.height()
        if use_preset and self.output_size:
            sx,sy=self.output_size[0]/r.width(),self.output_size[1]/r.height()
        image = QImage(max(1,round(r.width()*sx)), max(1,round(r.height()*sy)), QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.scale(sx,sy)
        p.translate(-r.x(),-r.y())
        if hasattr(self, 'imported_original'):
            p.drawImage(self.imported_rect,self.imported_original)
        else:
            p.drawImage(QRectF(self.rect()),self.base)
        for op in self.ops:
            draw_op(p,op,self.base,self.sx,self.sy)
        p.end()
        return image

    def finish(self, action):
        if self.selection.width() < 2 or self.selection.height() < 2:
            return
        image = self.export_image()
        if action == 'save':
            path, _ = QFileDialog.getSaveFileName(self, '保存截图', '截图.png', 'PNG 图片 (*.png);;JPEG 图片 (*.jpg)')
            if not path:
                return
            if not image.save(path):
                QMessageBox.warning(self, '保存失败', '无法写入所选文件。')
                return
        self.finished.emit(image, action)


class PinWindow(QWidget):
    def __init__(self, image):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.image, self.anchor = image, None
        self.setWindowTitle('轻匣 · 钉图')
        size = image.size().scaled(QSize(900, 700), Qt.KeepAspectRatio)
        self.resize(size)
        self.setToolTip('拖动移动 · 滚轮缩放 · 双击 / Esc 关闭')
        QShortcut(QKeySequence('Escape'),self,self.close)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(self.rect(),self.image)
        p.setPen(QPen(QColor('#b9c4bb'),1))
        p.drawRect(self.rect().adjusted(0,0,-1,-1))

    def mousePressEvent(self,event):
        self.anchor=event.globalPosition().toPoint()-self.pos()

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton and self.anchor is not None:
            self.move(event.globalPosition().toPoint()-self.anchor)

    def mouseDoubleClickEvent(self,event):
        self.close()

    def wheelEvent(self,event):
        factor=1.1 if event.angleDelta().y()>0 else 1/1.1
        size=self.size()*factor
        if 80 <= size.width() <= 2400 and 50 <= size.height() <= 1600:
            self.resize(size)
