from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QStackedWidget,QWidget,QCheckBox,QFormLayout,QKeySequenceEdit,QPushButton,QFrame,QMessageBox)

from ui import STYLE,icon

DEFAULTS={'clipboard_shortcut':'Ctrl+Alt+V','capture_shortcut':'Ctrl+Alt+S','image_shortcut':'Ctrl+Alt+E',
    'autostart':False,'show_on_launch':True,'record_clipboard':True,'dismiss_on_outside':True}


class SettingsPanel(QDialog):
    def __init__(self,controller):
        super().__init__()
        self.controller=controller
        self.setWindowTitle('轻匣 · 设置')
        self.setWindowIcon(icon('SETTING','#8471de'))
        self.resize(700,480)
        self.setMinimumSize(660,450)
        self.setStyleSheet(STYLE+'''
            QDialog {background: #f6f8f3;}
            QListWidget {background: transparent; border: 0; outline: 0; padding: 0;}
            QListWidget::item {padding: 12px 10px; margin-bottom: 6px; border-radius: 9px;}
            QListWidget::item:selected {background: #e0e9d9; color: #374d31;}
            QFrame#settingsCard {background: #fff; border: 1px solid #e3e8de; border-radius: 12px;}
            QCheckBox {spacing: 10px; padding: 7px 0;}
            QCheckBox::indicator {width: 17px; height: 17px;}
            QKeySequenceEdit {background: #f6f8f3; border: 1px solid #d8dfd4; border-radius: 8px; padding: 3px;}
            QPushButton#apply {background: #5c7750; color: white; border: 0; padding: 8px 24px;}
        ''')
        root=QVBoxLayout(self)
        root.setContentsMargins(24,20,24,20)
        root.setSpacing(18)
        title=QLabel('设置')
        title.setStyleSheet('font-size: 23px; font-weight: 600;')
        root.addWidget(title)
        middle=QHBoxLayout()
        middle.setSpacing(22)
        self.nav=QListWidget()
        self.nav.setFixedWidth(140)
        for name,ico in [('常规','SETTING'),('全局快捷键','COMMAND_PROMPT'),('剪贴板','PASTE')]:
            self.nav.addItem(QListWidgetItem(icon(ico),name))
        self.pages=QStackedWidget()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        middle.addWidget(self.nav)
        middle.addWidget(self.pages,1)
        root.addLayout(middle,1)
        self.checks={}
        self.edits={}
        general=self.page('常规','调整启动方式与日常使用习惯。')
        self.check(general,'autostart','开机自启动')
        hint=QLabel('仅当前 Windows 用户登录后启动，自动驻留托盘。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #87917e; font-size: 11px; padding-left: 27px;')
        general.addWidget(hint)
        self.check(general,'show_on_launch','手动启动时显示剪贴板')
        general.addStretch()
        data=QPushButton('打开本地数据目录')
        data.clicked.connect(controller.open_data)
        general.addWidget(data,alignment=Qt.AlignLeft)
        keys=self.page('全局快捷键','在其他应用中也能唤起。点击输入框后按下组合键。')
        form=QFormLayout()
        form.setVerticalSpacing(18)
        for key,label in [('clipboard_shortcut','剪贴板显示 / 隐藏'),('capture_shortcut','截图与标注'),('image_shortcut','打开图片标注')]:
            edit=QKeySequenceEdit()
            edit.setMaximumSequenceLength(1)
            edit.setClearButtonEnabled(True)
            edit.setMinimumWidth(220)
            self.edits[key]=edit
            form.addRow(label,edit)
        keys.addLayout(form)
        keys.addStretch()
        note=QLabel('快捷键不能重复；被其他程序占用时，会保留原设置。')
        note.setWordWrap(True)
        note.setStyleSheet('color: #87917e; font-size: 11px;')
        keys.addWidget(note)
        clips=self.page('剪贴板','记录与面板行为。历史内容只保存在本机。')
        self.check(clips,'record_clipboard','自动记录复制的内容')
        self.check(clips,'dismiss_on_outside','点击面板外部时收起')
        info=QLabel('支持文字、图片与文件记录。\n未收藏记录最多保留 200 条；文件记录引用原路径。')
        info.setStyleSheet('color: #87917e; font-size: 11px;')
        info.setWordWrap(True)
        clips.addWidget(info)
        clips.addStretch()
        self.clear_button=QPushButton('清空未收藏记录…')
        self.clear_button.clicked.connect(self.clear_history)
        clips.addWidget(self.clear_button,alignment=Qt.AlignLeft)
        bottom=QHBoxLayout()
        reset=QPushButton('恢复默认')
        reset.clicked.connect(lambda: self.load(DEFAULTS))
        bottom.addWidget(reset)
        self.status=QLabel('修改后点击“应用”。')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color: #87917e; font-size: 11px;')
        bottom.addWidget(self.status,1)
        self.apply_button=QPushButton('应用')
        self.apply_button.setObjectName('apply')
        self.apply_button.clicked.connect(self.apply)
        bottom.addWidget(self.apply_button)
        close=QPushButton('关闭')
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        root.addLayout(bottom)
        self.nav.setCurrentRow(0)
        self.load(controller.preferences())

    def clear_history(self):
        if QMessageBox.question(self,'清空记录','删除全部未收藏记录？收藏的记录会保留。') == QMessageBox.Yes:
            self.controller.history.clear()
            self.controller.panel.refresh()

    def page(self,title,subtitle):
        card=QFrame()
        card.setObjectName('settingsCard')
        layout=QVBoxLayout(card)
        layout.setContentsMargins(20,20,20,20)
        layout.setSpacing(12)
        heading=QLabel(title)
        heading.setStyleSheet('font-size: 18px; font-weight: 600;')
        layout.addWidget(heading)
        description=QLabel(subtitle)
        description.setStyleSheet('color: #87917e; font-size: 12px;')
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(8)
        self.pages.addWidget(card)
        return layout

    def check(self,layout,key,text):
        checkbox=QCheckBox(text)
        self.checks[key]=checkbox
        layout.addWidget(checkbox)

    def load(self,values):
        for key,edit in self.edits.items():
            edit.setKeySequence(QKeySequence(values[key]))
        for key,checkbox in self.checks.items():
            checkbox.setChecked(bool(values[key]))
        self.status.setText('修改后点击“应用”。')

    def apply(self):
        values={key:edit.keySequence().toString(QKeySequence.PortableText) for key,edit in self.edits.items()}
        values.update({key:checkbox.isChecked() for key,checkbox in self.checks.items()})
        ok,error=self.controller.apply_preferences(values)
        self.status.setStyleSheet('font-size: 11px; color: '+('#547747;' if ok else '#ce574d;'))
        self.status.setText('设置已应用。' if ok else error)
