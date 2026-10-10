"""Окно без экрана (Qt offscreen): стол, ходы мышью и кнопками, ИИ в потоке, темы, языки,
статистика, остановка за 2 секунды. Ожидания - с тайм-аутом; мышь - собранными событиями,
настоящий курсор не трогается."""
import json
import os
import time

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel

QWIDGETSIZE_MAX = (1 << 24) - 1

from aikit.widgets import Combo
from game import APP_NAME, GAME_INFO, create_widget
from game.ai.agents import NoviceAgent
from game.core import cards as C
from game.core.durak import DEFEND, MOVE_PASS, MOVE_TAKE, Rules, State, TRANSFER
from game.core.observation import Observation
from game.ui.i18n import EN, RU
from game.ui.session import Session


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    g = w.game
    g.change("anim_ms", 0)
    g.change("delay_ms", 0)
    yield w
    g.shutdown()
    w.close()
    # окно разрушается сразу и в потоке окна, а не когда-нибудь сборщиком мусора,
    # возможно в потоке ИИ
    w.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait(app, cond, limit=30.0):
    end = time.time() + limit
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.002)
    return cond()


def play_out(app, g, bot=None, limit=120.0):
    bot = bot or NoviceAgent()
    end = time.time() + limit
    while not g.session.over:
        assert time.time() < end, "партия не кончилась вовремя"
        s = g.session
        if s.human_turn():
            g.on_move_chosen(bot.choose(s.obs(s.human)))
        assert wait(app, lambda: g.session.over or g.session.human_turn(), 30), "ИИ не ответил"


def test_translations_complete():
    assert set(RU) == set(EN)


def test_game_vs_ai_to_the_end_records_stats(app, win):
    g = win.game
    g.change("level", "novice")
    g.start_game(seed=3)
    assert g.current_page() == "play"
    play_out(app, g)
    e = g.ctx.stats.entry("2p/novice")
    assert e["games"] == 1 and e["wins"] + e["losses"] + e["draws"] == 1
    assert g.play.status.text()


def test_peeking_keeps_game_out_of_stats(app, win):
    g = win.game
    g.change("level", "novice")
    g.start_game(seed=4)
    g.change("reveal", True)
    assert g.session.peeked
    play_out(app, g)
    assert g.ctx.stats.entry("2p/novice")["games"] == 0
    g.change("reveal", False)


def test_three_and_four_players_with_medium(app, win):
    g = win.game
    for n in (3, 4):
        g.change("players", n)
        g.change("level", "medium")
        g.start_game(seed=10 + n)
        play_out(app, g)
        assert g.ctx.stats.entry(f"{n}p/medium")["games"] == 1


def test_demo_mode_plays_itself(app, win):
    g = win.game
    g.change("mode", "demo")
    g.change("level", "novice")
    g.start_game(seed=2)
    assert wait(app, lambda: g.session.over, 60)
    assert g.play.table.reveal
    g.change("mode", "play")


def test_ai_receives_only_observation(app, win, monkeypatch):
    g = win.game
    seen = []
    orig_move, orig_th = g.ai.request_move, g.ai.request_thoughts

    def spy_move(token, obs, level, seed):
        seen.append(("move", obs))
        return orig_move(token, obs, level, seed)

    def spy_th(token, obs, seed):
        seen.append(("thoughts", obs))
        return orig_th(token, obs, seed)
    monkeypatch.setattr(g.ai, "request_move", spy_move)
    monkeypatch.setattr(g.ai, "request_thoughts", spy_th)
    g.change("level", "medium")
    g.change("show_thoughts", True)
    g.start_game(seed=6)
    play_out(app, g)
    g.change("show_thoughts", False)
    assert seen
    for kind, obs in seen:
        assert isinstance(obs, Observation)
        if kind == "thoughts":
            assert obs.player == g.session.human      # в игре думаем только за человека
        else:
            assert obs.player != g.session.human


def test_thoughts_show_grid_and_scores(app, win):
    g = win.game
    g.change("level", "novice")
    g.change("show_thoughts", True)
    g.start_game(seed=8)
    bot = NoviceAgent()
    for _ in range(200):
        s = g.session
        if s.over:
            break
        if s.human_turn() and len(s.legal()) > 1:
            # свежие мысли - к этому ходу (на ходу ИИ на панели только ваш учёт карт)
            assert wait(app, lambda: g.thoughts is not None and g.thoughts_token == g.token, 20)
            break
        if s.human_turn():
            g.on_move_chosen(bot.choose(s.obs(s.human)))
        wait(app, lambda: g.session.over or g.session.human_turn(), 30)
    if g.thoughts is not None:
        assert g.play.grid.blocks and g.play.moves.count() == len(g.session.legal())
        assert g.play.table.scores
    g.change("show_thoughts", False)


def human_state(g, hands, deck, first=0, transfer=False):
    """Ручная раздача в окне: место 0 - человек."""
    s = Session(players=len(hands), level="novice", transfer=transfer)
    s.state = State.from_parts(Rules(players=len(hands), transfer=transfer),
                               [C.mask(C.parse(x) for x in h) for h in hands],
                               [C.parse(x) for x in deck], first=first)
    g.session = s
    g.stack.setCurrentWidget(g.play)
    g._invalidate()
    g.after_change()
    return s


def test_click_card_plays_and_buttons_follow_legal_moves(app, win):
    g = win.game
    s = human_state(g, [["7♠", "7♣", "Q♦"], ["8♠", "A♣", "K♦", "9♦"]], ["6♥", "10♣", "J♣"])
    t = g.play.table
    assert t.legal and not g.play.pass_button.isVisible() or not g.play.pass_button.isVisibleTo(g.play)
    t.click_card(C.parse("7♠"))
    assert s.state.table[0][0] == C.parse("7♠")
    assert wait(app, lambda: s.human_turn(), 10)
    # ИИ отбился или взял - в любом случае у человека теперь подкидывание
    assert MOVE_PASS in s.legal()
    assert g.play.pass_button.isVisibleTo(g.play)
    g.on_pass()


def test_defend_with_two_targets_needs_a_slot(app, win):
    g = win.game
    # 0 - человек, отбивается после перевода: на столе 7♠ и 7♦, у человека 9♠ и 9♦ и козырь
    s = human_state(g, [["9♠", "9♦", "8♥", "K♣"], ["7♠"], ["7♦", "A♣", "J♣"]],
                    ["6♥", "10♣"], first=1, transfer=True)
    assert wait(app, lambda: s.human_turn(), 10)
    assert s.state.phase() == "defend"
    undefended = [i for i, (a, d) in enumerate(s.state.table) if d < 0]
    t = g.play.table
    assert len(undefended) == 2                      # 7♠ и переведённая 7♦
    trump_cands = [m for m in s.legal() if m[1] == C.parse("8♥")]
    assert len({m[2] for m in trump_cands}) == 2
    assert t.click_card(C.parse("8♥")) is None and t.selected == C.parse("8♥")
    m = t.click_slot(undefended[-1])
    assert m is not None and m[0] == DEFEND and m[2] == undefended[-1]
    assert s.state.table[undefended[-1]][1] == C.parse("8♥")


def test_transfer_by_dropping_on_table(app, win):
    g = win.game
    # 7♥ - козырь: им можно и побить 7♠, и перевести; бросок мимо карты на стол - перевод
    s = human_state(g, [["7♥", "A♣", "K♣"], ["9♦", "8♠", "J♣"], ["7♠"]],
                    ["6♥", "10♣"], first=2, transfer=True)
    assert wait(app, lambda: s.human_turn(), 10)
    assert any(m[0] == TRANSFER for m in s.legal())
    t = g.play.table
    c = C.parse("7♥")
    assert {m[0] for m in s.legal() if m[1] == c} == {DEFEND, TRANSFER}
    start = t.places[c].rect.center()
    end = t.table_area().center() + QPointF(0, t.card_size()[1])

    def ev(kind, pos, buttons):
        return QMouseEvent(kind, pos, pos, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
    t.mousePressEvent(ev(QMouseEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton))
    t.mouseMoveEvent(ev(QMouseEvent.Type.MouseMove, (start + end) / 2, Qt.MouseButton.LeftButton))
    assert t.drag is not None
    t.mouseMoveEvent(ev(QMouseEvent.Type.MouseMove, end, Qt.MouseButton.LeftButton))
    t.mouseReleaseEvent(ev(QMouseEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton))
    assert s.state.attacker == 0 and s.state.defender == 1          # перевели на следующего
    assert any(a == c for a, _ in s.state.table)


def test_take_button(app, win):
    g = win.game
    s = human_state(g, [["9♠", "K♦"], ["A♠", "Q♣", "J♣"]], ["6♥", "10♣"], first=1)
    assert wait(app, lambda: s.human_turn() and s.state.phase() == "defend", 10)
    assert g.play.take_button.isVisibleTo(g.play)
    g.on_take()
    assert s.state.taking or not s.state.table


def test_hidden_cards_have_no_individual_places(app, win):
    """Закрытые карты соперника все в центре веера: по вылету нельзя угадать порядок руки."""
    g = win.game
    g.start_game(seed=1)
    t = g.play.table
    st = g.session.state
    rects = {(t.places[c].rect.x(), t.places[c].rect.y()) for c in C.cards_of(st.hands[1])}
    assert len(rects) == 1
    g.change("reveal", True)
    rects = {(t.places[c].rect.x(), t.places[c].rect.y()) for c in C.cards_of(st.hands[1])}
    assert len(rects) == st.hands[1].bit_count()
    g.change("reveal", False)


def test_animation_creates_flights(app, win):
    g = win.game
    g.change("anim_ms", 300)
    g.change("level", "novice")
    g.start_game(seed=9)
    s = g.session
    if not s.human_turn():
        assert wait(app, lambda: s.human_turn(), 10)
    m = next(m for m in s.legal() if m[1] >= 0)
    g.on_move_chosen(m)
    assert g.play.table.flights
    assert wait(app, lambda: not g.play.table.animating(), 3)
    g.change("anim_ms", 0)


def test_theme_and_language_on_the_fly(app, win):
    g = win.game
    g.start_game(seed=5)
    win.ctx.set_theme("light")
    assert g.play.table.theme == "light"
    img = g.play.table.grab().toImage()
    assert not img.isNull()
    win.ctx.set_lang("en")
    assert g.play.take_button.text() == "Take"
    assert "AI" in " ".join(g.names())
    win.ctx.set_lang("ru")
    win.ctx.set_theme("dark")
    assert g.play.take_button.text() == "Беру"


def test_wrapped_labels_have_no_height_cap_and_combos_draw_arrow(app, win):
    g = win.game
    g.start_game(seed=5)
    for w in g.findChildren(QLabel):
        if w.wordWrap():
            assert w.maximumHeight() == QWIDGETSIZE_MAX, w.text()
    combos = g.settings_page.findChildren(Combo)
    assert len(combos) >= 3


def test_shutdown_within_two_seconds_while_ai_thinks(app, win):
    g = win.game
    g.change("players", 4)
    g.change("level", "strong")
    g.change("mode", "demo")
    g.change("delay_ms", 0)
    g.start_game(seed=12)
    wait(app, lambda: g.ai.busy(), 5)
    t0 = time.time()
    ok = g.shutdown()
    assert time.time() - t0 < 2.5 and ok
    g.change("mode", "play")
    g.change("players", 2)


def test_window_remembers_size(app, tmp_path):
    from aikit.host import make_window
    root = str(tmp_path / "home2")
    w, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    w.resize(1111, 777)
    w.show()
    app.processEvents()
    w.close()
    app.processEvents()
    data = json.load(open(os.path.join(root, "window.json"), encoding="utf-8"))
    assert data.get("width") == 1111 or data.get("w") == 1111 or 1111 in data.values()


def test_settings_change_rules(app, win):
    g = win.game
    g.change("transfer", True)
    g.change("five", True)
    g.start_game(seed=3)
    assert g.session.rules.transfer and g.session.rules.first_bout_five
    g.change("transfer", False)
    g.change("five", False)


def test_first_rule_after_fool(app, win):
    g = win.game
    g.change("first_rule", "after_fool")
    g.last_fool = (1, 2)
    g.start_game(seed=3)
    assert g.session.state.attacker == 0
    g.last_fool = (0, 2)
    g.start_game(seed=3)
    assert g.session.state.attacker == 1
    g.change("first_rule", "lowest")


def test_take_move_constant():
    assert MOVE_TAKE[0] == 3


# --- жизнь во вкладке оболочки: сборщик мусора, pause() / resume() ---


def _gc_state():
    import gc
    return gc.get_freeze_count(), gc.isenabled(), gc.get_threshold()


def test_widget_leaves_garbage_collector_alone(app, tmp_path):
    """Сборщик мусора общий на весь процесс: игра во вкладке оболочки не должна ни
    замораживать объекты (gc.freeze навсегда оставил бы в памяти и объекты оболочки), ни
    выключать сборщик, ни менять его пороги. 0.9.0 звала gc.freeze() в __init__."""
    from aikit.host import make_window
    before = _gc_state()
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.show()
    g = w.game
    g.change("anim_ms", 0)
    g.change("delay_ms", 0)
    g.change("level", "novice")
    g.change("mode", "demo")
    g.start_game(seed=4)
    assert wait(app, lambda: len(g.session.moves) >= 6, 30)
    assert g.shutdown()
    w.close()
    assert _gc_state() == before


def test_game_code_never_touches_gc():
    """Закон на весь код игры, а не только на окно: ни одного gc.freeze / disable /
    set_threshold в game/ и aikit/."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = []
    for top in ("game", "aikit"):
        for folder, _, files in os.walk(os.path.join(root, top)):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(folder, name)
                tree = ast.parse(open(path, encoding="utf-8").read())
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Attribute) and node.attr in ("freeze", "unfreeze", "disable", "set_threshold")
                            and isinstance(node.value, ast.Name) and node.value.id == "gc"):
                        bad.append(f"{os.path.relpath(path, root)}:{node.lineno} gc.{node.attr}")
    assert not bad, bad


def _demo(g, level="novice", seed=9):
    g.change("mode", "demo")
    g.change("level", level)
    g.change("players", 3)
    g.start_game(seed=seed)


def test_pause_stops_everything_and_resume_continues(app, win):
    g = win.game
    g.change("anim_ms", 200)
    _demo(g)
    assert wait(app, lambda: len(g.session.moves) >= 4, 30)
    g.pause()
    g.pause()                                   # второй раз - ничего не ломает
    n = len(g.session.moves)
    assert not g.timer.isActive() and not g.play.table.timer.isActive()
    assert not g.play.table.flights
    end = time.time() + 0.8
    while time.time() < end:                    # таймеры и потоки за это время не ходят
        app.processEvents()
        time.sleep(0.005)
    assert len(g.session.moves) == n
    g.change("show_thoughts", True)             # перерисовка скрытой вкладки не будит ИИ
    g.ctx.set_lang("en")
    for _ in range(50):
        app.processEvents()
        time.sleep(0.005)
    assert len(g.session.moves) == n and not g.timer.isActive()
    g.ctx.set_lang("ru")
    g.change("show_thoughts", False)
    assert wait(app, lambda: not g.ai.busy(), 5)
    assert g.current_page() == "play"
    g.resume()
    g.resume()
    g.change("anim_ms", 0)
    assert wait(app, lambda: len(g.session.moves) >= n + 4, 30)   # партия пошла дальше
    g.change("mode", "play")
    g.change("players", 2)


def test_pause_while_ai_thinks_drops_its_answer(app, win):
    g = win.game
    _demo(g, level="strong", seed=13)
    assert wait(app, lambda: g.ai.busy(), 10)
    n = len(g.session.moves)
    g.pause()
    assert wait(app, lambda: not g.ai.busy(), 3)    # поиск остановлен флагом, не досчитывается
    end = time.time() + 0.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    assert len(g.session.moves) == n
    g.resume()
    assert wait(app, lambda: len(g.session.moves) > n, 30)
    assert g.shutdown()
    g.change("mode", "play")
    g.change("players", 2)


def test_pause_on_human_turn_keeps_the_position(app, win):
    g = win.game
    g.change("level", "novice")
    g.start_game(seed=5)
    assert wait(app, lambda: g.session.human_turn(), 30)
    before = (len(g.session.moves), g.session.state.turn)
    g.pause()
    for _ in range(20):
        app.processEvents()
    g.resume()
    assert (len(g.session.moves), g.session.state.turn) == before
    assert g.session.human_turn()
    play_out(app, g)


def test_resume_in_menu_does_not_start_a_game(app, win):
    g = win.game
    g.pause()
    g.resume()
    assert g.current_page() == "menu" and g.session is None


def test_finished_ai_threads_are_deleted(app, win):
    """Каждый запрос к ИИ - свой QThread. Кончившийся поток удаляется, а не копится
    дочерним объектом до закрытия окна (0.9.0: ~45 за партию вдвоём вместе с агентами)."""
    from PySide6.QtCore import QCoreApplication, QEvent, QThread
    g = win.game
    g.change("mode", "demo")
    g.change("level", "novice")
    g.start_game(seed=8)
    assert wait(app, lambda: g.session.over, 60)
    assert len(g.session.moves) > 20
    # список чистит сам сигнал finished, без вызова busy()
    assert wait(app, lambda: not g.ai.jobs, 5)
    for _ in range(5):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    import gc
    from game.ui.ai_thread import _Job
    gc.collect()
    assert not g.ai.findChildren(QThread)
    assert sum(isinstance(o, _Job) for o in gc.get_objects()) <= 1
    g.change("mode", "play")


def test_play_button_deals_a_new_hand_each_time(app, win):
    """Кнопки «Играть» и «Новая партия»: clicked(bool) не должен стать зерном. 0.9.0 звала
    start_game(False), и каждая партия с кнопки шла с одной и той же раздачей (зерно 0)."""
    g = win.game
    g.change("level", "novice")
    deals = set()
    for b in (g.menu.play_button, g.play.again_button, g.menu.play_button, g.play.again_button):
        g.show_page("menu")
        b.click()
        assert g.current_page() == "play"
        st_ = g.session.state
        assert g.session.seed is not False
        deals.add((tuple(st_.hands), st_.trump))
    assert len(deals) == 4


def test_hotkeys_do_nothing_off_the_table(app, win):
    """Пробел (Бито/Пас) и T (Беру) - только на столе: из меню, статистики и настроек они
    не ходят за человека в спрятанной партии."""
    g = win.game
    g.change("level", "novice")
    for seed in range(40):
        g.start_game(seed=seed)
        if wait(app, lambda: g.session.human_turn(), 30) and MOVE_TAKE in g.session.legal():
            break
    else:
        pytest.fail("нет раздачи, где человек отбивается")
    for page in ("menu", "stats", "settings"):
        g.show_page(page)
        n = len(g.session.moves)
        g.on_take()
        g.on_pass()
        for _ in range(20):
            app.processEvents()
        assert len(g.session.moves) == n, page
    g.show_page("play")
    g.on_take()
    assert len(g.session.moves) == n + 1


def test_deal_flies_from_the_deck_and_ai_waits_for_it(app, win):
    """Раздача анимирована (spec §5): каждая карта на руках летит из колоды, и первый ход
    ИИ не начинается, пока карты летят."""
    g = win.game
    g.change("anim_ms", 300)
    g.change("level", "novice")
    g.change("mode", "demo")
    g.change("players", 4)
    g.start_game(seed=21)
    t = g.play.table
    hand_cards = {c for c, pl in t.places.items() if pl.z >= 30}
    assert len(hand_cards) == 24
    assert {f.card for f in t.flights} == hand_cards
    deck = t.deck_rect()
    assert all(abs(f.src.rect.x() - deck.x()) < 0.5 for f in t.flights)
    left = t.anim_left()
    assert left > 0.3 + 0.035 * 20                # очередь карт учтена
    assert g.timer.remainingTime() >= (left - 0.1) * 1000
    assert wait(app, lambda: not t.animating(), 5)
    g.change("anim_ms", 0)
    g.change("mode", "play")
    g.change("players", 2)


def test_thread_that_ignores_stop_survives_widget_destruction(app):
    """Поток, не успевший остановиться за shutdown() (перегруженная машина), уходит в
    сироты: окно разрушается, а поток дорабатывает сам. Разрушение работающего QThread -
    это qFatal и падение всей программы; в 0.9.0 от этого спасал только gc.freeze, который
    не давал сборщику разрушить старые окна."""
    import gc
    import threading as th
    from PySide6.QtCore import QCoreApplication, QEvent
    from game.ui import ai_thread
    ctl = ai_thread.AiController()
    release = th.Event()
    ctl._start(1, "move", lambda stop: release.wait(5) and None)
    assert ctl.busy()
    assert ctl.shutdown(100) is False                 # не успел - и честно сказал
    assert not ctl.jobs and len(ai_thread._ORPHANS) == 1
    ctl.deleteLater()
    del ctl
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    release.set()
    assert wait(app, lambda: not ai_thread._ORPHANS, 5)


@pytest.mark.parametrize("mode", ["demo", "play"])
@pytest.mark.parametrize("level", ["novice", "medium", "strong"])
def test_thoughts_panel_is_never_empty(app, win, mode, level):
    """«Мысли ИИ» включены - на панели всегда есть текст: чей ход и что на сетке. В показе
    «ИИ против ИИ» видны сетка учёта и оценки ходов (у новичка - что он играет по правилам).
    В 1.0.0-кандидате панель в показе была пустой: ход ИИ приходил раньше мыслей, и они
    выбрасывались как устаревшие (17 из 17 у новичка)."""
    g = win.game
    g.change("mode", mode)
    g.change("level", level)
    g.change("players", 2)
    g.change("show_thoughts", True)
    unseen = []                    # ходы ИИ в показе, сделанные без мыслей к этой позиции
    orig_apply = g._apply

    def spy_apply(move):
        s = g.session
        if (mode == "demo" and s.ai_turn() and len(s.legal()) > 1
                and not (g.thoughts is not None and g.thoughts_token == g.token
                         and g.thoughts["player"] == s.state.turn)):
            unseen.append(move)
        orig_apply(move)
    g._apply = spy_apply
    g.start_game(seed=31)
    pp = g.play
    seen = {"grid": 0, "scores": 0, "novice": 0, "ai_turn_text": 0, "fresh_on_ai_turn": 0}
    texts = []
    bot = NoviceAgent()
    end = time.time() + 90
    while len(g.session.moves) < 10 and not g.session.over and time.time() < end:
        app.processEvents()
        s = g.session
        if mode == "play" and s.human_turn() and g.thoughts is not None:
            g.on_move_chosen(bot.choose(s.obs(s.human)))
            continue
        time.sleep(0.005)
        assert pp.thoughts_text.isVisibleTo(pp) and pp.thoughts_text.text(), "пустая панель мыслей"
        texts.append(pp.thoughts_text.text())
        seen["grid"] += pp.grid.isVisibleTo(pp)
        seen["scores"] += pp.moves.isVisibleTo(pp) and pp.moves.count() > 0
        seen["novice"] += g.t("th_rules") in pp.thoughts_text.text()
        seen["ai_turn_text"] += s.ai_turn()
        seen["fresh_on_ai_turn"] += s.ai_turn() and g.thoughts is not None and g.thoughts_token == g.token
    assert len(g.session.moves) >= 10 or g.session.over
    assert seen["grid"] > 0, "сетка учёта ни разу не показана"
    if mode == "demo":
        if level == "novice":
            assert seen["novice"] > 0, "нет «играет по правилам»"
        else:
            assert seen["scores"] > 0, "оценки ходов ни разу не показаны"
    assert seen["ai_turn_text"] > 0
    assert seen["fresh_on_ai_turn"] > 0, "на ходу ИИ сетка не обновляется"
    assert not unseen, f"в показе ИИ сходил раньше, чем показал мысли: {len(unseen)} раз"
    g.change("show_thoughts", False)
    g.change("mode", "play")


# --- графики статистики (правило автора 10.10: графики во всех играх с ИИ) ---


def _charts(g):
    from game.ui.charts import BarChart, LineChart
    page = g.stats
    return {"share": page.share_chart, "levels": page.levels_chart, "moves": page.moves_chart,
            "margin": page.margin_chart, "passport": page.passport_chart}, (BarChart, LineChart)


def test_stats_page_has_charts_and_words_when_empty(app, win):
    g = win.game
    g.show_page("stats")
    cs, kinds = _charts(g)
    for name, c in cs.items():
        assert isinstance(c, kinds) and c.isVisibleTo(g.stats), name
        assert c.title, name
        if name != "passport":
            assert not c.has_data() and c.empty_text, f"{name}: пустой холст без надписи"
    assert cs["passport"].has_data()                 # паспорт есть всегда
    g.grab()


def test_finished_game_goes_to_history_and_charts(app, win):
    g = win.game
    g.change("level", "novice")
    g.start_game(seed=3)
    play_out(app, g)
    games = g.history.games
    assert len(games) == 1
    rec = games[0]
    s = g.session
    assert rec["outcome"] == s.outcome_for_human() and rec["moves"] == len(s.moves)
    assert rec["level"] == "novice" and rec["players"] == 2
    left = {q: s.state.hands[q].bit_count() for q in range(s.n)}
    expect = {"win": left[s.state.fool] if s.state.fool >= 0 else 0, "loss": -left[0], "draw": 0}[rec["outcome"]]
    assert rec["margin"] == expect
    for i in range(30):                              # ещё партии - сразу в журнал
        g.history.record({"players": 3, "level": "strong", "outcome": ("win", "loss", "draw")[i % 3],
                          "moves": 50 + i, "margin": (i % 7) - 3})
    g.show_page("stats")
    cs, _ = _charts(g)
    for name in ("share", "levels", "moves", "margin"):
        assert cs[name].has_data(), name
    assert cs["levels"].groups == [g.t("novice"), g.t("strong")]
    assert len(cs["share"].points) == 31 and len(cs["share"].second) == 31
    assert cs["moves"].points[-1] == (31.0, 79.0)
    g.ctx.set_theme("light")
    assert all(c.theme == "light" for c in cs.values())
    g.ctx.set_theme("dark")


def test_peeked_and_demo_games_stay_out_of_history(app, win):
    g = win.game
    g.change("level", "novice")
    g.change("reveal", True)
    g.start_game(seed=3)
    play_out(app, g)
    g.change("reveal", False)
    g.change("mode", "demo")
    g.start_game(seed=2)
    assert wait(app, lambda: g.session.over, 60)
    g.change("mode", "play")
    assert g.history.games == []
