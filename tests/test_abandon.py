"""Брошенная партия (решение автора 16.10): после вашего первого хода она идёт в статистику
и графики. Бросить - «Новая партия» (кнопка или N), «В меню» (кнопка или Esc), закрыть окно.
Вы уже вышли (избавились от карт), а ИИ ещё доигрывают - «не дурак», иначе - дурак.
До первого вашего хода (и автоматический пас, когда подкинуть нечего, - не ваш ход) партия
не считается. Подглядывание и показ «ИИ против ИИ» в статистику не идут, как и раньше.
Окно без экрана (Qt offscreen)."""
import time

import pytest
from PySide6.QtWidgets import QApplication

from game import APP_NAME, GAME_INFO, create_widget
from game.ai.agents import NoviceAgent
from game.core import cards as C
from game.core.durak import MOVE_PASS, Rules, State
from game.ui.session import Session

HEARTS = C.SUITS.index("♥")


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
    g.change("level", "novice")
    yield w
    g.shutdown()
    w.close()
    w.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait(app, cond, limit=30.0):
    end = time.time() + limit
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.002)
    return cond()


def human_state(g, hands, deck=(), first=0, trump=HEARTS):
    """Ручная раздача в окне: место 0 - человек, соперники - новички."""
    s = Session(players=len(hands), level="novice")
    s.state = State.from_parts(Rules(players=len(hands)), [C.mask(C.parse(x) for x in h) for h in hands],
                               [C.parse(x) for x in deck], first=first, trump=None if deck else trump)
    g.session = s
    g.stack.setCurrentWidget(g.play)
    g._invalidate()
    g.after_change()
    return s


def first_human_move(app, g, seed):
    """Новая партия вдвоём, ваш первый настоящий ход (не единственный пас)."""
    g.start_game(seed=seed)
    assert wait(app, lambda: g.session.human_turn() and g.session.legal() != [MOVE_PASS], 30)
    s = g.session
    g.on_move_chosen(NoviceAgent().choose(s.obs(s.human)))
    assert not s.over
    return s


def leave(app, g, how):
    if how == "menu":
        g.show_page("menu")
    elif how == "new":
        g.start_game(seed=99)
    else:
        g.shutdown()
    app.processEvents()


def entry(g, key="2p/novice"):
    return g.ctx.stats.entry(key)


@pytest.mark.parametrize("how", ["menu", "new", "close"])
def test_left_after_first_move_counts_as_fool(app, win, how):
    g = win.game
    s = first_human_move(app, g, seed=5)
    cards = s.state.hands[0].bit_count()
    leave(app, g, how)
    e = entry(g)
    assert (e["games"], e["losses"], e["wins"], e["draws"]) == (1, 1, 0, 0), how
    rec = g.history.games
    assert len(rec) == 1 and rec[0]["outcome"] == "loss" and rec[0]["margin"] == -cards
    assert rec[0]["moves"] == len(s.moves)


@pytest.mark.parametrize("how", ["menu", "new", "close"])
def test_left_before_first_move_is_not_counted(app, win, how):
    g = win.game
    g.start_game(seed=5)
    leave(app, g, how)
    assert entry(g)["games"] == 0 and g.history.games == []


def test_ai_moves_alone_do_not_start_the_count(app, win):
    """ИИ сходил, вы ещё нет - брошенная партия не считается."""
    g = win.game
    for seed in range(60):
        g.start_game(seed=seed)
        if g.session.state.turn != 0:
            break
    else:
        pytest.fail("нет раздачи, где первым ходит ИИ")
    assert wait(app, lambda: g.session.human_turn(), 30)
    assert len(g.session.moves) >= 1
    g.show_page("menu")
    assert entry(g)["games"] == 0


def test_automatic_pass_is_not_your_move(app, win):
    """Втроём: ИИ 1 ходит на ИИ 2, подкинуть вам нечего - пас сам. Это не ваш ход."""
    g = win.game
    s = human_state(g, [["A♣", "K♦"], ["6♠", "Q♦"], ["7♠", "9♣"]], first=1)
    # отбой ИИ 1 и ИИ 2 кончился (ваш пас - сам), теперь ИИ 2 ходит на вас - настоящий выбор
    assert wait(app, lambda: s.human_turn() and s.legal() != [MOVE_PASS], 30)
    assert s.state.bout == 1 and s.state.defender == 0
    g.show_page("menu")
    assert entry(g, "3p/novice")["games"] == 0


def test_left_once_is_counted_once(app, win):
    g = win.game
    first_human_move(app, g, seed=5)
    g.show_page("menu")
    g.show_page("stats")
    g.show_page("menu")
    g.shutdown()
    assert entry(g)["games"] == 1 and len(g.history.games) == 1


def test_peeked_or_demo_game_left_is_not_counted(app, win):
    g = win.game
    g.change("reveal", True)
    first_human_move(app, g, seed=5)
    g.show_page("menu")
    g.change("reveal", False)
    g.change("mode", "demo")
    g.start_game(seed=2)
    assert wait(app, lambda: len(g.session.moves) >= 3, 30)
    g.show_page("menu")
    g.change("mode", "play")
    assert entry(g)["games"] == 0 and g.history.games == []


def test_finished_game_is_not_counted_again_on_leaving(app, win):
    g = win.game
    s = human_state(g, [["6♠"], ["7♠", "A♣"]], first=0)
    g.on_move_chosen(next(m for m in s.legal() if m[1] == C.parse("6♠")))
    assert wait(app, lambda: s.over, 30)
    n = entry(g)["games"]
    assert n == 1
    g.show_page("menu")
    g.start_game(seed=1)
    assert entry(g)["games"] == n


def went_out(app, g):
    """Втроём: вы ходите последней картой 6♠, ИИ 1 бьёт 7♠, подкинуть ИИ 2 нечего - бито,
    вы вышли. У ИИ 1 и ИИ 2 карты остаются - они доигрывают."""
    g.change("delay_ms", 1500)          # ИИ ждёт: успеваем уйти, пока они доигрывают
    s = human_state(g, [["6♠"], ["7♠", "A♣", "K♦"], ["8♦", "9♣", "Q♣"]], first=0)
    g.on_move_chosen(next(m for m in s.legal() if m[1] == C.parse("6♠")))
    assert wait(app, lambda: 0 in s.state.out, 30)
    assert not s.over
    return s


@pytest.mark.parametrize("how", ["menu", "new", "close"])
def test_left_after_going_out_is_not_fool(app, win, how):
    g = win.game
    s = went_out(app, g)
    biggest = max(s.state.hands[q].bit_count() for q in (1, 2) if q not in s.state.out)
    leave(app, g, how)
    e = entry(g, "3p/novice")
    assert (e["games"], e["wins"], e["losses"], e["draws"]) == (1, 1, 0, 0), how
    rec = g.history.games
    assert len(rec) == 1 and rec[0]["outcome"] == "win" and rec[0]["players"] == 3
    # дурак ещё не известен: разница - у кого из доигрывающих больше всего карт
    assert rec[0]["margin"] == biggest > 0


def test_out_before_the_others_draw_is_a_win(app, win):
    """Вы вышли первым, ИИ 1 и ИИ 2 вышли потом одновременно (дурака нет). Для вас это
    «не дурак», как и при любом конце после вашего выхода, а не ничья."""
    g = win.game
    s = human_state(g, [["6♠"], ["7♠", "9♦"], ["10♦"]], first=0)
    g.on_move_chosen(next(m for m in s.legal() if m[1] == C.parse("6♠")))
    assert wait(app, lambda: s.over, 30)
    assert s.state.fool == -1 and s.state.out[0] == 0
    assert s.outcome_for_human() == "win"
    e = entry(g, "3p/novice")
    assert (e["games"], e["wins"], e["draws"]) == (1, 1, 0)
    assert g.history.games[-1]["outcome"] == "win"
    assert g.play.status.text() == g.t("win")


def test_out_together_with_the_last_is_still_a_draw(app, win):
    """Вдвоём вы и ИИ вышли одновременно - ничья, как и раньше."""
    g = win.game
    s = human_state(g, [["6♠"], ["7♠"]], first=0)
    g.on_move_chosen(next(m for m in s.legal() if m[1] == C.parse("6♠")))
    assert wait(app, lambda: s.over, 30)
    assert s.state.fool == -1 and s.outcome_for_human() == "draw"
    assert entry(g)["draws"] == 1


def test_stats_page_explains_the_count(app, win):
    g = win.game
    g.show_page("stats")
    text = g.stats.count_note.text()
    assert g.stats.count_note.isVisibleTo(g.stats) and text == g.t("count_note")
    for lang in ("ru", "en"):
        g.ctx.set_lang(lang)
        assert g.stats.count_note.text() == g.t("count_note")
    g.ctx.set_lang("ru")
