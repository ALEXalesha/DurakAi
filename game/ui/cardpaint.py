"""Карты, нарисованные своим кодом (QPainter): лицо, рубашка, масти контурами.

Чужие колоды не копируются: масти - фигуры из кругов и многоугольников, достоинство -
текст шрифтом окна, рубашка - сетка ромбов в цвет темы.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from game.core import cards as C

RED = "#c8323c"
BLACK = "#1c2230"

CLOTH = {
    # сукно в цвет темы: тёмная «Строгая» - глубокий сине-зелёный, светлая - светлый шалфей
    "dark": {"cloth": "#1d3b37", "cloth_edge": "#16302c", "slot": "#2a4f49",
             "back": "#3a5f99", "back_line": "#6f93c9", "face": "#f7f5ef", "edge": "#9aa3b2",
             "glow": "#ffd35a", "shade": "#0d1514"},
    "light": {"cloth": "#cfe2d5", "cloth_edge": "#b7d1c0", "slot": "#bcd6c6",
              "back": "#3a6fd8", "back_line": "#9cbcf5", "face": "#ffffff", "edge": "#8d98ab",
              "glow": "#e8a400", "shade": "#7f978a"},
}


def cloth(theme):
    return CLOTH.get(theme, CLOTH["dark"])


def suit_path(suit, cx, cy, size):
    """Контур масти с центром (cx, cy) высотой примерно size."""
    s = size
    path = QPainterPath()
    if suit == 3:          # червы: два круга и треугольник
        r = s * 0.27
        path.addEllipse(QPointF(cx - r * 0.95, cy - s * 0.12), r, r)
        path.addEllipse(QPointF(cx + r * 0.95, cy - s * 0.12), r, r)
        tri = QPainterPath()
        tri.addPolygon(QPolygonF([QPointF(cx - s * 0.5, cy - s * 0.04), QPointF(cx + s * 0.5, cy - s * 0.04),
                                  QPointF(cx, cy + s * 0.5)]))
        path = path.united(tri)
    elif suit == 2:        # бубны: ромб
        path.addPolygon(QPolygonF([QPointF(cx, cy - s * 0.52), QPointF(cx + s * 0.38, cy),
                                   QPointF(cx, cy + s * 0.52), QPointF(cx - s * 0.38, cy)]))
        path.closeSubpath()
    elif suit == 0:        # пики: перевёрнутое сердце и ножка
        r = s * 0.25
        path.addEllipse(QPointF(cx - r * 0.95, cy + s * 0.06), r, r)
        path.addEllipse(QPointF(cx + r * 0.95, cy + s * 0.06), r, r)
        tri = QPainterPath()
        tri.addPolygon(QPolygonF([QPointF(cx - s * 0.47, cy + s * 0.0), QPointF(cx + s * 0.47, cy + s * 0.0),
                                  QPointF(cx, cy - s * 0.5)]))
        stem = QPainterPath()
        stem.addPolygon(QPolygonF([QPointF(cx, cy + s * 0.08), QPointF(cx + s * 0.16, cy + s * 0.5),
                                   QPointF(cx - s * 0.16, cy + s * 0.5)]))
        path = path.united(tri).united(stem)
    else:                  # трефы: три круга и ножка
        r = s * 0.2
        path.addEllipse(QPointF(cx, cy - s * 0.25), r, r)
        path.addEllipse(QPointF(cx - s * 0.23, cy + s * 0.06), r, r)
        path.addEllipse(QPointF(cx + s * 0.23, cy + s * 0.06), r, r)
        stem = QPainterPath()
        stem.addPolygon(QPolygonF([QPointF(cx, cy - s * 0.05), QPointF(cx + s * 0.15, cy + s * 0.5),
                                   QPointF(cx - s * 0.15, cy + s * 0.5)]))
        path = path.united(stem)
    return path


def suit_color(suit):
    return RED if suit in (2, 3) else BLACK


def draw_suit(p, suit, cx, cy, size, color=None):
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color or suit_color(suit)))
    p.drawPath(suit_path(suit, cx, cy, size))
    p.restore()


def rank_text(c, lang="ru"):
    return (C.RANKS_RU if lang == "ru" else C.RANKS)[C.rank(c)]


def draw_face(p, rect, c, theme, lang="ru", glow=False, dim=False, trump=False):
    col = cloth(theme)
    w, h = rect.width(), rect.height()
    radius = w * 0.09
    p.save()
    if glow:
        p.setPen(QPen(QColor(col["glow"]), max(2.0, w * 0.05)))
    else:
        p.setPen(QPen(QColor(col["edge"]), 1.0))
    p.setBrush(QColor(col["face"]))
    p.drawRoundedRect(rect, radius, radius)
    s, color = C.suit(c), suit_color(C.suit(c))
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(max(8, int(h * 0.2)))
    p.setFont(font)
    p.setPen(QColor(color))
    corner = QRectF(rect.left() + w * 0.06, rect.top() + h * 0.03, w * 0.5, h * 0.24)
    p.drawText(corner, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, rank_text(c, lang))
    draw_suit(p, s, rect.left() + w * 0.2, rect.top() + h * 0.33, h * 0.13)
    big = h * (0.36 if C.rank(c) < 5 else 0.3)
    draw_suit(p, s, rect.center().x() + w * 0.06, rect.center().y() + h * 0.12, big)
    if C.rank(c) >= 5:        # картинки - буква достоинства в центре
        font.setPixelSize(max(8, int(h * 0.24)))
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(rect.left(), rect.top() + h * 0.18, w, h * 0.32), Qt.AlignmentFlag.AlignCenter,
                   rank_text(c, lang))
    if trump:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(col["glow"]))
        p.drawEllipse(QPointF(rect.right() - w * 0.14, rect.top() + h * 0.1), w * 0.05, w * 0.05)
    if dim:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(rect, radius, radius)
    p.restore()


def draw_back(p, rect, theme):
    col = cloth(theme)
    w = rect.width()
    radius = w * 0.09
    p.save()
    p.setPen(QPen(QColor(col["edge"]), 1.0))
    p.setBrush(QColor(col["face"]))
    p.drawRoundedRect(rect, radius, radius)
    inner = rect.adjusted(w * 0.07, w * 0.07, -w * 0.07, -w * 0.07)
    p.setBrush(QColor(col["back"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(inner, radius * 0.6, radius * 0.6)
    p.setClipRect(inner)
    p.setPen(QPen(QColor(col["back_line"]), max(1.0, w * 0.02)))
    step = max(6.0, w * 0.16)
    x = inner.left() - inner.height()
    while x < inner.right() + inner.height():
        p.drawLine(QPointF(x, inner.top()), QPointF(x + inner.height(), inner.bottom()))
        p.drawLine(QPointF(x, inner.bottom()), QPointF(x + inner.height(), inner.top()))
        x += step
    p.restore()


def draw_card(p, rect, c, face_up, theme, lang="ru", **kw):
    if face_up and c >= 0:
        draw_face(p, rect, c, theme, lang, **kw)
    else:
        draw_back(p, rect, theme)
