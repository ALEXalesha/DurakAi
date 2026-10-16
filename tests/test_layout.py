"""Законы раскладки стола (Qt offscreen): подписи игроков, колоды и бито всегда видны.

Снимки автора 16.10 (1.0.2): веер боковых ИИ закрывал их подпись «ИИ 3 · ходит …», а стопку
«бито» с числом 20 у правого края принимали за руку вышедшего «ИИ 4». Закон: прямоугольник
каждой подписи (по метрикам шрифта) лежит в окне стола, не задевает ни одной карты (руки,
колода, бито, стол) и другие подписи - на разных размерах окна, вдвоём-вчетвером, с рукой
до 30 карт, с открытыми и закрытыми картами соперников.
"""
import random

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from game.core import cards as C
from game.core.durak import Rules, State
from game.ui.i18n import EN, RU
from game.ui.table import TableWidget

SIZES = [(620, 480), (700, 560), (908, 772), (1200, 700), (1600, 1000), (2200, 1300),
         (620, 900), (1400, 480), (3500, 2100)]     # последний - окно во весь экран 4K


@pytest.fixture(scope="module")
def table():
    QApplication.instance() or QApplication([])
    t = TableWidget()
    t.anim_ms = 0
    yield t
    t.deleteLater()


def make_state(sizes, deck_n, pairs, seed=0):
    """Партия с заданным числом карт на руках и в колоде; pairs - пар на столе (из отбоя)."""
    rnd = random.Random(seed)
    cards = list(range(36))
    rnd.shuffle(cards)
    hands, k = [], 0
    for n in sizes:
        hands.append(C.mask(cards[k:k + n]))
        k += n
    deck = cards[k:k + deck_n]
    k += deck_n
    rest = cards[k:]
    trump = C.suit(deck[0]) if deck else C.suit(cards[0])
    s = State.from_parts(Rules(players=len(sizes)), hands, deck, first=0,
                         trump=None if deck else trump)
    for i in range(min(pairs, len(rest) // 2)):
        a, d = rest[2 * i], rest[2 * i + 1]
        s.table.append([a, d if i % 2 == 0 else -1])
        s.discard &= ~C.mask([a, d])
        if i % 2:
            s.discard |= C.mask([d])
    return s


def show(t, s, size, reveal, lang="ru", over=False, turn=None):
    T = RU if lang == "ru" else EN
    t.resize(*size)
    t.lang = lang
    names = [T["you"]] + [T["ai_n"].format(n=q + 1) for q in range(1, s.n)]
    # самые длинные подписи: роль у всех и «думает» у каждого по очереди
    roles = [T["defends"], T["attacks"], T["out"], T["fool_badge"]]
    t.badges = {q: roles[q % len(roles)] for q in range(s.n)}
    if over:
        s.fool = 1
        s.turn = -1
    elif turn is not None:
        s.turn = turn                      # жирная подпись - у того, чей ход
    t.set_state(s, 0, [], reveal, names, thinking=s.n - 1, animate=False)


def hand_cases():
    """(руки по игрокам, колода, пар на столе) - от раздачи до руки в 30 карт."""
    out = []
    for n in (2, 3, 4):
        out.append(([6] * n, 36 - 6 * n, 0))                  # раздача
        out.append(([6] * n, 36 - 6 * n, 3))
        out.append(([1] + [1] * (n - 1), 0, 0))               # конец: по карте
        out.append(([2] + [8] * (n - 1), 0, 6))
        out.append(([3] + [0] * (n - 2) + [36 - 3 - 3 * (n - 2) - 12], 0, 0))
        big = 30 - (n - 2)
        out.append(([1] * (n - 1) + [big], 36 - big - (n - 1), 0))   # 30 карт у последнего ИИ
        out.append(([big] + [1] * (n - 1), 36 - big - (n - 1), 0))   # 30 карт у вас
        k = (35 - 6) // (n - 1) if n > 2 else 15
        out.append(([1] + [k] * (n - 1), 35 - k * (n - 1), 0))   # у всех соперников много карт
        if n == 4:
            out.append(([1, 30, 1, 1], 3, 0))                  # 30 карт у левого ИИ
            out.append(([1, 1, 30, 1], 3, 0))                  # у верхнего
            out.append(([0, 0, 20, 0], 0, 0))                  # снимок автора: бито 16, все вышли
    return out


def problems(t):
    """Все нарушения закона в текущем кадре: список строк."""
    bad = []
    frame = QRectF(0, 0, t.width(), t.height())
    labels = t.label_items()
    boxes = t.card_boxes()
    area = t.table_area().adjusted(-8, -8, 8, 8)
    for i, lab in enumerate(labels):
        r = lab.rect
        if not lab.text or r.width() <= 0:
            bad.append(f"{lab.key}: пустая подпись")
            continue
        if not frame.contains(r):
            bad.append(f"{lab.key} «{lab.text}» за краем стола")
        for owner, box in boxes:
            if r.intersects(box):
                bad.append(f"{lab.key} «{lab.text}» задевает карту {owner}")
                break
        if r.intersects(area):
            bad.append(f"{lab.key} «{lab.text}» заходит на стол")
        for other in labels[i + 1:]:
            if r.intersects(other.rect):
                bad.append(f"{lab.key} «{lab.text}» задевает подпись {other.key} «{other.text}»")
    return bad


def sweep(t, sizes=SIZES, check=None):
    check = check or problems
    found = []
    for hands, deck_n, pairs in hand_cases():
        n = len(hands)
        over = not deck_n and pairs == 0
        for size in sizes:
            for reveal in (False, True):
                for lang in ("ru", "en"):
                    for turn in ([None] if over else range(n)):
                        s = make_state(hands, deck_n, pairs, seed=len(found) + n)
                        show(t, s, size, reveal, lang, over=over, turn=turn)
                        for b in check(t):
                            found.append(f"{size} {hands} колода {deck_n} стол {pairs} "
                                         f"{'открыто' if reveal else 'закрыто'} {lang} ход {turn}: {b}")
    return found


def card_problems(t):
    """Карты разных хозяев (руки, колода, бито, стол) не налезают друг на друга и не уходят за край."""
    bad = []
    frame = QRectF(0, 0, t.width(), t.height())
    boxes = t.card_boxes()
    for i, (o1, r1) in enumerate(boxes):
        if not frame.contains(r1):
            bad.append(f"карта {o1} за краем стола")
        for o2, r2 in boxes[i + 1:]:
            if o1 != o2 and r1.intersects(r2):
                bad.append(f"карты {o1} и {o2} налезают друг на друга")
    return sorted(set(bad))


def test_labels_never_covered(table):
    found = sweep(table)
    assert not found, f"{len(found)} нарушений, первые:" + chr(10) + chr(10).join(found[:15])


def test_hands_of_different_players_never_overlap(table):
    """Втроём с открытыми картами веера двух верхних соперников налезали друг на друга и
    уходили за край (найдено этим законом 16.10)."""
    found = sweep(table, check=card_problems)
    assert not found, f"{len(found)} нарушений, первые:" + chr(10) + chr(10).join(found[:15])


def _labels(t):
    return {lab.key: lab for lab in t.label_items()}


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_deck_and_discard_are_signed_under_their_piles(table, lang):
    """Снимок автора: стопка рубашкой с числом 20 у правого края - это бито, а её принимали
    за руку вышедшего ИИ. Теперь у стопок подписи «Колода N» и «Бито N» прямо под ними."""
    T = RU if lang == "ru" else EN
    s = make_state([2, 0, 6, 0], 0, 0)       # вчетвером, двое вышли, колода пуста, бито 28
    show(table, s, (908, 772), False, lang)
    labs = _labels(table)
    assert labs["deck"].text == T["deck_pile"].format(n=0)
    assert labs["discard"].text == T["discard_pile"].format(n=28)
    assert labs["discard"].text.split()[0] in ("Бито", "Discard")
    for key, pile in (("deck", table.deck_rect()), ("discard", table.discard_rect())):
        r = labs[key].rect
        assert r.top() >= pile.bottom(), key
        assert r.left() <= pile.center().x() <= r.right(), key
    s = make_state([6, 6, 6, 6], 12, 0)
    show(table, s, (908, 772), False, lang)
    labs = _labels(table)
    assert labs["deck"].text == T["deck_pile"].format(n=12)
    assert labs["discard"].text == T["discard_pile"].format(n=0)


def test_side_label_sits_above_a_long_fan(table):
    """Снимок автора: веер левого ИИ закрывал «ИИ 2 · ходит …». Подпись бокового игрока над
    его веером при любом числе карт, открытых и закрытых."""
    for reveal in (False, True):
        for n in (1, 6, 12, 30):
            s = make_state([1, n, 1, 1], 33 - n, 0)
            show(table, s, (700, 560), reveal, turn=1)
            fan = [r for o, r in table.card_boxes() if o == 1]
            lab = _labels(table)[1]
            assert lab.text.startswith("ИИ 2")
            assert lab.rect.bottom() <= min(r.top() for r in fan), (reveal, n)
            assert lab.rect.left() >= 0


def test_labels_are_painted_where_they_are_laid_out(table):
    """Подписи рисуются по тем же прямоугольникам, что проверяет закон: в каждом есть
    пиксели текста, а не только сукно."""
    from PySide6.QtGui import QColor, QImage
    s = make_state([6, 6, 6, 6], 12, 2)
    show(table, s, (908, 772), True, turn=1)
    img = QImage(table.size(), QImage.Format.Format_ARGB32)
    img.fill(0)
    table.render(img)
    from game.ui import cardpaint as cp
    cloth = QColor(cp.cloth(table.theme)["cloth"])
    for lab in table.label_items():
        r = lab.rect.toRect()
        differ = 0
        for x in range(r.left(), r.right(), 2):
            for y in range(r.top(), r.bottom(), 2):
                c = QColor(img.pixel(x, y))
                if abs(c.red() - cloth.red()) + abs(c.green() - cloth.green()) + abs(c.blue() - cloth.blue()) > 60:
                    differ += 1
        assert differ > 5, f"подпись {lab.key} «{lab.text}» не нарисована"


@pytest.mark.parametrize("players,size", [(4, (980, 700)), (3, (980, 700)), (4, (2560, 1400)),
                                          (2, (1280, 800))])
def test_real_games_in_the_window_keep_labels_clear(tmp_path, players, size):
    """Настоящие партии «ИИ против ИИ» в окне игры: после каждого хода закон раскладки цел."""
    import time

    from aikit.host import make_window
    from game import APP_NAME, GAME_INFO, create_widget
    app = QApplication.instance() or QApplication([])
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(*size)
    w.show()
    g = w.game
    g.change("anim_ms", 0)
    g.change("delay_ms", 0)
    t = g.play.table
    found, frames = [], [0]
    real = t.set_state

    def checked(*a, **k):
        real(*a, **k)
        frames[0] += 1
        found.extend(f"ход {frames[0]}: {b}" for b in problems(t) + card_problems(t))

    t.set_state = checked
    try:
        g.change("mode", "demo")
        g.change("level", "novice")
        g.change("players", players)
        for seed in (3, 4):
            g.start_game(seed=seed)
            end = time.time() + 60
            while not g.session.over and time.time() < end:
                app.processEvents()
                time.sleep(0.002)
            assert g.session.over
        assert frames[0] > 20
        assert not found, f"{len(found)} нарушений, первые:" + chr(10) + chr(10).join(found[:15])
    finally:
        g.change("mode", "play")
        g.shutdown()
        w.close()
        w.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_taking_line_is_a_separate_sentence(tmp_path):
    """Кадр README 1.0.3: «ИИ 2 берёт - можно подкинуть Соперники: сильный» - два предложения
    слиплись без точки."""
    from aikit.host import make_window
    from game import APP_NAME, GAME_INFO, create_widget
    from game.ui.session import Session
    QApplication.instance() or QApplication([])
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    g = w.game
    try:
        g.change("delay_ms", 0)
        s = Session(players=2, level="novice")
        s.state = make_state([6, 6], 24, 1)
        s.state.attacker, s.state.defender, s.state.turn = 0, 1, 0
        s.state.taking = True
        g.session = s
        g.stack.setCurrentWidget(g.play)
        g._invalidate()
        g.after_change()
        text = g.play.substatus.text()
        assert text.startswith(RU["taking"].format(name=RU["ai_n"].format(n=1)) + ". "), text
    finally:
        g.shutdown()
        w.close()
        w.deleteLater()
