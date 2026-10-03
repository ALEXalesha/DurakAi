"""Закон честности (spec §3): ИИ получает только observation(state, player).

Перестановка неизвестных игроку карт - по рукам соперников и по закрытой части колоды -
не должна менять ни того, что он видит, ни его решений при том же зерне. Известные
всем карты (взятые со стола, открытый козырь у того, кто его добрал) остаются на месте:
их видел каждый.
"""
import dataclasses
import random

from hypothesis import given, settings, strategies as st

from game.core import cards as C
from game.core.durak import Rules, State
from game.core.observation import Observation, observation


def random_position(seed, n, transfer):
    """Партия случайными ходами до случайного места, где решение не вынужденное."""
    rng = random.Random(seed)
    s = State.new(Rules(players=n, transfer=transfer), seed=seed)
    stop = rng.randrange(0, 120)
    k = 0
    while not s.over:
        if k >= stop and len(s.legal_moves()) > 1:
            return s
        s.apply(rng.choice(s.legal_moves()))
        k += 1
    return None


def shuffle_unknown(s, p, rng):
    """Копия s, в которой неизвестные игроку p карты розданы заново (те же размеры рук)."""
    obs = observation(s, p)
    s2 = s.clone(log=True)
    pool = []
    slots = []
    for q in range(s.n):
        if q == p:
            continue
        hidden = s.hands[q] & ~obs.known[q]
        pool += C.cards_of(hidden)
        slots.append((q, hidden.bit_count()))
        s2.hands[q] &= ~hidden
    closed = s.deck[1:] if s.deck else []
    pool += closed
    rng.shuffle(pool)
    i = 0
    for q, k in slots:
        s2.hands[q] |= C.mask(pool[i:i + k])
        i += k
    if s.deck:
        s2.deck = [s.deck[0]] + pool[i:]
    s2.check()
    return s2


def agents():
    from game.ai.agents import LEVELS, make_agent
    return [make_agent(level) for level in LEVELS]


@settings(max_examples=150)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.integers(0, 10 ** 6))
def test_shuffling_unknown_cards_changes_nothing_visible(seed, n, transfer, seed2):
    s = random_position(seed, n, transfer)
    if s is None:
        return
    p = s.turn
    rng = random.Random(seed2)
    for viewer in {p, rng.randrange(n)}:
        s2 = shuffle_unknown(s, viewer, rng)
        assert observation(s2, viewer) == observation(s, viewer)


@settings(max_examples=25)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.integers(0, 10 ** 6))
def test_ai_decisions_do_not_depend_on_unknown_cards(seed, n, transfer, seed2):
    s = random_position(seed, n, transfer)
    if s is None:
        return
    p = s.turn
    s2 = shuffle_unknown(s, p, random.Random(seed2))
    o1, o2 = observation(s, p), observation(s2, p)
    for agent in agents():
        assert agent.choose(o1, seed=11) == agent.choose(o2, seed=11), agent.level


def test_shuffle_really_moves_cards():
    """Проверка самой проверки: перестановка не пустая, иначе закон ничего не значит."""
    moved = total = 0
    for seed in range(60):
        s = random_position(seed, 2, False)
        if s is None or len(s.deck) < 2:     # без колоды вдвоём неизвестного нет
            continue
        s2 = shuffle_unknown(s, s.turn, random.Random(seed))
        total += 1
        moved += s2.hands != s.hands or s2.deck != s.deck
    assert total >= 20 and moved >= total - 1


def test_observation_sees_own_hand_and_public_table():
    """И обратное: своё и публичное наблюдение видит, иначе равенство ничего не стоит."""
    s = random_position(5, 2, False)
    p = s.turn
    o = observation(s, p)
    assert o.hand == s.hands[p]
    assert o.hand_sizes == tuple(h.bit_count() for h in s.hands)
    assert o.deck_size == len(s.deck) and o.discard == s.discard
    assert o.table == tuple(tuple(x) for x in s.table)
    assert o.legal == tuple(s.legal_moves())
    s2 = s.clone(log=True)
    other = 1 - p
    # обмен своей карты на чужую - наблюдение меняется
    mine = s.hands[p] & -s.hands[p]
    theirs = s.hands[other] & -s.hands[other]
    s2.hands[p] = (s.hands[p] & ~mine) | theirs
    s2.hands[other] = (s.hands[other] & ~theirs) | mine
    assert observation(s2, p) != o


def test_observation_holds_no_state_and_is_immutable():
    s = random_position(9, 3, True)
    o = observation(s, s.turn)
    assert isinstance(o, Observation)

    def walk(x):
        assert not isinstance(x, (State, list, dict, set)), type(x)
        if isinstance(x, tuple):
            for y in x:
                walk(y)
    for f in dataclasses.fields(o):
        walk(getattr(o, f.name))
    try:
        o.hand = 0
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("наблюдение можно поменять")


def test_known_cards_are_picked_up_and_trump():
    """Взятые со стола карты известны всем, пока не сыграны; открытый козырь - у добравшего."""
    from tests.test_durak import A, H, make
    from game.core.durak import MOVE_PASS, MOVE_TAKE
    s = make([["7♠", "7♣", "Q♣", "K♣", "A♣", "J♣"], ["8♦", "9♦", "J♦", "Q♦", "K♦"]],
             deck=["6♥", "10♣", "8♣"])
    s.apply(A("7♠"))
    s.apply(MOVE_TAKE)
    s.apply(A("7♣"))
    s.apply(MOVE_PASS)
    o = observation(s, 0)
    assert o.known[1] == H("7♠", "7♣")
    # 0 добрал 8♣ и 10♣, защитнику - открытый козырь 6♥... колода кончилась на 0
    s2 = make([["7♠", "Q♣", "K♣", "A♣", "J♣", "10♦"], ["8♠", "9♦", "J♦", "Q♦", "K♦"]],
              deck=["6♥", "10♣", "8♣"])
    from tests.test_durak import D
    s2.apply(A("7♠"))
    s2.apply(D("8♠"))
    s2.apply(MOVE_PASS)
    assert observation(s2, 0).known[1] == H("6♥")
    assert observation(s2, 1).known[1] == 0 or observation(s2, 1).known[0] == 0


@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans())
def test_known_cards_are_always_really_in_hand(seed, n, transfer):
    """Закон: «известные всем» карты игрока действительно у него - на каждом шаге партии."""
    rng = random.Random(seed)
    s = State.new(Rules(players=n, transfer=transfer), seed=seed)
    while not s.over:
        o = observation(s, s.turn)
        for q in range(n):
            assert o.known[q] & ~s.hands[q] == 0
        assert o.unseen() & o.hand == 0
        s.apply(rng.choice(s.legal_moves()))
