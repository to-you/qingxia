"""Procedural test content owned by this project; no downloaded images."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QLinearGradient, QFont

from ui import brand_icon


def make_scene():
    image=QImage(2940,1912,QImage.Format_ARGB32_Premultiplied)
    painter=QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(2,2)
    gradient=QLinearGradient(0,0,1470,956)
    gradient.setColorAt(0,QColor('#edf5f1'))
    gradient.setColorAt(1,QColor('#e5e9e2'))
    painter.fillRect(QRectF(0,0,1470,956),gradient)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor('#d5e7df'))
    painter.drawEllipse(QRectF(980,-180,660,660))
    painter.setBrush(QColor('#e7ddc5'))
    painter.drawEllipse(QRectF(-160,660,540,540))
    painter.drawPixmap(64,64,brand_icon().pixmap(58,58))
    painter.setPen(QColor('#2f6556'))
    painter.setFont(QFont('Microsoft YaHei UI',25,QFont.DemiBold))
    painter.drawText(140,96,'轻匣工作台')
    painter.setFont(QFont('Microsoft YaHei UI',12))
    painter.drawText(140,125,'复制、截图、标注和拼图，在本机完成。')
    cards=[(64,190,420,345,'随手收集','让复制的内容有处可寻。'),
           (510,190,420,345,'清晰表达','用标注说明重点，用拼图讲清过程。'),
           (956,190,450,345,'本地整理','自己的内容，留在自己的电脑。')]
    for x,y,width,height,title,subtitle in cards:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#fcfdf9'))
        painter.drawRoundedRect(QRectF(x,y,width,height),20,20)
        painter.setPen(QColor('#365c4c'))
        painter.setFont(QFont('Microsoft YaHei UI',18,QFont.DemiBold))
        painter.drawText(x+30,y+52,title)
        painter.setPen(QColor('#7a8d7f'))
        painter.setFont(QFont('Microsoft YaHei UI',11))
        painter.drawText(x+30,y+85,subtitle)
        for row in range(3):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(('#dae8de','#e4e8d9','#e5ded0')[row]))
            painter.drawRoundedRect(QRectF(x+30,y+118+row*62,width-60,44),10,10)
    painter.setPen(QColor('#688576'))
    painter.setFont(QFont('Microsoft YaHei UI',12))
    painter.drawText(64,594,'轻入口  /  本地处理  /  实时预览')
    painter.end()
    return image
