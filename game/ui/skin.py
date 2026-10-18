"""Вид страниц «Настройки» и «Статистика» Дурака - «карточный стол», как стартовое меню
(правило автора 17.10: настройки и статистика у каждой игры свои).

Фон страниц - зелёное сукно с золотой каймой и тёмным краем стола, на углах - сброшенные карты
(рубашки и пара открытых). Карточки - кожаные планки с золотой каймой, кнопки - карты (белые с
тёмным шрифтом), главная - золотая; переключатели - фишки; заголовок и подписи - Georgia.

Механизм общий (aikit.skin), здесь - только стиль Дурака.
"""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPen, QRadialGradient

from aikit.skin import Skin
from game.ui import cardpaint as CP
from game.ui.menu import FAN
from game.ui.menu import palette as felt_palette


def _pal(name):
    f = felt_palette(name)
    dark = name == "dark"
    return {"bg": f["felt_edge"], "surface": f["leather"] if dark else "#f7f1e2", "surface2": f["chip"],
            "border": f["rim"], "text": f["ink"], "muted": f["muted"], "accent": f["gold"],
            "accent_text": f["card_ink"] if dark else "#ffffff", "good": "#3fbf7f", "bad": f["red"], "warn": f["gold"],
            "grid": f["panel_line"], "button": f["card"], "button_text": f["card_ink"], "field": f["chip"],
            "stripe": f["gold"]}


class FeltSkin(Skin):
    key = "durak-table"
    palettes = {"dark": _pal("dark"), "light": _pal("light")}
    heading_family = "Georgia"
    heading_px = 34
    heading_color = "accent"
    section_family = "Georgia"
    section_color = "accent"
    body_family = "Georgia"
    mono_family = "Consolas"
    radius = 14
    control_radius = 10
    border = 2
    card_style = "plain"
    button_style = "plain"
    card_alpha = 236

    def extra_qss(self, p, theme):
        f = felt_palette(theme)
        return f"""
QPushButton {{ font-family: "Georgia"; font-weight: 700; }}
QPushButton:hover {{ border: 2px solid {f['gold']}; }}
QPushButton#primary {{ background: {f['gold']}; border: 2px solid {f['rim']}; }}
QPushButton#seg {{ border-radius: 15px; border: 2px dashed {f['panel_line']}; background: {f['chip']}; }}
QPushButton#seg:checked {{ background: {f['gold']}; color: {f['card_ink']}; border: 2px solid {f['rim']}; }}
QHeaderView::section {{ font-family: "Georgia"; border-bottom: 2px solid {f['rim']}; }}
QTableWidget {{ font-family: "Segoe UI"; }}   /* у Georgia цифры старого стиля: 0 как «o» */
QLabel#skinTag {{ font-family: "Georgia"; font-style: italic; font-size: 14px; color: {f['muted']}; }}
"""

    def paint_backdrop(self, p, w, h, pal, theme):
        f = felt_palette(theme)
        p.fillRect(0, 0, w, h, QColor(f["felt_edge"]))
        m = min(w, h) * 0.02
        cloth = QRadialGradient(w * 0.5, h * 0.45, max(w, h) * 0.7)
        cloth.setColorAt(0, QColor(f["felt"]).lighter(112))
        cloth.setColorAt(1, QColor(f["felt"]))
        p.setPen(QPen(QColor(f["rim"]), max(2.0, m * 0.25)))
        p.setBrush(cloth)
        p.drawRoundedRect(QRectF(m, m, w - 2 * m, h - 2 * m), m * 3, m * 3)
        ch = max(70.0, h * 0.2)
        cw = ch * 0.68
        for i, (fx, fy, face, angle) in enumerate(((0.92, 0.80, False, 18), (0.95, 0.70, True, -8),
                                                    (0.03, 0.88, False, -14), (0.07, 0.82, True, 9))):
            p.save()
            p.translate(fx * w, fy * h)
            p.rotate(angle)
            CP.draw_card(p, QRectF(-cw / 2, -ch / 2, cw, ch), FAN[i % len(FAN)], face, theme)
            p.restore()
        veil = QColor(f["felt_edge"])
        veil.setAlphaF(0.25)
        p.fillRect(0, 0, w, h, veil)


SKIN = FeltSkin()
