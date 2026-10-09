"""Виджет игры (create_widget по контракту): меню, стол, статистика, настройки.

Окно ему даёт оболочка (aikit.run_standalone или ИИ-Игротека). Тема и язык приходят из
ctx и меняются на лету по ctx.changed. Файлы - только в ctx.data_dir.
"""
import json
import os
import random

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QScrollArea, QSlider, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from aikit import settings as st
from aikit import theme
from aikit.widgets import Combo, button, card, label, restyle, segmented
from game.ai.agents import LEVELS
from game.core.durak import DRAW, MOVE_PASS, MOVE_TAKE, TRANSFER
from game.ui.ai_thread import AiController
from game.ui.i18n import translator
from game.ui.session import Session
from game.ui.table import TableWidget
from game.ui.thoughts import ProbGrid, move_text
from game.version import VERSION

PLAY_LEVELS = ("novice", "medium", "strong")
SCHEMA = {
    "players": (2, st.int_range(2, 4)),
    "level": ("medium", st.choice(*PLAY_LEVELS)),
    "mode": ("play", st.choice("play", "demo")),
    "transfer": (False, st.boolean()),
    "five": (False, st.boolean()),
    "first_rule": ("lowest", st.choice("lowest", "after_fool")),
    "show_thoughts": (False, st.boolean()),
    "reveal": (False, st.boolean()),
    "anim_ms": (260, st.int_range(0, 800)),
    "delay_ms": (450, st.int_range(0, 3000)),
}
PASSPORT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "durak-value.json")


def page_widget():
    w = QWidget()
    w.setObjectName("page")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return w


def fmt_time(t, seconds):
    if seconds < 90:
        return t("seconds", n=round(seconds))
    if seconds < 5400:
        return t("minutes", n=round(seconds / 60))
    return t("hours", n=f"{seconds / 3600:.1f}")


def number(n):
    return f"{n:,}".replace(",", " ")


def load_passport():
    with open(PASSPORT, encoding="utf-8") as f:
        return json.load(f)


# --- меню ---


class MenuPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        from PySide6.QtGui import QPixmap
        from game.ui.icon import render
        self.logo = QLabel()
        self.logo.setPixmap(QPixmap.fromImage(render(112)))
        col.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = label("", "title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.sub = label("", "muted", wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setFixedWidth(620)
        col.addWidget(self.sub, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(12)
        box = card()
        box.setMaximumWidth(640)
        grid = QGridLayout(box)
        grid.setContentsMargins(22, 18, 22, 18)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self.captions = {}

        def row(r, key, widget):
            cap = label("", "muted")
            self.captions[key] = cap
            grid.addWidget(cap, r, 0)
            grid.addWidget(widget, r, 1)

        w, self.players_buttons = segmented({2: "2", 3: "3", 4: "4"}, lambda v: gw.change("players", v))
        row(0, "players", w)
        w, self.level_buttons = segmented({lv: "" for lv in PLAY_LEVELS}, lambda v: gw.change("level", v))
        row(1, "level", w)
        w, self.variant_buttons = segmented({False: "", True: ""}, lambda v: gw.change("transfer", v))
        row(2, "variant", w)
        w, self.mode_buttons = segmented({"play": "", "demo": ""}, lambda v: gw.change("mode", v))
        row(3, "mode", w)
        col.addWidget(box, 0, Qt.AlignmentFlag.AlignHCenter)
        self.note = label("", "hint", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note.setFixedWidth(620)
        col.addWidget(self.note, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(8)
        self.play_button = button("", "menuPrimary", lambda: gw.start_game())
        self.stats_button = button("", "menu", lambda: gw.show_page("stats"))
        self.settings_button = button("", "menu", lambda: gw.show_page("settings"))
        for b in (self.play_button, self.stats_button, self.settings_button):
            col.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(col)
        outer.addStretch(3)
        self.foot = label("", "hint")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.foot)

    def sync(self, s):
        self.players_buttons[s["players"]].setChecked(True)
        self.level_buttons[s["level"]].setChecked(True)
        self.variant_buttons[s["transfer"]].setChecked(True)
        self.mode_buttons[s["mode"]].setChecked(True)
        from game.ai.net import default_net
        self.note.setText("" if default_net() is not None else self.gw.t("no_net"))
        self.note.setVisible(bool(self.note.text()))

    def retranslate(self):
        t = self.gw.t
        self.title.setText(t("app_title"))
        self.sub.setText(t("app_sub"))
        for key, cap in self.captions.items():
            cap.setText(t(key))
        for k, b in self.level_buttons.items():
            b.setText(t(k))
        self.variant_buttons[False].setText(t("podkidnoy"))
        self.variant_buttons[True].setText(t("perevodnoy"))
        for k, b in self.mode_buttons.items():
            b.setText(t("mode_" + k))
        self.play_button.setText(t("play"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.foot.setText(t("footer", v=VERSION))
        self.sync(self.gw.settings)


# --- партия ---


class PlayPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)
        self.table = TableWidget()
        self.table.moveChosen.connect(gw.on_move_chosen)
        root.addWidget(self.table, 1)

        side = card()
        side.setFixedWidth(330)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(6)
        self.heading = label("", "section", wrap=True)
        col.addWidget(self.heading)
        self.status = label("", "status", wrap=True)
        col.addWidget(self.status)
        self.substatus = label("", "muted", wrap=True)
        self.substatus.setMinimumHeight(38)     # только снизу: перенос строк не обрезается
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.substatus)
        acts = QHBoxLayout()
        self.pass_button = button("", "primary", gw.on_pass)
        self.take_button = button("", None, gw.on_take)
        acts.addWidget(self.pass_button, 1)
        acts.addWidget(self.take_button, 1)
        col.addLayout(acts)
        self.info = label("", "hint", wrap=True)
        col.addWidget(self.info)

        self.thoughts_box = QCheckBox("")
        self.thoughts_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.thoughts_box.toggled.connect(lambda on: gw.change("show_thoughts", on))
        col.addWidget(self.thoughts_box)
        self.thoughts_hint = label("", "hint", wrap=True)
        col.addWidget(self.thoughts_hint)
        self.grid = ProbGrid()
        col.addWidget(self.grid)
        self.moves_caption = label("", "muted")
        col.addWidget(self.moves_caption)
        self.moves = QListWidget()
        self.moves.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.moves.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.moves.setMinimumHeight(110)
        col.addWidget(self.moves)

        self.reveal_box = QCheckBox("")
        self.reveal_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reveal_box.toggled.connect(lambda on: gw.change("reveal", on))
        col.addWidget(self.reveal_box)
        self.reveal_hint = label("", "hint", wrap=True)
        col.addWidget(self.reveal_hint)
        self.pause_button = button("", None, gw.toggle_pause)
        col.addWidget(self.pause_button)
        col.addStretch(1)
        last = QHBoxLayout()
        self.again_button = button("", "primary", lambda: gw.start_game())
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        last.addWidget(self.again_button, 1)
        last.addWidget(self.menu_button, 1)
        col.addLayout(last)
        root.addWidget(side)
        self.side = side

    def fit_labels(self):
        """Подписи с переносом получают высоту по своей ширине (ловушка qt-wrapped-label-height:
        высоту не фиксировать, только минимум)."""
        for w in self.side.findChildren(QLabel):
            if w.wordWrap() and w.width() > 0:
                base = 38 if w is self.substatus else 0
                w.setMinimumHeight(max(base, w.heightForWidth(w.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_labels()

    def retranslate(self):
        t = self.gw.t
        self.take_button.setText(t("take"))
        self.thoughts_box.setText(t("thoughts"))
        self.moves_caption.setText(t("moves_eval"))
        self.reveal_box.setText(t("reveal"))
        self.reveal_hint.setText(t("reveal_hint"))
        self.again_button.setText(t("again"))
        self.menu_button.setText(t("menu"))
        self.pause_button.setText(t("resume") if self.gw.paused else t("pause"))
        self.fit_labels()


# --- статистика ---


def table_widget(cols):
    tw = QTableWidget(0, cols)
    tw.verticalHeader().setVisible(False)
    tw.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tw.setShowGrid(False)
    tw.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tw.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = tw.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setHighlightSections(False)
    return tw


def fit_height(tw):
    tw.resizeRowsToContents()
    tw.setFixedHeight(tw.horizontalHeader().height() + sum(tw.rowHeight(r) for r in range(tw.rowCount())) + 4)


def item(text, align=Qt.AlignmentFlag.AlignCenter):
    it = QTableWidgetItem(text)
    it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return it


class StatsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = page_widget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(26, 22, 26, 22)
        col.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        top.addWidget(self.menu_button)
        col.addLayout(top)
        mine = card()
        mc = QVBoxLayout(mine)
        mc.setContentsMargins(18, 14, 18, 14)
        self.mine_title = label("", "section")
        mc.addWidget(self.mine_title)
        self.table = table_widget(6)
        mc.addWidget(self.table)
        col.addWidget(mine)
        pc = card()
        lay = QVBoxLayout(pc)
        lay.setContentsMargins(18, 14, 18, 14)
        self.pass_title = label("", "section")
        self.pass_text = label("", "muted", wrap=True)
        self.checks = table_widget(3)
        self.pass_foot = label("", "hint", wrap=True)
        for w in (self.pass_title, self.pass_text, self.checks, self.pass_foot):
            lay.addWidget(w)
        col.addWidget(pc)
        col.addStretch(1)

    def refresh(self):
        t = self.gw.t
        self.heading.setText(t("stats_title"))
        self.menu_button.setText(t("menu"))
        self.mine_title.setText(t("your_games"))
        self.table.setHorizontalHeaderLabels([t(k) for k in ("col_setup", "col_games", "col_wins", "col_draws",
                                                               "col_fools", "col_streak")])
        rows = [(n, lv) for n in (2, 3, 4) for lv in PLAY_LEVELS]
        self.table.setRowCount(len(rows))
        stats = self.gw.ctx.stats
        for r, (n, lv) in enumerate(rows):
            e = stats.entry(f"{n}p/{lv}")
            self.table.setItem(r, 0, item(f"{n} · {t(lv)}", Qt.AlignmentFlag.AlignLeft))
            for c, f in enumerate(("games", "wins", "draws", "losses", "best_streak"), start=1):
                self.table.setItem(r, c, item(str(e[f])))
        fit_height(self.table)
        self.pass_title.setText(t("passport"))
        try:
            pp = load_passport()
        except (OSError, ValueError):
            self.pass_text.setText(t("not_trained"))
            self.checks.hide()
            self.pass_foot.hide()
            return
        net, tr = pp["network"], pp["training"]
        self.pass_text.setText(t("passport_text", features=net["features"],
                                 hidden=" × ".join(str(h) for h in net["hidden"]),
                                 params=number(net["parameters"]), games=number(tr["games"]),
                                 positions=number(tr["positions"]), time=fmt_time(t, tr["seconds"])))
        self.checks.setHorizontalHeaderLabels([t("col_level"), t("col_check"), t("col_result")])
        rows = pp["checks"]
        self.checks.setRowCount(len(rows))
        for r, ch in enumerate(rows):
            self.checks.setItem(r, 0, item(t(ch["level"]), Qt.AlignmentFlag.AlignLeft))
            self.checks.setItem(r, 1, item(t("check_" + ch["check"])))
            if ch["players"] == 2:
                res = f"{100 * ch['score']:.1f}%"
            else:
                res = t("fool_rate", p=f"{100 * ch['fool_rate']:.1f}", q=f"{100 / ch['players']:.0f}")
            self.checks.setItem(r, 2, item(res))
        fit_height(self.checks)
        self.checks.show()
        self.pass_foot.setText(t("checks_text", n=pp.get("games_per_check", 1000)))
        self.pass_foot.show()


# --- настройки ---


class SettingsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer0 = QVBoxLayout(self)
        outer0.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer0.addWidget(scroll)
        body = page_widget()
        scroll.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        top.addWidget(self.menu_button)
        outer.addLayout(top)
        box = card()
        box.setMaximumWidth(760)
        self.grid = QGridLayout(box)
        self.grid.setContentsMargins(22, 18, 22, 18)
        self.grid.setHorizontalSpacing(22)
        self.grid.setVerticalSpacing(16)
        self.grid.setColumnStretch(0, 1)
        self.rows = {}
        self.theme_combo = Combo()
        for k in theme.THEMES:
            self.theme_combo.addItem("", k)
        self.theme_combo.currentIndexChanged.connect(lambda i: gw.ctx.set_theme(self.theme_combo.itemData(i)))
        self._row("theme", self.theme_combo)
        self.lang_combo = Combo()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.currentIndexChanged.connect(lambda i: gw.ctx.set_lang(self.lang_combo.itemData(i)))
        self._row("language", self.lang_combo)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(gw.ctx.sound.volume)
        self.volume.valueChanged.connect(gw.ctx.set_volume)
        self._row("volume", self.volume)
        self.anim = QSlider(Qt.Orientation.Horizontal)
        self.anim.setRange(0, 800)
        self.anim.valueChanged.connect(lambda v: gw.change("anim_ms", int(v)))
        self._row("anim", self.anim)
        self.delay = QSlider(Qt.Orientation.Horizontal)
        self.delay.setRange(0, 3000)
        self.delay.valueChanged.connect(lambda v: gw.change("delay_ms", int(v)))
        self._row("delay", self.delay)
        self.transfer_box = QCheckBox("")
        self.transfer_box.toggled.connect(lambda on: gw.change("transfer", on))
        self._row("transfer", self.transfer_box)
        self.five_box = QCheckBox("")
        self.five_box.toggled.connect(lambda on: gw.change("five", on))
        self._row("five", self.five_box)
        self.first_combo = Combo()
        self.first_combo.addItem("", "lowest")
        self.first_combo.addItem("", "after_fool")
        self.first_combo.currentIndexChanged.connect(lambda i: gw.change("first_rule", self.first_combo.itemData(i)))
        self._row("first_rule", self.first_combo)
        outer.addWidget(box)
        self.note = label("", "hint")
        outer.addWidget(self.note)
        outer.addStretch(1)

    def _row(self, key, widget):
        r = len(self.rows)
        names = QVBoxLayout()
        names.setSpacing(2)
        title = label("", "section")
        hint = label("", "hint", wrap=True)
        names.addWidget(title)
        names.addWidget(hint)
        self.grid.addLayout(names, r, 0)
        self.grid.addWidget(widget, r, 1)
        self.rows[key] = (title, hint)

    def retranslate(self):
        t = self.gw.t
        self.heading.setText(t("settings_title"))
        self.menu_button.setText(t("menu"))
        for key, (title, hint) in self.rows.items():
            title.setText(t(key))
            hint.setText(t(key + "_hint"))
        for i, k in enumerate(theme.THEMES):
            self.theme_combo.setItemText(i, t(k))
        self.first_combo.setItemText(0, t("first_lowest"))
        self.first_combo.setItemText(1, t("first_after_fool"))
        self.note.setText(t("saved_note"))
        self.sync()

    def sync(self):
        g = self.gw
        for combo, value in ((self.theme_combo, g.ctx.theme), (self.lang_combo, g.ctx.lang),
                             (self.first_combo, g.settings["first_rule"])):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(value))
            combo.blockSignals(False)
        for w, value in ((self.anim, g.settings["anim_ms"]), (self.delay, g.settings["delay_ms"])):
            w.blockSignals(True)
            w.setValue(value)
            w.blockSignals(False)
        for w, value in ((self.transfer_box, g.settings["transfer"]), (self.five_box, g.settings["five"])):
            w.blockSignals(True)
            w.setChecked(value)
            w.blockSignals(False)


# --- сам виджет игры ---


class GameWidget(QWidget):
    def __init__(self, ctx):
        super().__init__()
        # gc.freeze() здесь нет: сборщик мусора общий на весь процесс, и в оболочке
        # заморозка навсегда оставила бы в памяти и её объекты. Замер tools/gc_bench.py:
        # без заморозки ни ходы ИИ, ни отклик окна не хуже (README, раздел о 1.0.0).
        self.ctx = ctx
        self.t = translator(ctx.lang)
        self.settings = st.Settings(SCHEMA, ctx.file("settings.json"))
        self.session = None
        self.token = 0
        self.paused = False           # пауза показа «ИИ против ИИ» (кнопка)
        self.hidden = False           # оболочка спрятала вкладку: pause() / resume()
        self.thoughts = None
        self.last_fool = None
        self.rng = random.Random()
        self.ai = AiController(self)
        self.ai.ready.connect(self.on_ai)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._step)
        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.menu = MenuPage(self)
        self.play = PlayPage(self)
        self.stats = StatsPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = {"menu": self.menu, "play": self.play, "stats": self.stats, "settings": self.settings_page}
        for p in self.pages.values():
            self.stack.addWidget(p)
        for keys, slot in (("Escape", lambda: self.show_page("menu")), ("Space", self.on_pass),
                           ("T", self.on_take), ("N", self.start_game)):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
        ctx.changed.connect(self.on_ctx_changed)
        self.play.table.anim_ms = self.settings["anim_ms"]
        self.apply_theme()
        self.retranslate()
        self.show_page("menu")

    def minimumSizeHint(self):
        return QSize(980, 640)

    # --- общее ---

    def current_page(self):
        w = self.stack.currentWidget()
        return next(k for k, p in self.pages.items() if p is w)

    def show_page(self, name):
        if name != "play":
            self._invalidate()
        self.stack.setCurrentWidget(self.pages[name])
        if name == "stats":
            self.stats.refresh()
        elif name == "settings":
            self.settings_page.sync()
        elif name == "menu":
            self.menu.sync(self.settings)

    def change(self, key, value):
        if self.settings[key] == value:
            return
        self.settings.set(key, value)
        if key in ("players", "level", "mode", "transfer"):
            self.menu.sync(self.settings)
            self.settings_page.sync()
        elif key == "anim_ms":
            self.play.table.anim_ms = value
        elif key in ("show_thoughts", "reveal"):
            if key == "reveal" and value and self.session is not None and self.session.mode == "play":
                self.session.peeked = True
            self.thoughts = None
            self.after_change()

    def on_ctx_changed(self, what):
        if what == "theme":
            self.apply_theme()
        elif what == "lang":
            self.t = translator(self.ctx.lang)
            self.retranslate()

    def apply_theme(self):
        c = theme.palette(self.ctx.theme)
        self.play.table.set_theme(self.ctx.theme, self.ctx.lang)
        self.play.grid.set_theme(self.ctx.theme, self.ctx.lang)
        for combo in self.findChildren(Combo):
            combo.set_arrow_color(c["text"])
        self.update()

    def retranslate(self):
        self.play.table.set_theme(self.ctx.theme, self.ctx.lang)
        self.play.grid.set_theme(self.ctx.theme, self.ctx.lang)
        self.menu.retranslate()
        self.play.retranslate()
        self.settings_page.retranslate()
        if self.current_page() == "stats":
            self.stats.refresh()
        if self.session is not None:
            self.refresh(animate=False)

    def pause(self):
        """Оболочка спрятала вкладку (переключились на другую игру, свернули окно): ИИ
        не думает и не ходит, таймеры стоят, полёт карт сразу кончается. Партия ждёт."""
        if self.hidden:
            return
        self.hidden = True
        self._invalidate()
        self.play.table.finish_animation()

    def resume(self):
        """Вкладку показали снова: партия идёт дальше с того же места."""
        if not self.hidden:
            return
        self.hidden = False
        if self.session is not None and self.current_page() == "play":
            self.after_change()

    def shutdown(self):
        """Окно закрывается: таймеры стоп, поиски остановить и дождаться (не дольше 2 с)."""
        self._invalidate()
        return self.ai.shutdown(2000)

    def _invalidate(self):
        self.token += 1
        self.timer.stop()
        self.ai.cancel()

    # --- партия ---

    def start_game(self, seed=None):
        s = self.settings
        if seed is None or isinstance(seed, bool):    # clicked(bool) кнопки - не зерно
            seed = self.rng.randrange(2 ** 31)
        first = None
        if s["first_rule"] == "after_fool" and self.last_fool is not None and self.last_fool[1] == s["players"]:
            first = (self.last_fool[0] + 1) % s["players"]
        self.session = Session(s["players"], s["level"], s["mode"], s["transfer"], s["five"], seed, first)
        self.session.peeked = s["reveal"] and s["mode"] == "play"
        self.paused = False
        self.thoughts = None
        self.stack.setCurrentWidget(self.play)
        self._invalidate()
        self.play.table.start_deal()
        self.after_change()

    def _human_may(self, move):
        """Ход человека принимается только со стола: клавиши Пробел и T работают и в меню,
        а партия там спрятана."""
        s = self.session
        return (s is not None and not self.hidden and self.current_page() == "play"
                and s.human_turn() and move in s.legal())

    def on_move_chosen(self, move):
        if self._human_may(move):
            self._apply(move)

    def on_pass(self):
        if self._human_may(MOVE_PASS):
            self._apply(MOVE_PASS)

    def on_take(self):
        if self._human_may(MOVE_TAKE):
            self._apply(MOVE_TAKE)

    def _apply(self, move):
        s = self.session
        s.apply(move)
        self.ctx.sound.play("capture" if move == MOVE_TAKE else "move")
        self.thoughts = None
        self.after_change()

    def names(self):
        s = self.session
        out = []
        for p in range(s.n):
            if p == s.human:
                out.append(self.t("you"))
            else:
                out.append(self.t("ai_n", n=p if s.human == 0 else p + 1))
        return out

    def after_change(self):
        """После любого изменения партии: перерисовать, записать итог, запустить ИИ."""
        self.token += 1
        self.timer.stop()
        self.ai.cancel()
        s = self.session
        if s is None:
            return
        self.refresh()
        if s.over:
            self._finish()
            return
        if self.hidden:                   # resume() запустит ход заново
            return
        if s.human_turn():
            legal = s.legal()
            if legal == [MOVE_PASS]:          # подкинуть нечего - пас без вопроса
                self.timer.start(self._delay(short=True))
            elif self.settings["show_thoughts"]:
                self.ai.request_thoughts(self.token, s.obs(s.human), self.rng.randrange(2 ** 31))
            return
        if s.mode == "demo" and self.paused:
            return
        self.timer.start(self._delay())

    def _delay(self, short=False):
        anim = round(max(0.0, self.play.table.anim_left()) * 1000)   # сначала долетят карты
        base = 120 if short else self.settings["delay_ms"]
        return max(base, anim + 40)

    def _step(self):
        s = self.session
        if s is None or s.over:
            return
        if s.human_turn():
            if s.legal() == [MOVE_PASS]:
                self._apply(MOVE_PASS)
            return
        legal = s.legal()
        if len(legal) == 1:
            self._apply(legal[0])
            return
        p = s.state.turn
        self.refresh(animate=False)
        obs = s.obs(p)
        if s.mode == "demo" and self.settings["show_thoughts"]:
            self.ai.request_thoughts(self.token, obs, self.rng.randrange(2 ** 31))
        self.ai.request_move(self.token, obs, s.level, self.rng.randrange(2 ** 31))

    def on_ai(self, token, kind, payload):
        if token != self.token or self.session is None:
            return
        s = self.session
        if isinstance(payload, Exception):
            self.play.info.setText(self.t("error", e=payload))
            return
        if kind == "thoughts":
            self.thoughts = payload
            self.refresh(animate=False)
            return
        if s.ai_turn() and payload in s.legal():
            self._apply(payload)

    def _finish(self):
        s = self.session
        self.last_fool = (s.fool(), s.n) if s.fool() != DRAW else None
        outcome = s.outcome_for_human()
        if outcome and not s.recorded:
            if not s.peeked:
                self.ctx.stats.record(s.stats_key(), outcome)
            s.recorded = True
            self.ctx.sound.play(outcome)

    def toggle_pause(self):
        self.paused = not self.paused
        self.play.pause_button.setText(self.t("resume") if self.paused else self.t("pause"))
        if not self.paused:
            self.after_change()
        else:
            self._invalidate()

    # --- вид ---

    def refresh(self, animate=True):
        s = self.session
        if s is None:
            return
        t = self.t
        pp = self.play
        st_ = s.state
        names = self.names()
        demo = s.mode == "demo"
        reveal = demo or self.settings["reveal"]
        human_turn = s.human_turn()
        legal = s.legal() if human_turn else []
        scores = None
        if self.thoughts and self.settings["show_thoughts"] and self.thoughts["player"] == (st_.turn if demo else s.human):
            scores = dict(self.thoughts["scores"])
        badges = {}
        if not st_.over:
            badges[st_.attacker] = t("attacks")
            badges[st_.defender] = t("defends")
        for q in st_.out:
            badges[q] = t("out")
        if st_.over and st_.fool >= 0:
            badges[st_.fool] = t("fool_badge")
        pp.table.badges = badges
        thinking = st_.turn if (s.ai_turn() and not st_.over) else -1
        pp.table.set_state(st_, 0, legal, reveal, names, thinking, scores if not demo else None, animate=animate)
        variant = t("perevodnoy") if s.rules.transfer else t("podkidnoy")
        pp.heading.setText(f"{t('app_title')} · {variant} · {s.n}")
        if st_.over:
            outcome = s.outcome_for_human()
            if outcome:
                restyle(pp.status, {"win": "statusWin", "loss": "statusLoss", "draw": "statusDraw"}[outcome])
                pp.status.setText(t(outcome))
            else:
                restyle(pp.status, "statusDraw" if st_.fool == DRAW else "status")
                pp.status.setText(t("draw") if st_.fool == DRAW else t("fool_is", name=names[st_.fool]))
            pp.substatus.setText(t("nobody_fool") if st_.fool == DRAW else t("fool_is", name=names[st_.fool]))
        else:
            restyle(pp.status, "status")
            ph = st_.phase()
            if human_turn:
                if ph == "attack":
                    pp.status.setText(t("your_attack"))
                elif ph == "defend":
                    text = t("your_defend")
                    if any(m[0] == TRANSFER for m in legal):
                        text += ". " + t("your_transfer")
                    pp.status.setText(text)
                else:
                    pp.status.setText(t("your_throw", word=t("pass") if st_.taking else t("bito")))
            else:
                pp.status.setText(t("ai_thinks", name=names[st_.turn]))
            if demo:
                sub = t("demo_text", level=t(s.level).lower())
            else:
                sub = t("play_text", level=t(s.level).lower(), variant=variant)
            if st_.taking and st_.defender != s.human:
                sub = t("taking", name=names[st_.defender]) + " " + sub
            pp.substatus.setText(sub)
        trump_name = t("trump") + ": " + "♠♣♦♥"[st_.trump]
        pp.info.setText(f"{trump_name} · " + (t("deck_left", n=len(st_.deck)) if st_.deck else t("deck_empty"))
                        + " · " + t("discard", n=st_.discard.bit_count()))
        pass_ok = MOVE_PASS in legal
        pp.pass_button.setText(t("pass") if st_.taking else t("bito"))
        pp.pass_button.setEnabled(pass_ok)
        pp.take_button.setEnabled(MOVE_TAKE in legal)
        # кнопка видна, только когда этот ход есть: выключенная «основная» кнопка на вид
        # не отличается от включённой
        pp.pass_button.setVisible(not demo and pass_ok)
        pp.take_button.setVisible(not demo and MOVE_TAKE in legal)
        show = self.settings["show_thoughts"]
        pp.thoughts_box.blockSignals(True)
        pp.thoughts_box.setChecked(show)
        pp.thoughts_box.blockSignals(False)
        pp.thoughts_hint.setText(t("thoughts_hint_demo") if demo else t("thoughts_hint"))
        pp.thoughts_hint.setVisible(show)
        th = self.thoughts if show else None
        if th is not None:
            P = th["belief"]
            viewer = th["player"]
            blocks = [(t("prob_of", name=names[q]), P[:, q]) for q in range(s.n)
                      if q != viewer and q not in st_.out]
            if st_.deck:
                blocks.append((t("prob_deck"), P[:, s.n]))
            pp.grid.set_data(blocks, st_.trump)
            pp.moves.clear()
            for m, v in sorted(th["scores"], key=lambda x: -x[1]):
                pp.moves.addItem(f"{v:+.2f}   {move_text(t, m, self.ctx.lang)}")
        else:
            pp.grid.set_data([], st_.trump)
            pp.moves.clear()
        pp.grid.setVisible(show and th is not None)
        pp.moves.setVisible(show and th is not None)
        pp.moves_caption.setVisible(show and th is not None)
        pp.reveal_box.setVisible(not demo)
        pp.reveal_hint.setVisible(not demo and self.settings["reveal"])
        pp.reveal_box.blockSignals(True)
        pp.reveal_box.setChecked(self.settings["reveal"])
        pp.reveal_box.blockSignals(False)
        pp.pause_button.setVisible(demo)
        pp.fit_labels()
