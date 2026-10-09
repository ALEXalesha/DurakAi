"""Стол: свои карты веером внизу, соперники рубашками с числом, колода с козырем, отбой,
пары «атака / защита» в центре. Ход - нажатие на карту или перетаскивание на стол.

Каждой карте в каждом состоянии отводится место. После хода места сравниваются, и карты,
у которых место поменялось, летят из старого в новое (anim_ms). Закрытые карты соперника
не имеют своих мест в веере - только центр веера: иначе по тому, из какого места веера
вылетела рубашка, можно было бы угадать порядок карт в чужой руке.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from aikit import theme as aitheme
from game.core import cards as C
from game.core.durak import ATTACK, DEFEND, TRANSFER
from game.ui import cardpaint as cp


def sort_key(c, trump):
    """Порядок своей руки: некозырные по мастям, козыри справа; внутри - по достоинству."""
    s = C.suit(c)
    return (1 if s == trump else 0, s, C.rank(c))


class Place:
    __slots__ = ("rect", "angle", "face", "z")

    def __init__(self, rect, angle=0.0, face=True, z=0):
        self.rect = rect
        self.angle = angle
        self.face = face
        self.z = z

    def same(self, other):
        return (other is not None and abs(self.rect.x() - other.rect.x()) < 0.5
                and abs(self.rect.y() - other.rect.y()) < 0.5 and abs(self.angle - other.angle) < 0.5)


class Flight:
    __slots__ = ("card", "src", "dst", "start", "dur")

    def __init__(self, card, src, dst, start, dur):
        self.card = card
        self.src = src
        self.dst = dst
        self.start = start
        self.dur = dur


class TableWidget(QWidget):
    moveChosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(QSize(620, 480))
        self.setMouseTracking(True)
        self.theme = "dark"
        self.lang = "ru"
        self.state = None
        self.viewer = 0
        self.legal = []
        self.reveal = False
        self.names = []
        self.badges = {}
        self.thinking = -1
        self.scores = {}
        self.anim_ms = 250
        self.places = {}
        self.deal_next = False        # следующая set_state - раздача: карты летят из колоды
        self.flights = []
        self.selected = -1
        self.hover = -1
        self.press = None
        self.drag = None
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # ---------- данные ----------

    def set_theme(self, name, lang):
        self.theme = name
        self.lang = lang
        self.update()

    def set_state(self, state, viewer, legal, reveal, names, thinking=-1, scores=None, animate=True):
        """state - полное состояние партии (окно его знает); закрытые карты рисуются рубашкой.
        legal - допустимые ходы человека или []. scores - {ход: оценка} для «Мыслей ИИ»."""
        old = self.places
        self.state = state
        self.viewer = viewer
        self.legal = list(legal)
        self.reveal = reveal
        self.names = list(names)
        self.thinking = thinking
        self.scores = dict(scores or {})
        if self.selected >= 0 and not any(m[1] == self.selected for m in self.legal):
            self.selected = -1
        self.places = self.compute_places()
        if self.deal_next:
            self.deal_next = False
            deck = Place(self.deck_rect(), 0, False, 1)
            old = {c: deck for c, pl in self.places.items() if pl.z >= 30}   # карты на руках
        if animate and self.anim_ms > 0 and old:
            now = time.monotonic()
            keep = [f for f in self.flights if now - f.start < f.dur]
            flying = {f.card for f in keep}
            stagger = 0.0
            for c, place in self.places.items():
                prev = old.get(c)
                if prev is None or place.same(prev) or c in flying:
                    continue
                keep.append(Flight(c, prev, place, now + stagger, self.anim_ms / 1000.0))
                stagger += 0.035
            self.flights = keep
            if self.flights:
                self.timer.start()
        else:
            self.flights = []
        self.update()

    def start_deal(self):
        """Новая партия: прошлые места забыты, розданные карты полетят из колоды."""
        self.places = {}
        self.deal_next = True

    def animating(self):
        now = time.monotonic()
        return any(now < f.start + f.dur for f in self.flights)

    def anim_left(self):
        """Секунд до конца последнего полёта (с учётом очереди карт), 0 - не летят."""
        now = time.monotonic()
        return max((f.start + f.dur - now for f in self.flights), default=0.0) if self.flights else 0.0

    def finish_animation(self):
        """Карты сразу на своих местах (вкладку спрятали - лететь некому смотреть)."""
        self.flights = []
        self.timer.stop()
        self.update()

    def _tick(self):
        if not self.animating():
            self.flights = []
            self.timer.stop()
        self.update()

    # ---------- геометрия ----------

    def card_size(self):
        h = max(60.0, min(self.height() * 0.19, self.width() * 0.105))
        return h * 0.68, h

    def seat_of(self, p):
        """Место игрока p на экране: 'bottom', 'top', 'left', 'right', 'tl', 'tr'."""
        n = self.state.n
        k = (p - self.viewer) % n
        if k == 0:
            return "bottom"
        if n == 2:
            return "top"
        if n == 3:
            return ("tl", "tr")[k - 1]
        return ("left", "top", "right")[k - 1]

    def seat_center(self, seat):
        W, H = self.width(), self.height()
        cw, ch = self.card_size()
        return {
            "bottom": QPointF(W / 2, H - ch * 0.5 - 30),
            "top": QPointF(W / 2, ch * 0.62 + 18),
            "tl": QPointF(W * 0.27, ch * 0.62 + 18),
            "tr": QPointF(W * 0.73, ch * 0.62 + 18),
            "left": QPointF(cw * 0.95, H * 0.42),
            "right": QPointF(W - cw * 0.95, H * 0.42),
        }[seat]

    def deck_rect(self):
        cw, ch = self.card_size()
        x = self.width() * 0.13 if self.state.n == 4 else cw * 0.5 + 10
        if self.state.n == 4:
            x = cw * 2.1
        return QRectF(x, self.height() * 0.42 - ch / 2, cw, ch)

    def discard_rect(self):
        cw, ch = self.card_size()
        x = self.width() - cw * 1.5 - 10
        if self.state.n == 4:
            x = self.width() - cw * 3.1
        return QRectF(x, self.height() * 0.42 - ch / 2, cw, ch)

    def table_area(self):
        cw, ch = self.card_size()
        d, r = self.deck_rect(), self.discard_rect()
        left = d.right() + cw * 0.8
        right = r.left() - cw * 0.4
        top = ch * 1.35 + 24
        bottom = self.height() - ch * 1.45
        return QRectF(left, top, max(cw * 3, right - left), max(ch * 1.2, bottom - top))

    def slot_rect(self, i, defense=False):
        """Место пары i: до трёх в ряд, ряд по центру стола; второй ряд - с четвёртой пары."""
        cw, ch = self.card_size()
        area = self.table_area()
        cols = 3
        gap_x = cw * 0.55
        gap_y = ch * 0.18
        n = max(len(self.state.table) if self.state is not None else 0, i + 1)
        rows = 1 if n <= cols else 2
        col, row = i % cols, i // cols
        in_row = min(cols, n - row * cols)
        row_w = in_row * cw + (in_row - 1) * gap_x + cw * 0.3
        x0 = area.center().x() - row_w / 2
        block_h = rows * ch + (rows - 1) * gap_y + ch * 0.22
        y0 = area.center().y() - block_h / 2
        x = x0 + col * (cw + gap_x)
        y = y0 + row * (ch + gap_y)
        if defense:
            x += cw * 0.3
            y += ch * 0.22
        return QRectF(x, y, cw, ch)

    def hand_rects(self, cards, center, face, vertical=False, raise_cards=()):
        cw, ch = self.card_size()
        n = len(cards)
        if n == 0:
            return {}
        span = (self.width() * (0.62 if not vertical else 0.0)) if not vertical else self.height() * 0.36
        if not face:
            span = cw * 2.4 if not vertical else ch * 1.6
        step = min(cw * (0.72 if face else 0.22), (span - cw) / max(n - 1, 1)) if n > 1 else 0
        out = {}
        total = step * (n - 1)
        for i, c in enumerate(cards):
            if vertical:
                y = center.y() - total / 2 + i * step - ch / 2
                rect = QRectF(center.x() - cw / 2, y, cw, ch)
            else:
                x = center.x() - total / 2 + i * step - cw / 2
                lift = ch * 0.14 if c in raise_cards else 0
                rect = QRectF(x, center.y() - ch / 2 - lift, cw, ch)
            out[c] = (rect, i)
        return out

    def playable(self):
        return {m[1] for m in self.legal if m[1] >= 0}

    def compute_places(self):
        s = self.state
        if s is None:
            return {}
        places = {}
        cw, ch = self.card_size()
        # стол
        for i, (a, d) in enumerate(s.table):
            places[a] = Place(self.slot_rect(i), 0, True, 10 + 2 * i)
            if d >= 0:
                places[d] = Place(self.slot_rect(i, True), 0, True, 11 + 2 * i)
        # колода и козырь
        deck_r = self.deck_rect()
        for c in s.deck:
            if c == s.trump_card:
                r = QRectF(deck_r.center().x() - cw * 0.15, deck_r.center().y() - ch / 2, cw, ch)
                places[c] = Place(r, 90.0, True, 0)
            else:
                places[c] = Place(deck_r, 0, False, 1)
        # отбой
        disc = self.discard_rect()
        for c in C.cards_of(s.discard):
            places[c] = Place(disc, 0, False, 1)
        # руки
        for p in range(s.n):
            seat = self.seat_of(p)
            center = self.seat_center(seat)
            mine = p == self.viewer and (s.n and True)
            face = self.reveal or (mine and self.viewer >= 0)
            cards = sorted(C.cards_of(s.hands[p]), key=lambda c: sort_key(c, s.trump))
            if face:
                vertical = seat in ("left", "right")
                raise_cards = self.playable() | ({self.selected} if self.selected >= 0 else set()) \
                    if mine else ()
                rects = self.hand_rects(cards, center, True, vertical and not mine, raise_cards)
                for c in cards:
                    rect, i = rects[c]
                    places[c] = Place(rect, 0, True, 30 + i)
            else:
                r = QRectF(center.x() - cw / 2, center.y() - ch / 2, cw, ch)
                for c in cards:
                    places[c] = Place(r, 0, False, 30)
        return places

    # ---------- рисование ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = cp.cloth(self.theme)
        pal = aitheme.palette(self.theme)
        p.setPen(QPen(QColor(col["cloth_edge"]), 2))
        p.setBrush(QColor(col["cloth"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 18, 18)
        s = self.state
        if s is None:
            p.end()
            return
        cw, ch = self.card_size()
        now = time.monotonic()
        flying = {f.card for f in self.flights if now < f.start + f.dur}
        font = QFont("Segoe UI")
        font.setPixelSize(max(11, int(ch * 0.13)))
        p.setFont(font)
        # места на столе
        area = self.table_area()
        p.setPen(QPen(QColor(col["slot"]), 1.5, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(area.adjusted(-8, -8, 8, 8), 14, 14)
        # колода
        deck_r = self.deck_rect()
        if s.deck:
            if s.trump_card in s.deck and s.trump_card not in flying:
                self._draw_place(p, s.trump_card, self.places[s.trump_card])
            if len(s.deck) > 1:
                for k in range(min(3, len(s.deck) - 1)):
                    cp.draw_back(p, deck_r.translated(-k * 1.5, -k * 1.5), self.theme)
        else:
            self._draw_suit_mark(p, deck_r, s.trump)
        self._text(p, QRectF(deck_r.left() - cw * 0.5, deck_r.bottom() + 4, cw * 2.2, 22),
                   str(len(s.deck)) if s.deck else "0", pal["text"], Qt.AlignmentFlag.AlignLeft)
        # отбой
        disc = self.discard_rect()
        nd = s.discard.bit_count()
        if nd:
            for k in range(min(4, max(1, nd // 6))):
                p.save()
                p.translate(disc.center())
                p.rotate((k * 37) % 23 - 11)
                cp.draw_back(p, QRectF(-cw / 2, -ch / 2, cw, ch), self.theme)
                p.restore()
        else:
            p.setPen(QPen(QColor(col["slot"]), 1.5, Qt.PenStyle.DashLine))
            p.drawRoundedRect(disc, 8, 8)
        self._text(p, QRectF(disc.left() - cw * 0.3, disc.bottom() + 4, cw * 1.6, 22), str(nd),
                   pal["text"], Qt.AlignmentFlag.AlignCenter)
        # соперники и подписи
        for q in range(s.n):
            self._draw_seat(p, q, flying)
        # стол
        target_slots = self._target_slots()
        for i, (a, d) in enumerate(s.table):
            if a not in flying:
                self._draw_place(p, a, self.places[a], glow=i in target_slots)
            if d >= 0 and d not in flying:
                self._draw_place(p, d, self.places[d])
        # полёты
        for f in sorted(self.flights, key=lambda f: f.dst.z):
            if now < f.start:
                self._draw_place(p, f.card, f.src)
                continue
            if now >= f.start + f.dur:
                continue
            t = (now - f.start) / f.dur
            t = 1 - (1 - t) ** 3
            r = QRectF(f.src.rect.x() + (f.dst.rect.x() - f.src.rect.x()) * t,
                       f.src.rect.y() + (f.dst.rect.y() - f.src.rect.y()) * t, cw, ch)
            ang = f.src.angle + (f.dst.angle - f.src.angle) * t
            self._draw_place(p, f.card, Place(r, ang, f.src.face if t < 0.5 else f.dst.face))
        # перетаскиваемая карта
        if self.drag is not None:
            c, pos = self.drag
            r = QRectF(pos.x() - cw / 2, pos.y() - ch / 2, cw, ch)
            cp.draw_face(p, r, c, self.theme, self.lang, glow=True, trump=C.suit(c) == s.trump)
        p.end()

    def _draw_place(self, p, c, place, glow=False, dim=False, badge=None):
        p.save()
        r = place.rect
        if place.angle:
            p.translate(r.center())
            p.rotate(place.angle)
            r = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        cp.draw_card(p, r, c, place.face, self.theme, self.lang, glow=glow, dim=dim,
                     trump=place.face and self.state is not None and C.suit(c) == self.state.trump) \
            if place.face else cp.draw_back(p, r, self.theme)
        if badge is not None:
            value = max(-1.0, min(1.0, badge))
            rgb = aitheme.heat(value, self.theme)
            br = QRectF(r.center().x() - r.width() * 0.42, r.top() - r.height() * 0.2, r.width() * 0.84,
                        r.height() * 0.17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(*rgb))
            p.drawRoundedRect(br, 5, 5)
            f = QFont("Segoe UI")
            f.setPixelSize(max(9, int(br.height() * 0.7)))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(aitheme.palette(self.theme)["text"]))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, f"{value:+.2f}")
        p.restore()

    def _draw_seat(self, p, q, flying):
        s = self.state
        pal = aitheme.palette(self.theme)
        cw, ch = self.card_size()
        seat = self.seat_of(q)
        center = self.seat_center(seat)
        mine = q == self.viewer
        cards = sorted(C.cards_of(s.hands[q]), key=lambda c: sort_key(c, s.trump))
        face = self.reveal or mine
        playable = self.playable() if mine else set()
        if face:
            for c in cards:
                if c in flying or c not in self.places:
                    continue
                if self.drag is not None and self.drag[0] == c:
                    continue
                badge = None
                if mine and self.scores:
                    vals = [v for m, v in self.scores.items() if m[1] == c]
                    badge = max(vals) if vals else None
                self._draw_place(p, c, self.places[c], glow=c in playable or c == self.selected,
                                 dim=mine and bool(self.legal) and c not in playable, badge=badge)
        else:
            n = len(cards)
            vertical = seat in ("left", "right")
            shown = min(n, 8)
            step = cw * 0.18
            for k in range(shown):
                off = (k - (shown - 1) / 2) * step
                r = QRectF(center.x() - cw / 2 + (0 if vertical else off),
                           center.y() - ch / 2 + (off if vertical else 0), cw, ch)
                cp.draw_back(p, r, self.theme)
            if n:
                badge = QRectF(center.x() - 16, center.y() - 13, 32, 26)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(badge, 8, 8)
                self._text(p, badge, str(n), "#ffffff", Qt.AlignmentFlag.AlignCenter, bold=True)
        # подпись: имя и роль
        name = self.names[q] if q < len(self.names) else str(q)
        role = self.badges.get(q, "")
        text = name + (f" · {role}" if role else "") + (" …" if q == self.thinking else "")
        if seat == "bottom":
            r = QRectF(center.x() - 200, self.height() - 24, 400, 22)
        elif seat in ("left", "right"):
            r = QRectF(center.x() - cw, center.y() + ch * 0.75 + 4, cw * 2, 40)
        else:
            r = QRectF(center.x() - 160, 2, 320, 20)
        color = pal["warn"] if q == s.turn and not s.over else pal["text"]
        if s.over and s.fool == q:
            color = pal["bad"]
        self._text(p, r, text, color, Qt.AlignmentFlag.AlignCenter, bold=q == s.turn)

    def _draw_suit_mark(self, p, rect, suit):
        col = cp.cloth(self.theme)
        p.setPen(QPen(QColor(col["slot"]), 1.5, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 8, 8)
        cp.draw_suit(p, suit, rect.center().x(), rect.center().y(), rect.height() * 0.4,
                     cp.suit_color(suit))

    def _text(self, p, rect, text, color, align, bold=False):
        f = p.font()
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, text)

    # ---------- мышь ----------

    def _candidates(self, c):
        return [m for m in self.legal if m[1] == c]

    def _target_slots(self):
        if self.selected < 0:
            return set()
        return {m[2] for m in self._candidates(self.selected) if m[0] == DEFEND}

    def card_at(self, pos):
        """Своя карта под точкой (верхняя в веере)."""
        s = self.state
        if s is None or self.viewer < 0:
            return -1
        best = None
        for c in C.cards_of(s.hands[self.viewer]):
            pl = self.places.get(c)
            if pl and pl.face and pl.rect.contains(pos):
                if best is None or pl.z > best[0]:
                    best = (pl.z, c)
        return best[1] if best else -1

    def slot_at(self, pos):
        s = self.state
        if s is None:
            return -1
        for i, (a, d) in enumerate(s.table):
            if self.slot_rect(i).united(self.slot_rect(i, True)).contains(pos):
                return i
        return -1

    def on_table(self, pos):
        return self.table_area().adjusted(-20, -20, 20, 20).contains(pos)

    def choose(self, c, slot=-1, table=False):
        """Ход картой c: на место slot (бить) или на стол (ход, подкидывание, перевод).
        Возвращает ход или None. Если вариантов несколько - карта выбирается и ждёт цели."""
        cands = self._candidates(c)
        if not cands:
            return None
        if slot >= 0:
            for m in cands:
                if m[0] == DEFEND and m[2] == slot:
                    return m
        if table:
            for m in cands:
                if m[0] in (ATTACK, TRANSFER):
                    return m
            defends = [m for m in cands if m[0] == DEFEND]
            if len(defends) == 1:
                return defends[0]
        if len(cands) == 1 and slot < 0:
            return cands[0]
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.legal:
            return
        pos = event.position()
        c = self.card_at(pos)
        if c >= 0 and self._candidates(c):
            self.press = (c, pos)
            return
        if self.selected >= 0:
            slot = self.slot_at(pos)
            m = self.choose(self.selected, slot, table=slot < 0 and self.on_table(pos))
            if m is not None:
                self.selected = -1
                self.moveChosen.emit(m)
            else:
                self.selected = -1
                self.places = self.compute_places()
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self.press is not None:
            c, start = self.press
            if self.drag is not None or (pos - start).manhattanLength() > 8:
                self.drag = (c, pos)
                self.update()

    def mouseReleaseEvent(self, event):
        if self.press is None:
            return
        c, _ = self.press
        self.press = None
        pos = event.position()
        if self.drag is not None:
            self.drag = None
            slot = self.slot_at(pos)
            m = self.choose(c, slot, table=self.on_table(pos))
            if m is not None:
                self.selected = -1
                self.moveChosen.emit(m)
            self.update()
            return
        m = self.choose(c)
        if m is not None:
            self.selected = -1
            self.moveChosen.emit(m)
        else:
            self.selected = c
            self.places = self.compute_places()
            self.update()

    def click_card(self, c):
        """Нажатие на свою карту без мыши - для проверок и клавиатуры."""
        m = self.choose(c)
        if m is not None:
            self.selected = -1
            self.moveChosen.emit(m)
            return m
        if self._candidates(c):
            self.selected = c
            self.places = self.compute_places()
            self.update()
        return None

    def click_slot(self, slot):
        if self.selected < 0:
            return None
        m = self.choose(self.selected, slot, table=slot < 0)
        if m is not None:
            self.selected = -1
            self.moveChosen.emit(m)
        return m


__all__ = ["TableWidget", "sort_key", "math"]
