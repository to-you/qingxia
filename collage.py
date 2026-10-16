"""Local multi-image layouts with a scaled preview and full-resolution export."""
import math
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QRectF, QTimer
from PySide6.QtGui import QImage, QPainter, QPainterPath, QColor, QPixmap, QIcon, QPixmapCache, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QAbstractItemView, QComboBox, QSpinBox,
    QColorDialog, QFileDialog, QFrame, QButtonGroup, QToolButton, QDialog, QDialogButtonBox,
    QAbstractSpinBox, QStyledItemDelegate)

from ui import STYLE, icon


TEMPLATES = (('vertical','竖向长图'),('horizontal','横向拼接'),('grid2','双列网格'),
             ('grid3','三列网格'),('hero_left','主图在左'),('hero_top','主图在上'))
CANVASES = (('自动尺寸',None),('方图 · 1080 × 1080',(1080,1080)),
            ('竖图 · 1080 × 1440',(1080,1440)),('竖屏 · 1080 × 1920',(1080,1920)),
            ('横图 · 1920 × 1080',(1920,1080)),('公众号封面 · 900 × 383',(900,383)))


def grid_rects(count,columns,area,gap):
    columns=min(count,columns)
    rows=math.ceil(count/columns)
    width=(area.width()-(columns-1)*gap)/columns
    height=(area.height()-(rows-1)*gap)/rows
    if min(width,height)<1:
        raise ValueError('图片数量或间距过大，请减少图片、缩小间距，或选择自动尺寸。')
    return [QRectF(area.x()+(i%columns)*(width+gap),area.y()+(i//columns)*(height+gap),width,height)
            for i in range(count)]


def collage_geometry(images,template,canvas=None,gap=12,padding=16):
    if not images or any(image.isNull() for image in images):
        raise ValueError('请添加有效图片。')
    count=len(images)
    if canvas is None:
        if template=='vertical':
            width=1080
            height=round(sum((width-2*padding)*image.height()/image.width() for image in images)
                         +(count-1)*gap+2*padding)
        elif template=='horizontal':
            height=720
            width=round(sum((height-2*padding)*image.width()/image.height() for image in images)
                        +(count-1)*gap+2*padding)
        else:
            width=1080
            columns=min(count,3 if template=='grid3' else 2)
            cell=(width-2*padding-(columns-1)*gap)/columns
            rows=math.ceil(count/columns)
            height=round(rows*cell+(rows-1)*gap+2*padding) if template.startswith('grid') else 1080
    else:
        width,height=canvas
    area=QRectF(padding,padding,width-2*padding,height-2*padding)
    if min(area.width(),area.height())<1:
        raise ValueError('外边距过大，请减小外边距。')
    if count==1:
        rects=[area]
    elif template in ('vertical','horizontal') and canvas is None:
        rects=[]
        position=padding
        for image in images:
            if template=='vertical':
                extent=area.width()*image.height()/image.width()
                rects.append(QRectF(padding,position,area.width(),extent))
            else:
                extent=area.height()*image.width()/image.height()
                rects.append(QRectF(position,padding,extent,area.height()))
            position+=extent+gap
    elif template in ('hero_left','hero_top'):
        if template=='hero_left':
            extent=(area.width()-gap)*0.6
            first=QRectF(area.x(),area.y(),extent,area.height())
            rest=QRectF(first.right()+gap,area.y(),area.width()-extent-gap,area.height())
            columns=1 if count<=4 else 2
        else:
            extent=(area.height()-gap)*0.6
            first=QRectF(area.x(),area.y(),area.width(),extent)
            rest=QRectF(area.x(),first.bottom()+gap,area.width(),area.height()-extent-gap)
            columns=min(3,count-1)
        rects=[first]+grid_rects(count-1,columns,rest,gap)
    else:
        columns={'vertical':1,'horizontal':count,'grid2':2,'grid3':3}[template]
        rects=grid_rects(count,columns,area,gap)
    return QSize(width,height),rects


def render_collage(images,template='grid2',canvas=None,gap=12,padding=16,
                   background=Qt.transparent,fit='contain',radius=12,preview=False):
    size,rects=collage_geometry(images,template,canvas,gap,padding)
    if not preview and (size.width()*size.height()>50_000_000 or max(size.width(),size.height())>30000):
        raise ValueError('成图过大，请减少图片或选择固定画布尺寸。')
    scale=min(1,900/max(size.width(),size.height())) if preview else 1
    result=QImage(max(1,round(size.width()*scale)),max(1,round(size.height()*scale)),QImage.Format_ARGB32_Premultiplied)
    if result.isNull():
        raise ValueError('无法创建画布，请选择较小的尺寸。')
    result.fill(QColor(background))
    painter=QPainter(result)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(scale,scale)
    for image,cell in zip(images,rects):
        source=QRectF(image.rect())
        target=QRectF(cell)
        if fit=='cover':
            ratio=min(image.width()/cell.width(),image.height()/cell.height())
            width,height=cell.width()*ratio,cell.height()*ratio
            source=QRectF((image.width()-width)/2,(image.height()-height)/2,width,height)
        else:
            ratio=min(cell.width()/image.width(),cell.height()/image.height())
            width,height=image.width()*ratio,image.height()*ratio
            target=QRectF(cell.center().x()-width/2,cell.center().y()-height/2,width,height)
        path=QPainterPath()
        corner=min(radius,target.width()/2,target.height()/2)
        path.addRoundedRect(target,corner,corner)
        painter.save()
        painter.setClipPath(path)
        painter.drawImage(target,image,source)
        painter.restore()
    painter.end()
    return result


class CollagePreview(QWidget):
    def __init__(self):
        super().__init__()
        self.image=QImage()
        self.checker=QPixmap(16,16)
        self.checker.fill(QColor('#ffffff'))
        painter=QPainter(self.checker)
        painter.fillRect(0,0,8,8,QColor('#edf0eb'))
        painter.fillRect(8,8,8,8,QColor('#edf0eb'))
        painter.end()
        self.setMinimumSize(300,260)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor('#e8ede6'))
        if self.image.isNull():
            painter.setPen(QColor('#7a8775'))
            painter.drawText(self.rect(),Qt.AlignCenter,'添加图片，选择一个布局开始拼图')
            return
        fitted=self.image.size().scaled(self.size()-QSize(36,36),Qt.KeepAspectRatio)
        rect=QRectF((self.width()-fitted.width())/2,(self.height()-fitted.height())/2,fitted.width(),fitted.height())
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(rect.adjusted(-1,-1,1,1),QColor('#d4ddd0'))
        painter.fillRect(rect,QBrush(self.checker))
        painter.drawImage(rect,self.image)


def template_icon(template):
    images=[QImage(10,10,QImage.Format_RGB32) for _ in range(5)]
    _,rects=collage_geometry(images,template,(90,60),4,4)
    pixmap=QPixmap(90,60)
    pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap)
    painter.setPen(Qt.NoPen)
    for index,rect in enumerate(rects):
        painter.setBrush(QColor('#8da98b' if index==0 else '#d0ddcc'))
        painter.drawRoundedRect(rect,3,3)
    painter.end()
    return QIcon(pixmap)


class CollageEditor(QWidget):
    output_ready=Signal(QImage,str)

    def __init__(self,history):
        super().__init__()
        self.history=history
        self.template='grid2'
        self.background=QColor(Qt.transparent)
        self.setWindowTitle('轻匣 · 多图拼接')
        self.setWindowIcon(icon('LAYOUT','#6d8962'))
        self.resize(1120,760)
        self.setMinimumSize(940,650)
        self.setStyleSheet((STYLE+'''
            QWidget#collageEditor {background: #f6f8f3;}
            QFrame#side {background: #fff; border: 1px solid #e0e6dc; border-radius: 12px;}
            QListWidget {background: transparent; border: 0; outline: 0;}
            QListWidget::item {padding: 8px; margin: 3px; border-radius: 8px;}
            QListWidget::item:selected {background: #e3eddf; color: #354c30;}
            QToolButton#template {border: 1px solid #e2e8de; border-radius: 9px; padding: 5px;}
            QToolButton#template:checked {border: 1px solid #829d77; background: #eef4e9;}
            QPushButton#primary {background: #607c53; color: white; border: 0; padding: 9px 20px;}
            QComboBox {background: #f7f9f5; border: 1px solid #e0e7dc; border-radius: 9px;
                       padding: 8px 30px 8px 11px; min-height: 18px; color: #42533e;}
            QComboBox:hover {background: #f1f5ed; border-color: #bacab0;}
            QComboBox:focus, QComboBox:on {border-color: #8ca57e; background: #f3f7ef;}
            QComboBox::drop-down {subcontrol-origin: padding; subcontrol-position: top right;
                                 width: 30px; border: none; background: transparent;}
            QComboBox::down-arrow {image: url("__CHEVRON__"); width: 16px; height: 16px;}
            QComboBox QAbstractItemView {background: white; border: 1px solid #dce5d6;
                border-radius: 9px; padding: 5px; outline: 0; selection-background-color: #eaf2e4;
                selection-color: #3e5535;}
            QComboBox QAbstractItemView::item {min-height: 32px; padding: 0 8px; border-radius: 5px;}
            QFrame#stepper {background: #f7f9f5; border: 1px solid #e0e7dc; border-radius: 9px;}
            QSpinBox#spacingValue {background: transparent; border: 0; padding: 0; color: #42533e;}
            QSpinBox#spacingValue:focus {background: #edf3e7; border-radius: 5px;}
            QToolButton#stepperButton {background: transparent; border: 0; border-radius: 6px;
                                      padding: 0; font-size: 19px; color: #62785a;}
            QToolButton#stepperButton:hover {background: #e5eddf;}
            QToolButton#stepperButton:pressed {background: #d6e3cd;}
            QToolButton#stepperButton:disabled {color: #c3cdbd;}
        ''').replace('__CHEVRON__',(Path(__file__).parent/'assets'/'chevron-down.svg').as_posix()))
        self.setObjectName('collageEditor')
        self.render_timer=QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(50)
        self.render_timer.timeout.connect(self.update_preview)
        root=QVBoxLayout(self)
        root.setContentsMargins(22,20,22,18)
        header=QHBoxLayout()
        title=QLabel('多图拼接')
        title.setStyleSheet('font-size: 24px; font-weight: 600;')
        header.addWidget(title)
        header.addStretch()
        for text,callback in [('导入图片',self.import_files),('从剪贴板历史添加',self.add_from_history)]:
            button=QPushButton(text)
            button.clicked.connect(callback)
            header.addWidget(button)
        root.addLayout(header)
        body=QHBoxLayout()
        body.setSpacing(16)
        sources=QFrame()
        sources.setObjectName('side')
        sources.setFixedWidth(190)
        left=QVBoxLayout(sources)
        left.addWidget(QLabel('图片顺序'))
        hint=QLabel('拖动排序，第一张为主图')
        hint.setStyleSheet('color: #8a9581; font-size: 11px;')
        left.addWidget(hint)
        self.sources=QListWidget()
        self.sources.setIconSize(QSize(70,60))
        self.sources.setDragDropMode(QAbstractItemView.InternalMove)
        self.sources.setDefaultDropAction(Qt.MoveAction)
        self.sources.model().rowsMoved.connect(self.schedule_preview)
        self.sources.model().rowsInserted.connect(self.schedule_preview)
        self.sources.model().rowsRemoved.connect(self.schedule_preview)
        left.addWidget(self.sources,1)
        order=QHBoxLayout()
        for label,callback in [('↑',lambda: self.move_source(-1)),('↓',lambda: self.move_source(1)),('移除',self.remove_source)]:
            button=QPushButton(label)
            button.clicked.connect(callback)
            order.addWidget(button)
        left.addLayout(order)
        body.addWidget(sources)
        self.preview=CollagePreview()
        body.addWidget(self.preview,1)
        controls=QFrame()
        controls.setObjectName('side')
        controls.setFixedWidth(242)
        right=QVBoxLayout(controls)
        right.setSpacing(8)
        right.addWidget(QLabel('布局模板'))
        templates=QGridLayout()
        self.template_group=QButtonGroup(self)
        self.template_buttons={}
        for index,(key,label) in enumerate(TEMPLATES):
            button=QToolButton()
            button.setObjectName('template')
            button.setText(label)
            button.setIcon(template_icon(key))
            button.setIconSize(QSize(86,44))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setFixedSize(102,72)
            button.setCheckable(True)
            button.setChecked(key==self.template)
            button.clicked.connect(lambda checked=False,k=key: self.set_template(k))
            self.template_group.addButton(button)
            self.template_buttons[key]=button
            templates.addWidget(button,index//2,index%2)
        right.addLayout(templates)
        right.addWidget(QLabel('输出画布'))
        self.canvas_box=QComboBox()
        for label,size in CANVASES:
            self.canvas_box.addItem(label,size)
        self.canvas_box.currentIndexChanged.connect(self.schedule_preview)
        right.addWidget(self.canvas_box)
        self.fit_box=QComboBox()
        self.fit_box.addItem('完整显示（不裁切）','contain')
        self.fit_box.addItem('填满画框（居中裁切）','cover')
        self.fit_box.currentIndexChanged.connect(self.schedule_preview)
        right.addWidget(self.fit_box)
        for combo in (self.canvas_box,self.fit_box):
            combo.setItemDelegate(QStyledItemDelegate(combo))
            combo.view().setMinimumWidth(250)
        self.spacing={}
        for key,label,value,maximum in [('gap','图片间距',12,80),('padding','外边距',16,100),('radius','图片圆角',12,48)]:
            row=QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            field=QFrame()
            field.setObjectName('stepper')
            field.setFixedSize(132,36)
            field_row=QHBoxLayout(field)
            field_row.setContentsMargins(4,4,4,4)
            field_row.setSpacing(0)
            spin=QSpinBox()
            spin.setObjectName('spacingValue')
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignCenter)
            spin.setFixedWidth(68)
            spin.setRange(0,maximum)
            spin.setValue(value)
            spin.setSuffix(' px')
            spin.valueChanged.connect(self.schedule_preview)
            self.spacing[key]=spin
            minus=QToolButton()
            minus.setObjectName('stepperButton')
            minus.setText('−')
            minus.setFixedSize(26,26)
            minus.setToolTip('减少'+label)
            minus.setAutoRepeat(True)
            minus.clicked.connect(spin.stepDown)
            plus=QToolButton()
            plus.setObjectName('stepperButton')
            plus.setText('+')
            plus.setFixedSize(26,26)
            plus.setToolTip('增加'+label)
            plus.setAutoRepeat(True)
            plus.clicked.connect(spin.stepUp)
            field_row.addWidget(minus)
            field_row.addWidget(spin)
            field_row.addWidget(plus)
            def update_steps(value,s=spin,down=minus,up=plus):
                down.setEnabled(value>s.minimum())
                up.setEnabled(value<s.maximum())
            spin.valueChanged.connect(update_steps)
            update_steps(value)
            row.addWidget(field)
            right.addLayout(row)
        self.background_button=QPushButton('背景颜色 · 透明')
        self.background_button.clicked.connect(self.choose_background)
        right.addWidget(self.background_button)
        right.addStretch()
        body.addWidget(controls)
        root.addLayout(body,1)
        footer=QHBoxLayout()
        self.status=QLabel('添加至少 2 张图片开始拼接')
        self.status.setWordWrap(True)
        footer.addWidget(self.status,1)
        self.export_buttons=[]
        for text,action in [('继续标注','edit'),('保存图片','save'),('复制成图','copy')]:
            button=QPushButton(text)
            if action=='copy':
                button.setObjectName('primary')
            button.clicked.connect(lambda checked=False,a=action: self.export(a))
            button.setEnabled(False)
            self.export_buttons.append(button)
            footer.addWidget(button)
        root.addLayout(footer)

    def images(self):
        return [self.sources.item(i).data(Qt.UserRole)['image'] for i in range(self.sources.count())]

    def add_images(self,entries):
        added=0
        for image,label in entries:
            if image.isNull():
                continue
            item=QListWidgetItem(QIcon(QPixmap.fromImage(image).scaled(70,60,Qt.KeepAspectRatio,Qt.SmoothTransformation)),
                                 f'{label[:16]}\n{image.width()} × {image.height()}')
            item.setData(Qt.UserRole,{'image':image,'label':label})
            item.setToolTip(label)
            self.sources.addItem(item)
            added+=1
        self.update_preview()
        return added

    def import_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'添加拼图图片','','图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if paths:
            added=self.add_images([(QImage(path),Path(path).name) for path in paths])
            if added<len(paths):
                self.status.setText(f'已添加 {added} 张；有 {len(paths)-added} 个文件无法读取。')

    def add_from_history(self):
        rows=self.history.items(category='image')
        if not rows:
            self.status.setText('剪贴板历史还没有图片，请先复制图片，或点击“导入图片”。')
            return
        dialog=QDialog(self)
        dialog.setWindowTitle('从剪贴板历史添加图片')
        dialog.resize(500,480)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('按 Ctrl / Shift 多选图片'))
        choices=QListWidget()
        choices.setIconSize(QSize(70,60))
        choices.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for row in rows:
            preview=QPixmapCache.find('clip-preview:'+row['digest'])
            if preview is None:
                preview=QPixmap.fromImage(QImage.fromData(row['image'])).scaled(70,60,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            item=QListWidgetItem(QIcon(preview),row['text']+' · '+row['source'])
            item.setData(Qt.UserRole,row)
            choices.addItem(item)
        layout.addWidget(choices)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('添加所选图片')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted:
            self.add_images([(QImage.fromData(item.data(Qt.UserRole)['image']),'剪贴板图片')
                             for item in choices.selectedItems()])

    def move_source(self,delta):
        row=self.sources.currentRow()
        target=row+delta
        if 0<=row<self.sources.count() and 0<=target<self.sources.count():
            item=self.sources.takeItem(row)
            self.sources.insertItem(target,item)
            self.sources.setCurrentRow(target)
            self.update_preview()

    def remove_source(self):
        row=self.sources.currentRow()
        if row>=0:
            self.sources.takeItem(row)
            self.update_preview()

    def set_template(self,key):
        self.template=key
        self.template_buttons[key].setChecked(True)
        self.update_preview()

    def choose_background(self):
        color=QColorDialog.getColor(self.background,self,'拼图背景颜色',QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self.background=color
            self.background_button.setText('背景颜色 · '+('透明' if color.alpha()==0 else color.name(QColor.HexArgb).upper()))
            self.update_preview()

    def schedule_preview(self,*_):
        self.render_timer.start()

    def options(self):
        return dict(template=self.template,canvas=self.canvas_box.currentData(),
                    background=self.background,fit=self.fit_box.currentData(),
                    **{key:spin.value() for key,spin in self.spacing.items()})

    def update_preview(self):
        self.render_timer.stop()
        images=self.images()
        valid=False
        if images:
            try:
                options=self.options()
                size,_=collage_geometry(images,self.template,options['canvas'],options['gap'],options['padding'])
                self.preview.image=render_collage(images,**options,preview=True)
                self.status.setText(f'{len(images)} 张图片 · 成图 {size.width()} × {size.height()} 像素')
                valid=len(images)>=2
                if not valid:
                    self.status.setText('已添加 1 张图片，再添加至少 1 张即可拼接。')
            except ValueError as error:
                self.preview.image=QImage()
                self.status.setText(str(error))
        else:
            self.preview.image=QImage()
            self.status.setText('添加至少 2 张图片开始拼接')
        self.preview.update()
        for button in self.export_buttons:
            button.setEnabled(valid)

    def export(self,action):
        if self.sources.count()<2:
            return
        try:
            image=render_collage(self.images(),**self.options())
        except ValueError as error:
            self.status.setText(str(error))
            return
        if action=='save':
            path,_=QFileDialog.getSaveFileName(self,'保存拼图','拼图.png','PNG 图片 (*.png);;JPEG 图片 (*.jpg)')
            if not path:
                return
            saved=image
            if Path(path).suffix.lower() in ('.jpg','.jpeg'):
                saved=QImage(image.size(),QImage.Format_RGB32)
                saved.fill(Qt.white)
                painter=QPainter(saved)
                painter.drawImage(0,0,image)
                painter.end()
            if not saved.save(path):
                self.status.setText('保存失败，请选择可写入的目录。')
                return
        if action=='edit':
            self.hide()
        self.output_ready.emit(image,action)
        self.status.setText('已复制成图，可直接粘贴。' if action=='copy' else '拼图已保存。' if action=='save' else '已打开标注。')

    def closeEvent(self,event):
        self.render_timer.stop()
        super().closeEvent(event)
