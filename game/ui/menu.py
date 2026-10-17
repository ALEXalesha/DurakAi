"""Стартовое меню Дурака - «карточный стол».

Свой стиль (правило автора 17.10: у каждой игры своё меню, и боковые панели тоже): зелёное сукно
с виньеткой и золотой каймой стола; слева раздающий веер карт медленно раскрывается и
собирается, под ним колода с открытым козырем, сверху по одной падают карты «отбоя». Справа -
колонка: заголовок Georgia цвета старого золота, кнопки-карты (белая карта с мастью в углу,
масти по кругу ♠ ♥ ♦ ♣) и переключатели-фишки. Светлая тема - светлое сукно и бумажные карты.
Боковая панель партии - кожаная планка у края стола с золотой каймой.

Общее из aikit.menu - только живой фон (Backdrop), заголовок Title и законы раскладки. Карты
рисует свой game.ui.cardpaint, как на столе партии.
"""
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout

from aikit.menu import Backdrop, Title
from aikit.widgets import fit_segments, label, segmented
from game.core import cards as C
from game.ui import cardpaint as CP

PALETTES = {
    "dark": {
        "felt": "#1d4a35", "felt_edge": "#0e2419", "rim": "#b08d3c", "gold": "#e2c26b", "ink": "#f4efe1",
        "muted": "#b9c8bb", "panel": "rgba(20, 34, 26, 228)", "panel_line": "#6d5a2c", "chip": "#24543d",
        "card": "#fbf8ef", "card_ink": "#1c2230", "red": "#c8323c", "leather": "#2a1f17",
    },
    "light": {
        "felt": "#bfdcc8", "felt_edge": "#8fb8a0", "rim": "#9b7a2f", "gold": "#8a6a1e", "ink": "#1f2a22",
        "muted": "#47594c", "panel": "rgba(250, 247, 238, 235)", "panel_line": "#c4ab6e", "chip": "#e6efe7",
        "card": "#ffffff", "card_ink": "#1c2230", "red": "#c8323c", "leather": "#efe6d2",
    },
}

SUIT_ORDER = (0, 3, 2, 1)          # ♠ ♥ ♦ ♣ - у кнопок по кругу
FAN = (C.card(3, 8), C.card(0, 7), C.card(2, 6), C.card(1, 8), C.card(3, 5), C.card(0, 8))
TRUMP = C.card(2, 4)


def palette(name):
    return PALETTES.get(name, PALETTES["dark"])


def fan_open(t):
    """Насколько раскрыт веер (0..1): плавно раскрывается и собирается, период 9 с."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * (t % 9.0) / 9.0)


class Felt(Backdrop):
    """Фон: сукно, веер, колода с козырем и падающие карты отбоя - в левой части стола."""

    FPS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = "ru"
        self.free_right = 0.0            # карты - левее этой границы (раскладка меню сдвигает)
        rng = random.Random(5)
        self.falling = [(rng.randrange(36), rng.random(), rng.uniform(0.25, 0.45), rng.uniform(-30, 30),
                         rng.uniform(0, 12)) for _ in range(7)]

    def card_size(self, h):
        ch = max(90.0, h * 0.26)
        return ch * 0.68, ch

    def zone(self, w, h):
        right = self.free_right or w * 0.55
        return QRectF(w * 0.03, h * 0.06, max(0.0, right - w * 0.06), h * 0.88)

    def fan_rects(self, w, h, t):
        """[(карта, центр, угол)] веера - и для рисования, и для закона «не на кнопках»."""
        z = self.zone(w, h)
        cw, ch = self.card_size(h)
        cx, cy = z.center().x(), z.top() + z.height() * 0.58
        spread = 10 + 46 * fan_open(t)
        n = len(FAN)
        out = []
        for i, c in enumerate(FAN):
            a = (i - (n - 1) / 2) * spread / (n - 1) * 2 / 2
            out.append((c, QPointF(cx, cy), a))
        return out, (cw, ch)

    def paint_scene(self, p, w, h, t):
        pal = palette(self.theme_name)
        g = QRadialGradient(QPointF(w * 0.45, h * 0.45), max(w, h) * 0.75)
        g.setColorAt(0, QColor(pal["felt"]))
        g.setColorAt(1, QColor(pal["felt_edge"]))
        p.fillRect(0, 0, w, h, g)
        rim = QColor(pal["rim"])
        p.setPen(QPen(rim, max(2.0, h * 0.004)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        m = h * 0.025
        p.drawRoundedRect(QRectF(m, m, w - 2 * m, h - 2 * m), h * 0.08, h * 0.08)
        z = self.zone(w, h)
        if z.width() < 120:
            return
        cw, ch = self.card_size(h)
        cw, ch = min(cw, z.width() * 0.38), min(ch, z.width() * 0.38 / 0.68)
        p.save()
        p.setClipRect(QRectF(m * 2, m * 2, z.right() - m * 2, h - m * 4))     # внутри каймы, левее колонки
        # падающие карты отбоя - сверху вниз, повернувшись
        for c, lane, speed, turn, off in self.falling:
            y = ((t * speed * h * 0.25 + off * h * 0.1) % (h * 1.3)) - ch
            x = z.left() + lane * max(1.0, z.width() - cw)
            p.save()
            p.translate(x + cw / 2, y + ch / 2)
            p.rotate(turn + t * 8)
            p.setOpacity(0.35)
            CP.draw_card(p, QRectF(-cw * 0.4, -ch * 0.4, cw * 0.8, ch * 0.8), c, True, self.theme_name, self.lang)
            p.restore()
        # колода с козырем под ней
        dx, dy = z.left() + z.width() * 0.12, z.top() + z.height() * 0.12
        p.save()
        p.translate(dx + ch / 2, dy + cw / 2)
        p.rotate(90)
        CP.draw_card(p, QRectF(-cw / 2, -ch / 2, cw, ch), TRUMP, True, self.theme_name, self.lang, trump=True)
        p.restore()
        for k in range(4):
            CP.draw_card(p, QRectF(dx + k * 1.5, dy - k * 1.5, cw, ch), -1, False, self.theme_name, self.lang)
        # веер
        fan, _ = self.fan_rects(w, h, t)
        for c, centre, a in fan:
            p.save()
            p.translate(centre.x(), centre.y() + ch * 0.55)
            p.rotate(a)
            CP.draw_card(p, QRectF(-cw / 2, -ch * 1.05, cw, ch), c, True, self.theme_name, self.lang,
                         glow=(c == FAN[-1]))
            p.restore()
        p.restore()


class CardButton(QPushButton):
    """Кнопка-карта: белая карта, масть в левом углу своим контуром (как на картах стола)."""

    def __init__(self, suit, slot, primary=False):
        super().__init__("")
        self.suit = suit
        self.setObjectName("cardPrimary" if primary else "card")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda _=False: slot())
        self.mark = 20

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        CP.draw_suit(p, self.suit, self.mark * 1.15, self.height() / 2, self.mark)
        p.end()


def plate_qss(pal, k=1.0):
    def px(v):
        return f"{max(1, round(v * k))}px"
    return f"""
QPushButton#card, QPushButton#cardPrimary, QPushButton {{
    font-family: "Georgia", "Cambria"; font-size: {px(18)}; font-weight: 700;
    text-align: left; padding: {px(10)} {px(18)} {px(10)} {px(48)};
    background: {pal['card']}; color: {pal['card_ink']};
    border: 1px solid {pal['panel_line']}; border-radius: {px(10)};
}}
QPushButton#cardPrimary, QPushButton#primary {{ background: {pal['gold']}; color: {pal['card_ink'] if pal is PALETTES['dark'] else '#ffffff'};
    border: {px(2)} solid {pal['rim']}; }}
QPushButton:hover {{ border: {px(2)} solid {pal['gold']}; }}
QPushButton:disabled {{ color: {pal['muted']}; background: {pal['chip']}; }}
QPushButton#seg {{
    font-family: "Georgia", "Cambria"; font-size: {px(14)}; font-weight: 400; text-align: center;
    padding: {px(5)} {px(12)}; border-radius: {px(15)};
    background: {pal['chip']}; color: {pal['ink']}; border: {px(2)} dashed {pal['panel_line']};
}}
QPushButton#seg:checked {{ background: {pal['gold']}; color: {pal['card_ink']}; border: {px(2)} solid {pal['rim']}; font-weight: 700; }}
"""


def menu_qss(pal, k):
    def px(v):
        return f"{max(1, round(v * k))}px"
    return f"""
QFrame#rail {{ background: {pal['panel']}; border: {px(2)} solid {pal['rim']}; border-radius: {px(16)}; }}
QLabel#feltSub {{ font-family: "Georgia", "Cambria"; font-style: italic; font-size: {px(15)}; color: {pal['muted']}; }}
QLabel#feltCaption {{ font-family: "Georgia", "Cambria"; font-size: {px(14)}; color: {pal['gold']}; }}
QLabel#feltNote {{ font-family: "Georgia", "Cambria"; font-size: {px(12)}; color: {pal['muted']}; }}
QLabel#feltFoot {{ font-family: "Georgia", "Cambria"; font-size: {px(12)}; color: {pal['muted']}; }}
""" + plate_qss(pal, k)


def page_qss(pal):
    return f"QWidget#page {{ background: {pal['felt_edge']}; }}"


def side_qss(pal):
    """Боковая панель партии - кожаная планка у края стола с золотой каймой."""
    return f"""
QFrame#card {{ background: {pal['panel']}; border: 2px solid {pal['rim']}; border-radius: 16px; }}
QLabel {{ color: {pal['ink']}; }}
QLabel#section {{ font-family: "Georgia", "Cambria"; font-size: 17px; font-weight: 700; color: {pal['gold']}; }}
QLabel#status {{ font-family: "Georgia", "Cambria"; font-size: 20px; font-weight: 700; color: {pal['ink']}; }}
QLabel#statusWin {{ font-family: "Georgia", "Cambria"; font-size: 20px; font-weight: 700; color: #3fbf7f; }}
QLabel#statusLoss {{ font-family: "Georgia", "Cambria"; font-size: 20px; font-weight: 700; color: {pal['red']}; }}
QLabel#statusDraw {{ font-family: "Georgia", "Cambria"; font-size: 20px; font-weight: 700; color: {pal['gold']}; }}
QLabel#muted {{ color: {pal['muted']}; }}
QLabel#hint {{ font-family: "Georgia", "Cambria"; font-size: 12px; color: {pal['muted']}; }}
QListWidget {{ background: {pal['chip']}; color: {pal['ink']}; border: 1px solid {pal['panel_line']}; border-radius: 8px; }}
QCheckBox {{ font-family: "Georgia", "Cambria"; color: {pal['ink']}; spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 9px; border: 2px solid {pal['rim']}; background: {pal['chip']}; }}
QCheckBox::indicator:checked {{ background: {pal['gold']}; image: none; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QPushButton {{
    font-family: "Georgia", "Cambria"; font-size: 15px; font-weight: 700; padding: 7px 10px;
    background: {pal['card']}; color: {pal['card_ink']}; border: 1px solid {pal['panel_line']}; border-radius: 10px;
}}
QPushButton:hover {{ border: 2px solid {pal['gold']}; }}
QPushButton:disabled {{ color: {pal['muted']}; background: {pal['chip']}; }}
QPushButton#primary {{ background: {pal['gold']}; color: {pal['card_ink'] if pal is PALETTES['dark'] else '#ffffff'}; border: 2px solid {pal['rim']}; }}
"""


class MenuPage(Felt):
    """Меню: справа колонка на «рейке» стола, слева - веер карт."""

    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.scale = None
        root = QHBoxLayout(self)
        self.root = root
        root.addStretch(1)
        col = QVBoxLayout()
        self.column = col
        root.addLayout(col)
        col.addStretch(1)
        self.title = Title("Georgia", 70, spacing=0.02, min_px=30, align=Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.title)
        self.sub = label("", "feltSub", wrap=True)
        col.addWidget(self.sub)
        self.rail = QFrame()
        self.rail.setObjectName("rail")
        grid = QGridLayout(self.rail)
        self.grid = grid
        self.captions = {}
        self.seg = {}
        from game.ui.widget import PLAY_LEVELS
        rows = (("players", segmented({2: "2", 3: "3", 4: "4"}, lambda v: gw.change("players", v))),
                ("level", segmented({lv: "" for lv in PLAY_LEVELS}, lambda v: gw.change("level", v))),
                ("variant", segmented({False: "", True: ""}, lambda v: gw.change("transfer", v))),
                ("mode", segmented({"play": "", "demo": ""}, lambda v: gw.change("mode", v))))
        for r, (key, (box, buttons)) in enumerate(rows):
            cap = label("", "feltCaption")
            self.captions[key] = cap
            grid.addWidget(cap, r, 0)
            grid.addWidget(box, r, 1)
            self.seg[key] = buttons
        grid.setColumnStretch(2, 1)
        col.addWidget(self.rail)
        self.note = label("", "feltNote", wrap=True)
        col.addWidget(self.note)
        # clicked(bool) не доходит до start_game (зерно False) - CardButton зовёт slot() без аргументов
        self.play_button = CardButton(SUIT_ORDER[0], gw.start_game, primary=True)
        self.stats_button = CardButton(SUIT_ORDER[1], lambda: gw.show_page("stats"))
        self.settings_button = CardButton(SUIT_ORDER[2], lambda: gw.show_page("settings"))
        self.buttons = (self.play_button, self.stats_button, self.settings_button)
        for b in self.buttons:
            col.addWidget(b)
        col.addStretch(1)
        self.foot = label("", "feltFoot", wrap=True)
        col.addWidget(self.foot)
        self.apply_scale(force=True)

    def scale_for(self, w, h):
        return round(max(1.0, min(2.4, w / 1280, h / 800)), 2)

    def column_width(self):
        return round(min(540 * self.scale, max(470, self.width() * 0.5)))

    def apply_scale(self, force=False):
        k = self.scale_for(max(self.width(), 900), max(self.height(), 700))
        if not force and k == self.scale:
            return
        self.scale = k
        pal = palette(self.theme_name)
        self.setStyleSheet(menu_qss(pal, k))
        self.title.px = round(70 * k)
        self.title.min_px = round(30 * k)
        self.title.set_color(pal["gold"])
        self.title.updateGeometry()
        self.root.setContentsMargins(round(30 * k), round(34 * k), round(60 * k), round(40 * k))
        self.column.setSpacing(round(10 * k))
        self.grid.setContentsMargins(round(18 * k), round(14 * k), round(18 * k), round(14 * k))
        self.grid.setHorizontalSpacing(round(12 * k))
        self.grid.setVerticalSpacing(round(9 * k))
        for b in self.buttons:
            b.mark = round(20 * k)
            b.update()
        for group in self.seg.values():
            fit_segments(group)
        self._fit()

    def _fit(self):
        w = self.column_width()
        for x in (self.title, self.sub, self.rail, self.note, self.foot) + self.buttons:
            x.setFixedWidth(w)
        right = self.root.contentsMargins().right()
        self.free_right = self.width() - right - w - round(20 * self.scale)

    def column_rect(self):
        w = self.column_width()
        right = self.root.contentsMargins().right()
        return QRectF(self.width() - right - w, 0, w, self.height())

    def set_theme(self, name):
        super().set_theme(name)
        self.apply_scale(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_scale()
        self._fit()

    def sync(self, s):
        self.seg["players"][s["players"]].setChecked(True)
        self.seg["level"][s["level"]].setChecked(True)
        self.seg["variant"][s["transfer"]].setChecked(True)
        self.seg["mode"][s["mode"]].setChecked(True)
        from game.ai.net import default_net
        self.note.setText("" if default_net() is not None else self.gw.t("no_net"))
        self.note.setVisible(bool(self.note.text()))

    def retranslate(self):
        t = self.gw.t
        self.lang = self.gw.ctx.lang
        self.title.setText(t("app_title"))
        self.sub.setText(t("app_sub"))
        for key, cap in self.captions.items():
            cap.setText(t(key))
        for k, b in self.seg["level"].items():
            b.setText(t(k))
        self.seg["variant"][False].setText(t("podkidnoy"))
        self.seg["variant"][True].setText(t("perevodnoy"))
        for k, b in self.seg["mode"].items():
            b.setText(t("mode_" + k))
        self.play_button.setText(t("play"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.apply_scale(force=True)
        self.sync(self.gw.settings)
        self.update()

    def set_foot(self, text):
        self.foot.setText(text)
