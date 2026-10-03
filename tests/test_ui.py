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
            assert wait(app, lambda: g.thoughts is not None, 20)
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
