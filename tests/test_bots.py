"""Простой бот, случайный игрок и турнир с зёрнами."""
import random

from hypothesis import given, settings, strategies as st

from game.ai.agents import NoviceAgent, RandomAgent, make_agent, novice_move
from game.ai.tournament import match, play_game
from game.core import cards as C
from game.core.durak import ATTACK, DEFEND, MOVE_PASS, MOVE_TAKE, Rules, State
from game.core.observation import observation
from tests.test_durak import A, D, H, make


def obs_of(s):
    return observation(s, s.turn)


def test_novice_attacks_with_lowest_non_trump():
    s = make([["A♠", "6♥", "9♣", "7♦"], ["8♠", "9♦", "J♦"]], deck=["8♥", "10♣"])
    assert NoviceAgent().choose(obs_of(s)) == A("7♦")


def test_novice_prefers_pair_among_equals():
    s = make([["7♠", "7♣", "7♦", "K♦"], ["8♠", "9♦", "J♦"]], deck=["8♥", "10♣"])
    s2 = make([["7♠", "8♣", "8♦", "K♦"], ["9♠", "9♦", "J♦"]], deck=["8♥", "10♣"])
    assert NoviceAgent().choose(obs_of(s))[1] in {C.parse("7♠"), C.parse("7♣"), C.parse("7♦")}
    assert NoviceAgent().choose(obs_of(s2)) == A("7♠")


def test_novice_defends_with_cheapest_and_saves_trumps():
    s = make([["7♠"], ["9♠", "Q♠", "6♥", "K♦"]], deck=["8♥", "10♣"])
    s.apply(A("7♠"))
    assert NoviceAgent().choose(obs_of(s)) == D("9♠")
    s = make([["7♠"], ["8♦", "6♥", "K♦"]], deck=["8♥", "10♣"])
    s.apply(A("7♠"))
    assert NoviceAgent().choose(obs_of(s)) == D("6♥")       # младший козырь - можно


def test_novice_takes_instead_of_high_trump_early():
    deck = ["8♥"] + [x + "♣" for x in ("6", "7", "8", "9", "10", "J", "Q", "K", "A")]
    s = make([["7♠"], ["A♥", "K♦"]], deck=deck)
    s.apply(A("7♠"))
    assert NoviceAgent().choose(obs_of(s)) == MOVE_TAKE


def test_novice_takes_when_cannot_beat():
    s = make([["A♠"], ["8♠", "K♦"]], deck=["8♥", "10♣"])
    s.apply(A("A♠"))
    assert NoviceAgent().choose(obs_of(s)) == MOVE_TAKE


def test_novice_throws_cheap_not_trump():
    s = make([["7♠", "7♥", "8♣", "Q♦"], ["9♠", "8♦", "J♦", "K♦"]], deck=["6♥", "10♣"])
    s.apply(A("7♠"))
    s.apply(D("9♠"))
    # на столе 7 и 9: 7♥ - козырь, его не подкидывает; больше нечего - пас
    assert NoviceAgent().choose(obs_of(s)) == MOVE_PASS


@settings(max_examples=60)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans())
def test_novice_always_returns_legal_move(seed, n, transfer):
    rng = random.Random(seed)
    s = State.new(Rules(players=n, transfer=transfer), seed=seed)
    bot = NoviceAgent()
    while not s.over:
        o = obs_of(s)
        m = bot.choose(o)
        assert m in o.legal
        s.apply(m if rng.random() < 0.7 else rng.choice(s.legal_moves()))


def test_tournament_is_reproducible():
    r1 = match(NoviceAgent(), RandomAgent(), 20, seed=4)
    r2 = match(NoviceAgent(), RandomAgent(), 20, seed=4)
    assert r1.details == r2.details
    r3 = match(NoviceAgent(), RandomAgent(), 20, seed=5)
    assert r3.details != r1.details


def test_paired_deals_swap_seats():
    r = match(RandomAgent(), RandomAgent(), 6, seed=1)
    seeds = [d[0] for d in r.details]
    assert seeds[0] == seeds[1] and seeds[2] == seeds[3] and seeds[0] != seeds[2]
    assert [d[1] for d in r.details] == [0, 1, 0, 1, 0, 1]


def test_novice_beats_random():
    r = match(NoviceAgent(), RandomAgent(), 200, seed=1)
    assert r.win_rate > 0.8, r.win_rate


def test_novice_rarely_fool_among_randoms():
    for n in (3, 4):
        r = match(NoviceAgent(), RandomAgent(), 120, seed=2, players=n)
        assert r.fool_rate < 0.5 / n, (n, r.fool_rate)


def test_make_agent_levels():
    assert make_agent("random").level == "random"
    assert make_agent("novice").level == "novice"


def test_novice_takes_when_one_of_several_cannot_be_beaten():
    from tests.test_durak import T
    s = make([["7♠", "Q♣"], ["7♦", "A♣"], ["8♠", "K♣", "J♣"]], deck=["6♥", "10♣"],
             transfer=True)
    s.apply(A("7♠"))
    s.apply(T("7♦"))
    o = obs_of(s)
    assert D("8♠", 0) in o.legal
    assert NoviceAgent().choose(o) == MOVE_TAKE      # 7♦ не побить - 8♠ не тратит
