from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QIcon
from PySide6.QtWidgets import QWidget, QToolButton
from qfluentwidgets import FluentIcon as FI, Theme

import native

STYLE = '''
QWidget {font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 13px; color: #303632;}
QToolTip {background: #fff; color: #303632; border: 1px solid #d4dbd5; padding: 6px;}
QToolButton {border: 0; border-radius: 12px; padding: 7px; background: transparent;}
QToolButton:hover {background: rgba(120,140,116,35);}
QToolButton:checked {background: rgba(120,140,116,55);}
QToolButton:disabled {color: #b8beb8;}
QLineEdit {background: rgba(110,130,110,20); border: 1px solid rgba(70,90,70,28); border-radius: 16px; padding: 7px 13px; selection-background-color: #91b8ff;}
QLineEdit:focus {border-color: #85a5ed;}
QScrollArea {background: transparent; border: 0;}
QScrollBar:horizontal {height: 5px; background: transparent; margin: 0 10px;}
QScrollBar::handle:horizontal {background: rgba(80,100,80,55); border-radius: 2px; min-width: 30px;}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {width: 0;}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {background: transparent;}
QMenu {background: #f9fbf7; border: 1px solid #d8ded6; border-radius: 9px; padding: 5px;}
QMenu::item {padding: 8px 24px; border-radius: 5px;}
QMenu::item:selected {background: #e2ebdf;}
QPushButton {background: #edf2e9; border: 1px solid #d8dfd4; border-radius: 8px; padding: 7px 16px;}
QPushButton:hover {background: #dfe9da;}
QDialog {background: #f6f8f3;}
'''


def brand_icon():
    return QIcon(str(Path(__file__).parent/'assets'/'qingxia.svg'))


def icon(name, color='#343c35'):
    return getattr(FI, name).icon(theme=Theme.LIGHT, color=QColor(color))


def tool(name, tip, callback, parent=None, checkable=False):
    button = QToolButton(parent)
    button.setIcon(icon(name))
    button.setIconSize(QSize(19, 19))
    button.setFixedSize(36, 36)
    button.setToolTip(tip)
    button.setCheckable(checkable)
    button.clicked.connect(callback)
    return button


class Glass(QWidget):
    def __init__(self, parent=None, flags=Qt.Widget):
        super().__init__(parent, flags)
        self.radius = 19
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)

    def showEvent(self, event):
        super().showEvent(event)
        if self.isWindow():
            native.glass(self)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1))
        p.setBrush(QColor(240, 245, 231, 90 if self.isWindow() else 218))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), self.radius, self.radius)
