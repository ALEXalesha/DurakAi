"""Иконка программы: две карты веером на сукне, нарисованные тем же кодом, что и стол.
Её же собирает в .ico build.py."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap

from game.core import cards as C
from game.ui import cardpaint as cp


def render(size=256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.18, size * 0.18)
    p.setClipPath(clip)
    p.fillRect(QRectF(0, 0, size, size), QColor(cp.cloth("dark")["cloth"]))
    w, h = size * 0.5, size * 0.72
    for angle, card in ((-14, C.parse("A♠")), (12, C.parse("A♥"))):
        p.save()
        p.translate(size / 2, size * 0.56)
        p.rotate(angle)
        cp.draw_face(p, QRectF(-w / 2, -h / 2, w, h), card, "dark", "en")
        p.restore()
    p.end()
    return img


def app_icon():
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render(s)))
    return icon
