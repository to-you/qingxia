import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QUrl, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPixmap, QPixmapCache, QImage, QAction, QKeySequence, QShortcut, QWheelEvent
from PySide6.QtWidgets import (QApplication, QFrame, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout,
    QScrollArea, QWidget, QMenu, QInputDialog, QMessageBox, QFileDialog, QToolButton)

from ui import Glass, icon, tool, brand_icon
import native

KINDS = {'text': ('文本', '#5e8275'), 'image': ('图片', '#5b8eaf'), 'link': ('链接', '#7f80ad'),
         'color': ('颜色', '#9d8b61'), 'file': ('文件', '#b67e62')}


class ClipCard(QFrame):
    chosen = Signal(dict)
    multi_chosen = Signal(dict)
    menu_requested = Signal(dict, object)

    def __init__(self, item, number, parent=None):
        super().__init__(parent)
        self.item = item
        self.selected = False
        self.setFixedSize(230, 230)
        self.setObjectName('card')
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('QFrame#card {background: #fcfdfc; border: 1px solid #e0e6e0; border-radius: 16px;} QLabel {background: transparent; border: 0;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        kind = item['kind']
        label, color = KINDS[kind]
        badge = QLabel(label, self)
        badge.setStyleSheet(f'background: #edf3ef; color: {color}; border-radius: 6px; padding: 3px 8px; font-weight: 600; font-size: 11px;')
        heading=QHBoxLayout()
        heading.addWidget(badge)
        heading.addStretch()
        index = QLabel(str(number) + (' · 收藏' if item['starred'] else ''))
        self.index_label = index
        index.setStyleSheet('font-size: 10px; font-weight: 600; color: #6b716c;')
        heading.addWidget(index)
        layout.addLayout(heading)
        if kind == 'image':
            preview = QLabel()
            preview.setAlignment(Qt.AlignCenter)
            cache_key = 'clip-preview:' + item['digest']
            pixmap = QPixmapCache.find(cache_key)
            if pixmap is None:
                pixmap = QPixmap.fromImage(QImage.fromData(item['image']))
                pixmap = pixmap.scaled(198, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                QPixmapCache.insert(cache_key, pixmap)
            preview.setPixmap(pixmap)
            layout.addWidget(preview, 1)
        elif kind == 'file':
            files = [Path(QUrl(u).toLocalFile()) for u in json.loads(item['text'])]
            image = QLabel()
            image.setPixmap(icon('ZIP_FOLDER' if files[0].suffix.lower() in ('.zip', '.7z', '.rar') else 'DOCUMENT', '#d6aa3d').pixmap(QSize(38, 38)))
            layout.addWidget(image)
            layout.addStretch()
            title = QLabel(files[0].name + (f' 等 {len(files)} 个文件' if len(files) > 1 else ''))
            title.setStyleSheet('font-weight: 600; font-size: 14px;')
            title.setWordWrap(True)
            title.setMaximumHeight(38)
            layout.addWidget(title)
            location = QLabel(str(files[0].parent))
            location.setStyleSheet('font-size: 11px; color: #91978f; background: #f2f4f1; border-radius: 5px; padding: 3px;')
            location.setMaximumWidth(198)
            layout.addWidget(location)
        elif kind == 'color':
            swatch = QLabel()
            swatch.setFixedHeight(89)
            swatch.setStyleSheet(f'background: {item["text"].strip()}; border-radius: 11px;')
            layout.addSpacing(7)
            layout.addWidget(swatch)
            text = QLabel(item['text'].strip().upper())
            text.setAlignment(Qt.AlignCenter)
            text.setStyleSheet('font-weight: 600;')
            layout.addWidget(text)
            layout.addStretch()
        elif kind == 'link':
            symbol = QLabel()
            symbol.setAlignment(Qt.AlignCenter)
            symbol.setPixmap(icon('GLOBE', '#a499eb').pixmap(42,42))
            layout.addWidget(symbol,1)
            title=QLabel((QUrl(item['text'].strip()).host() or item['text'])[:50])
            title.setStyleSheet('font-size: 14px; font-weight: 600;')
            layout.addWidget(title)
            address=QLabel(item['text'][:55])
            address.setStyleSheet('color: #959d94; font-size: 11px;')
            layout.addWidget(address)
        else:
            preview = QLabel(item['text'][:350])
            preview.setWordWrap(True)
            preview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            preview.setStyleSheet('font-size: 14px; font-weight: 500; color: #414741;')
            preview.setMaximumHeight(133)
            layout.addWidget(preview, 1)
        age = max(0, int(time.time() - item['created']))
        when = '刚刚' if age < 60 else f'{age // 60} 分钟前' if age < 3600 else time.strftime('%m-%d %H:%M', time.localtime(item['created']))
        detail = item['text'] if kind == 'image' else (f'{len(item["text"])} 个字符' if kind != 'file' else '')
        source = QLabel(f'{item["source"]} · {when}' + (f' · {detail}' if detail else ''))
        source.setStyleSheet('color: #858b84; font-size: 10px;')
        source.setMaximumWidth(198)
        layout.addWidget(source)
        self.setToolTip('双击粘贴回原窗口 · 右键管理\n' + item['text'][:220])

    def set_selected(self, selected):
        if self.selected == selected:
            return
        self.selected = selected
        self.setStyleSheet(f'QFrame#card {{background: {"#eef7f3" if selected else "#fcfdfc"}; border: 1px solid {"#4a9b88" if selected else "#e0e6e0"}; border-radius: 16px;}} QLabel {{background: transparent; border: 0;}}')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.item['kind']=='image' and event.modifiers() & Qt.ControlModifier:
                self.multi_chosen.emit(self.item)
            else:
                self.chosen.emit(self.item)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not event.modifiers() & Qt.ControlModifier:
            self.window().paste_requested.emit(self.item)

    def contextMenuEvent(self, event):
        self.menu_requested.emit(self.item, event.globalPos())


class HorizontalScroll(QScrollArea):
    def wheelEvent(self, event: QWheelEvent):
        bar = self.horizontalScrollBar()
        delta = event.angleDelta().x() or event.angleDelta().y()
        bar.setValue(bar.value() - delta)
        event.accept()


class ClipboardPanel(Glass):
    paste_requested = Signal(dict)
    copy_requested = Signal(dict)
    annotate_requested = Signal(dict)
    capture_requested = Signal()
    open_requested = Signal()
    settings_requested = Signal()
    collage_requested = Signal(list)
    visibility_changed=Signal(bool)

    def __init__(self, history):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('轻匣 · 剪贴板')
        self.history = history
        self.category, self.tag = 'all', ''
        self.clipboard_shortcut='Ctrl+Alt+V'
        self.capture_shortcut='Ctrl+Alt+S'
        self.image_shortcut='Ctrl+Alt+E'
        self.dismiss_on_outside=True
        self.cards, self.rows, self.selected = [], [], 0
        self.card_cache = {}
        self.multi_ids = []
        self.motion=''
        self.shown_pos=QPoint()
        self.hidden_pos=QPoint()
        self.slide=QPropertyAnimation(self,b'pos',self)
        self.slide.finished.connect(self.slide_finished)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 24)
        root.setSpacing(18)
        header = QHBoxLayout()
        header.setSpacing(7)
        brand = QLabel()
        brand.setPixmap(brand_icon().pixmap(27, 27))
        header.addWidget(brand)
        brand_name=QLabel('轻匣')
        brand_name.setStyleSheet('color: #2f7564; font-size: 14px; font-weight: 600;')
        header.addWidget(brand_name)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索')
        self.search.setFixedWidth(220)
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon('SEARCH', '#7e8878'), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self.refresh)
        header.addWidget(self.search)
        self.filters = []
        for key, title in [('all', '全部')] + [(k, v[0]) for k, v in KINDS.items()] + [('starred', '收藏')]:
            button = QToolButton()
            button.setText(title)
            button.setCheckable(True)
            if key in KINDS:
                button.setIcon(icon('LABEL', KINDS[key][1]))
                button.setIconSize(QSize(10, 10))
                button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.clicked.connect(lambda checked=False, k=key: self.filter(k))
            header.addWidget(button)
            self.filters.append((key, button))
        self.tag_button = tool('TAG', '按标签筛选', self.show_tags)
        header.addWidget(self.tag_button)
        header.addStretch()
        self.collage_button=tool('LAYOUT','多图拼接 · Ctrl + 单击可多选图片',self.request_collage)
        self.collage_button.setText('拼图')
        self.collage_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.collage_button.setFixedWidth(70)
        header.addWidget(self.collage_button)
        self.capture_button=tool('CAMERA', '截图  Ctrl+Alt+S', self.capture_requested.emit)
        self.image_button=tool('EDIT', '打开图片标注  Ctrl+Alt+E', self.open_requested.emit)
        header.addWidget(self.capture_button)
        header.addWidget(self.image_button)
        self.settings_button = tool('SETTING','设置',self.settings_requested.emit)
        header.addWidget(self.settings_button)
        header.addWidget(tool('CLOSE', '收起  Esc', self.dismiss))
        root.addLayout(header)
        self.scroll = HorizontalScroll()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setStyleSheet('background: transparent;')
        self.card_layout = QHBoxLayout(self.content)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(20)
        self.card_layout.setAlignment(Qt.AlignLeft)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll)
        self.hint = QLabel(self)
        self.hint.setStyleSheet('color: #717c6b; font-size: 10px; padding-left: 3px;')
        QShortcut(QKeySequence('Escape'), self, self.dismiss)
        QShortcut(QKeySequence('Ctrl+F'), self, self.search.setFocus)
        QShortcut(QKeySequence('Return'), self, self.paste_current)
        QShortcut(QKeySequence('Ctrl+C'), self, self.copy_current)
        QShortcut(QKeySequence('Left'), self, lambda: self.select(self.selected - 1))
        QShortcut(QKeySequence('Right'), self, lambda: self.select(self.selected + 1))
        for i in range(1, 10):
            QShortcut(QKeySequence(f'Alt+{i}'), self, lambda n=i: self.paste_number(n))
        self.resize(1470, 324)
        self.refresh()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.hint.setGeometry(23,self.height()-18,self.width()-46,14)

    def open_at(self, screen):
        geo = screen.availableGeometry()
        start=self.pos() if self.isVisible() else QPoint(geo.x()+12,screen.geometry().bottom()+1)
        self.slide.stop()
        self.setGeometry(geo.x() + 12, geo.bottom() - 335, geo.width() - 24, 324)
        self.shown_pos=self.pos()
        self.hidden_pos=QPoint(self.x(),screen.geometry().bottom()+1)
        self.move(start)
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        self.motion='opening'
        self.slide.setDuration(420)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.setStartValue(start)
        self.slide.setEndValue(self.shown_pos)
        self.slide.start()

    def dismiss(self):
        if not self.isVisible() or self.motion=='closing':
            return
        self.slide.stop()
        self.motion='closing'
        self.slide.setDuration(200)
        self.slide.setEasingCurve(QEasingCurve.InCubic)
        self.slide.setStartValue(self.pos())
        self.slide.setEndValue(self.hidden_pos)
        self.slide.start()

    def slide_finished(self):
        if self.motion=='closing':
            self.hide()
        self.motion=''

    def hideEvent(self,event):
        self.slide.stop()
        self.motion=''
        self.visibility_changed.emit(False)
        super().hideEvent(event)

    def showEvent(self,event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def outside_click(self,pos):
        if not self.dismiss_on_outside:
            return
        inside=native.point_in_window(int(self.winId()),*pos) if isinstance(pos,tuple) else self.frameGeometry().contains(pos)
        if not self.isVisible() or inside:
            return
        if QApplication.activePopupWidget() or QApplication.activeModalWidget():
            return
        self.dismiss()

    def set_shortcuts(self,clipboard,capture,image):
        self.clipboard_shortcut,self.capture_shortcut,self.image_shortcut=clipboard,capture,image
        self.capture_button.setToolTip('截图  '+capture)
        self.image_button.setToolTip('打开图片标注  '+image)

    def filter(self, category, tag=''):
        if (self.category, self.tag) == (category, tag):
            return
        self.category, self.tag = category, tag
        self.multi_ids = []
        self.refresh()

    def refresh(self, *_):
        if not hasattr(self, 'card_layout'):
            return
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            if item.widget():
                if isinstance(item.widget(), ClipCard):
                    item.widget().hide()
                    item.widget().set_selected(False)
                else:
                    item.widget().deleteLater()
        self.rows = self.history.items(self.search.text(), self.category, self.tag)
        self.cards = []
        for number, row in enumerate(self.rows, 1):
            card = self.card_cache.get(row['id'])
            if card is None or card.item != row:
                if card is not None:
                    card.deleteLater()
                card = ClipCard(row, number, self.content)
                card.chosen.connect(lambda item: self.select(next(i for i, row in enumerate(self.rows) if row['id'] == item['id'])))
                card.multi_chosen.connect(self.toggle_image)
                card.menu_requested.connect(self.context_menu)
                self.card_cache[row['id']] = card
            card.index_label.setText(str(number) + (' · 收藏' if row['starred'] else ''))
            self.card_layout.addWidget(card)
            card.show()
            self.cards.append(card)
        visible_ids = {row['id'] for row in self.rows}
        for item_id in list(self.card_cache):
            if len(self.card_cache) <= max(256, len(self.rows)):
                break
            if item_id not in visible_ids:
                self.card_cache.pop(item_id).deleteLater()
        if not self.rows:
            empty = QLabel('没有匹配的记录' if self.search.text() or self.category != 'all' or self.tag else '复制文字、图片或文件后，会自动出现在这里。')
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet('color: #7d8877; font-size: 15px; padding: 50px;')
            self.card_layout.addWidget(empty)
        for key, button in self.filters:
            button.setChecked(key == self.category and not self.tag)
        self.hint.setText(f'{len(self.rows)} 条记录' + (f' · 标签：{self.tag}' if self.tag else '') + '    双击 / Enter 粘贴    ·    Alt+1–9 快速粘贴    ·    右键管理    ·    Esc 收起')
        self.multi_ids=[item_id for item_id in self.multi_ids if any(row['id']==item_id and row['kind']=='image' for row in self.rows)]
        self.select(0,keep_multi=True)

    def select(self, index, keep_multi=False):
        if not keep_multi:
            self.multi_ids=[]
        self.selected = max(0, min(index, len(self.cards) - 1))
        for i, card in enumerate(self.cards):
            card.set_selected(card.item['id'] in self.multi_ids if self.multi_ids else i == self.selected)
        if self.cards:
            self.scroll.ensureWidgetVisible(self.cards[self.selected], 15, 0)
        self.collage_button.setText(f'拼图 {len(self.multi_ids)}' if self.multi_ids else '拼图')

    def toggle_image(self,item):
        if not self.multi_ids and self.rows:
            current=self.rows[self.selected]
            if current['kind']=='image' and current['id']!=item['id']:
                self.multi_ids.append(current['id'])
        if item['id'] in self.multi_ids:
            self.multi_ids.remove(item['id'])
        else:
            self.multi_ids.append(item['id'])
        self.select(next(i for i,row in enumerate(self.rows) if row['id']==item['id']),keep_multi=True)

    def request_collage(self,item=None):
        if isinstance(item,dict) and item['id'] not in self.multi_ids:
            rows=[item]
        elif self.multi_ids:
            by_id={row['id']:row for row in self.rows}
            rows=[by_id[item_id] for item_id in self.multi_ids if item_id in by_id]
        else:
            rows=[self.rows[self.selected]] if self.rows and self.rows[self.selected]['kind']=='image' else []
        self.collage_requested.emit(rows)

    def paste_current(self):
        if self.rows:
            self.paste_requested.emit(self.rows[self.selected])

    def copy_current(self):
        if self.rows:
            self.copy_requested.emit(self.rows[self.selected])

    def paste_number(self, number):
        if len(self.rows) >= number:
            self.paste_requested.emit(self.rows[number - 1])

    def context_menu(self, item, pos):
        menu = QMenu(self)
        menu.addAction(icon('PASTE'), '粘贴到原窗口', lambda: self.paste_requested.emit(item))
        menu.addAction(icon('COPY'), '复制', lambda: self.copy_requested.emit(item))
        menu.addAction(icon('HEART'), '取消收藏' if item['starred'] else '收藏', lambda: self.star(item))
        menu.addAction(icon('TAG'), '设置标签…', lambda: self.edit_tag(item))
        if item['kind'] == 'image':
            menu.addAction(icon('LAYOUT'), '多图拼接…', lambda: self.request_collage(item))
            menu.addAction(icon('EDIT'), '标注图片', lambda: self.annotate_requested.emit(item))
            menu.addAction(icon('SAVE'), '保存图片…', lambda: self.save_image(item))
        menu.addSeparator()
        menu.addAction(icon('DELETE'), '删除记录', lambda: self.delete(item))
        menu.exec(pos)

    def star(self, item):
        self.history.update(item['id'], starred=not item['starred'])
        self.refresh()

    def edit_tag(self, item):
        text, ok = QInputDialog.getText(self, '标签', '输入标签名称，留空可移除：', text=item['tag'])
        if ok:
            self.history.update(item['id'], tag=text.strip())
            self.refresh()

    def show_tags(self):
        menu = QMenu(self)
        menu.addAction('全部标签', lambda: self.filter('all'))
        tags = sorted({item['tag'] for item in self.history.items() if item['tag']})
        for tag in tags:
            menu.addAction(tag, lambda t=tag: self.filter('all', t))
        if not tags:
            menu.addAction('右键卡片 → 设置标签').setEnabled(False)
        menu.exec(self.tag_button.mapToGlobal(self.tag_button.rect().bottomLeft()))

    def delete(self, item):
        self.history.delete(item['id'])
        self.refresh()

    def save_image(self, item):
        path, _ = QFileDialog.getSaveFileName(self, '保存图片', '剪贴板.png', 'PNG 图片 (*.png)')
        if path and not QImage.fromData(item['image']).save(path):
            QMessageBox.warning(self, '保存失败', '无法写入所选文件。')
