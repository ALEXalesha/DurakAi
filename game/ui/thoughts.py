"""«Мысли ИИ»: где может лежать каждая карта (сетка 4 x 9 на каждого соперника и колоду)
и оценка каждого хода.

Сетка строится только из наблюдения того игрока, за которого думают: в игре против ИИ -
человека (иначе по нулям в сетке ИИ было бы видно его руку), в показе - того ИИ, чей ход.
"""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from aikit import theme as aitheme
from game.core import cards as C
from game.ui import cardpaint as cp


class ProbGrid(QWidget):
    CELL = 26
    TITLE = 18
    GAP = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.lang = "ru"
        self.blocks = []          # [(подпись, [36 вероятностей])]
        self.trump = 3

    def set_data(self, blocks, trump):
        self.blocks = blocks
        self.trump = trump
        self.updateGeometry()
        self.update()

    def set_theme(self, name, lang):
        self.theme = name
        self.lang = lang
        self.update()

    def block_height(self):
        return self.TITLE + 4 * self.CELL + self.GAP

    def sizeHint(self):
        return QSize(self.CELL * 10, max(1, len(self.blocks)) * self.block_height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def hasHeightForWidth(self):
        return False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = aitheme.palette(self.theme)
        cell = min(self.CELL, (self.width() - 4) / 10)
        f = QFont("Segoe UI")
        f.setPixelSize(12)
        p.setFont(f)
        ranks = C.RANKS_RU if self.lang == "ru" else C.RANKS
        y = 0.0
        for title, probs in self.blocks:
            p.setPen(QColor(pal["muted"]))
            p.drawText(QRectF(0, y, self.width(), self.TITLE), Qt.AlignmentFlag.AlignLeft, title)
            y += self.TITLE
            for row, suit in enumerate((0, 1, 2, 3)):
                cp.draw_suit(p, suit, cell * 0.5, y + row * cell + cell / 2, cell * 0.55)
                for r in range(9):
                    c = C.card(suit, r)
                    v = float(probs[c])
                    rect = QRectF(cell * (r + 1), y + row * cell, cell - 2, cell - 2)
                    base = QColor(pal["surface2"])
                    hot = QColor(pal["accent"] if suit != self.trump else pal["warn"])
                    mix = QColor(round(base.red() + (hot.red() - base.red()) * v),
                                 round(base.green() + (hot.green() - base.green()) * v),
                                 round(base.blue() + (hot.blue() - base.blue()) * v))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(mix)
                    p.drawRoundedRect(rect, 3, 3)
                    p.setPen(QColor(pal["accent_text"] if v > 0.55 else pal["muted"]))
                    f.setPixelSize(10)
                    p.setFont(f)
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ranks[r])
            y += 4 * cell + self.GAP
        p.end()


def move_text(t, m, lang="ru"):
    from game.core.durak import ATTACK, DEFEND, TAKE, TRANSFER
    kind, c, _ = m
    if kind == TAKE:
        return t("move_take")
    if c < 0:
        return t("move_pass")
    name = (C.RANKS_RU if lang == "ru" else C.RANKS)[C.rank(c)] + C.SUITS[C.suit(c)]
    key = {ATTACK: "move_attack", DEFEND: "move_defend", TRANSFER: "move_transfer"}[kind]
    return t(key, card=name)
