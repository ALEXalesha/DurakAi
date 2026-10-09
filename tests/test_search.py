"""Поиск по раскладкам и точный перебор в конце."""
import random
import threading
import time

import numpy as np
from hypothesis import given, settings, strategies as st

from game.ai import tracker
from game.ai.agents import NoviceAgent, make_agent
from game.ai.search import Exact, SearchAgent, exact_applicable, finish_bout, heuristic, state_from
from game.core import cards as C
from game.core.durak import Rules, State
from game.core.observation import observation
from tests.test_durak import A, H, make
from tests.test_honesty import random_position


@settings(max_examples=60)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.integers(0, 10 ** 6))
def test_state_from_sample_keeps_public_part(seed, n, transfer, seed2):
    s = random_position(seed, n, transfer)
    if s is None:
        return
    o = observation(s, s.turn)
    hands, deck = tracker.sample(o, np.random.default_rng(seed2))
    w = state_from(o, hands, deck)
    w.check()
    assert w.table == s.table and w.discard == s.discard and w.turn == s.turn
    assert w.attacker == s.attacker and w.defender == s.defender and w.out == s.out
    assert sorted(w.legal_moves()) == sorted(s.legal_moves())
    finish_bout(w)
    w.check()
    assert w.over or not w.table


def endgame():
    # колода пуста, козырь червы. У меня (0) Т♥ и 6♠, у соперника 7♠.
    # 6♠ первой - соперник бьёт и выходит, я дурак. Т♥ первой - он берёт, потом 6♠... он дурак.
    return make([["A♥", "6♠"], ["7♠"]], trump="♥")


def test_exact_finds_the_only_winning_move():
    s = endgame()
    o = observation(s, 0)
    assert exact_applicable(o)
    res = dict(Exact().solve(s, 0))
    assert res[A("A♥")] == 1.0 and res[A("6♠")] == -1.0
    assert NoviceAgent().choose(o) == A("6♠")          # простой бот ошибается
    assert make_agent("strong").choose(o) == A("A♥")   # сильный - нет
    # и оценки у сильного точные: перебор, а не догадка по раскладкам
    assert dict(make_agent("strong").analyze(o)) == {A("A♥"): 1.0, A("6♠"): -1.0}


def test_exact_gives_up_when_too_big():
    s = State.new(Rules(), seed=3)
    s.deck = []
    s.trump_card = -1
    assert Exact(node_limit=50).solve(s, s.turn) is None


def _big_endgame():
    s = State.new(Rules(), seed=3)
    s.deck = []
    s.trump_card = -1
    return s


def test_exact_listens_to_stop_and_deadline():
    """Точный перебор не держит поток дольше флага остановки и срока хода."""
    s = _big_endgame()
    flag = threading.Event()
    flag.set()
    t0 = time.perf_counter()
    assert Exact(node_limit=10 ** 9).solve(s, s.turn, stop=flag) is None
    assert Exact(node_limit=10 ** 9).solve(s, s.turn, deadline=time.perf_counter() - 1) is None
    assert time.perf_counter() - t0 < 1.0
    # без флага и срока тот же перебор идёт дольше 64 узлов - значит, проверка была нужна
    e = Exact(node_limit=200)
    assert e.solve(s, s.turn) is None and e.nodes > 64


def _real_endgame():
    """Настоящий конец партии вдвоём: колода пуста, карт на руках побольше."""
    bot = NoviceAgent()
    for seed in range(200):
        s = State.new(Rules(), seed=seed)
        while not s.over:
            o = observation(s, s.turn)
            if (not s.deck and exact_applicable(o) and len(o.legal) > 1
                    and sum(h.bit_count() for h in s.hands) >= 10):
                return s, o
            s.apply(bot.choose(o))
    raise AssertionError("нет подходящего конца партии")


def test_search_with_exact_stops_quickly():
    s, o = _real_endgame()
    flag = threading.Event()
    flag.set()
    agent = SearchAgent(samples=24, use_net=False, exact=True, node_limit=10 ** 9)
    t0 = time.perf_counter()
    res = agent.analyze(o, stop=flag)
    assert time.perf_counter() - t0 < 1.0
    assert [m for m, _ in res] == list(o.legal)
    assert agent.exact.nodes <= 64                    # перебор оборван (весь - сотни узлов)


def test_same_observation_same_seed_same_move():
    s = random_position(21, 3, True)
    o = observation(s, s.turn)
    a = make_agent("medium")
    assert a.choose(o, seed=5) == a.choose(o, seed=5)
    assert a.analyze(o, seed=5) == a.analyze(o, seed=5)


def test_analyze_scores_every_legal_move():
    s = random_position(8, 2, False)
    o = observation(s, s.turn)
    res = make_agent("medium").analyze(o, seed=1)
    assert [m for m, _ in res] == list(o.legal)
    assert all(-1.0 <= v <= 1.0 for _, v in res)


def test_stop_flag_and_time_limit_end_search_early():
    s = State.new(Rules(players=4), seed=2)
    o = observation(s, s.turn)
    slow = SearchAgent(samples=5000, use_net=False, exact=False)
    ev = threading.Event()
    ev.set()
    t = time.perf_counter()
    slow.choose(o, seed=1, stop=ev)
    assert time.perf_counter() - t < 1.0
    timed = SearchAgent(samples=5000, use_net=False, exact=False, time_limit=0.2)
    t = time.perf_counter()
    timed.choose(o, seed=1)
    assert time.perf_counter() - t < 1.5


def test_heuristic_prefers_fewer_and_stronger_cards():
    good = make([["A♥", "K♥"], ["6♠", "7♠", "8♣", "9♦"]], deck=["6♥", "10♣"])
    bad = make([["6♠", "7♠", "8♣", "9♦"], ["A♥", "K♥"]], deck=["6♥", "10♣"])
    assert heuristic(good, 0) > 0 > heuristic(bad, 0)


@settings(max_examples=15)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans())
def test_search_agents_play_legal_full_games(seed, n, transfer):
    rng = random.Random(seed)
    s = State.new(Rules(players=n, transfer=transfer), seed=seed)
    agent = SearchAgent(samples=3, use_net=False, exact=True)
    while not s.over:
        o = observation(s, s.turn)
        m = agent.choose(o, seed=rng.randrange(10 ** 6)) if rng.random() < 0.5 else rng.choice(o.legal)
        assert m in o.legal
        s.apply(m)
