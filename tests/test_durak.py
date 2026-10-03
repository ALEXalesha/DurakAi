"""Правила партии: ручные раздачи на каждое правило spec §2 и случайные партии с инвариантами."""
import random

import pytest
from hypothesis import given, strategies as st

from game.core import cards as C
from game.core.durak import (ATTACK, DEFEND, DRAW, MOVE_PASS, MOVE_TAKE, PASS, TAKE, TRANSFER,
                             Rules, State, first_attacker, play)


def H(*names):
    return C.mask(C.parse(x) for x in names)


def deck_of(*names):
    """Колода: первая карта - дно (открытый козырь), последняя - верх."""
    return [C.parse(x) for x in names]


def make(hands, deck=(), first=0, trump=None, **rules):
    """Ручная раздача. Остальные карты - в отбое."""
    r = Rules(players=len(hands), **rules)
    return State.from_parts(r, [H(*h) for h in hands], deck_of(*deck), first=first,
                            trump=None if deck else C.SUITS.index(trump))


def A(name):
    return (ATTACK, C.parse(name), -1)


def D(name, slot=0):
    return (DEFEND, C.parse(name), slot)


def defend(s, name):
    """Побить первую не побитую карту."""
    slot = next(i for i, (a, d) in enumerate(s.table) if d < 0)
    s.apply(D(name, slot))


def T(name):
    return (TRANSFER, C.parse(name), -1)


# ---------- раздача и первый ход ----------

def test_new_game_deals_six_and_lowest_trump_starts():
    for seed in range(30):
        for n in (2, 3, 4):
            s = State.new(Rules(players=n), seed=seed)
            assert all(h.bit_count() == 6 for h in s.hands)
            assert len(s.deck) == 36 - 6 * n
            assert s.trump == C.suit(s.deck[0]) == C.suit(s.trump_card)
            lows = [min((c for c in C.cards_of(h) if C.suit(c) == s.trump), default=99)
                    for h in s.hands]
            if min(lows) < 99:
                assert s.attacker == lows.index(min(lows))
            assert s.defender == (s.attacker + 1) % n
            assert s.turn == s.attacker
            s.check()


def test_first_attacker_without_trumps_is_lowest_card():
    hands = [H("8♠", "K♣"), H("7♦", "A♠"), H("9♠")]
    assert first_attacker(hands, 3) == 1


def test_first_can_be_given():
    s = State.new(Rules(players=3), seed=1, first=2)
    assert s.attacker == 2 and s.defender == 0


# ---------- защита ----------

def test_defense_same_suit_higher_or_any_trump():
    s = make([["7♠"], ["6♠", "9♠", "A♣", "6♥", "K♦"]], deck=["8♥", "10♣"])
    s.apply(A("7♠"))
    assert s.turn == 1
    moves = set(s.legal_moves())
    assert moves == {D("9♠"), D("6♥"), MOVE_TAKE}


def test_trump_beaten_only_by_higher_trump():
    s = make([["9♥"], ["A♠", "8♥", "10♥", "K♦"]], deck=["7♥", "10♣"])
    s.apply(A("9♥"))
    assert set(s.legal_moves()) == {D("10♥"), MOVE_TAKE}


def test_illegal_move_raises_and_changes_nothing():
    s = make([["7♠", "8♠"], ["6♠", "9♠"]], deck=["8♥", "10♣"])
    before = (s.hands[:], s.table[:], s.turn)
    with pytest.raises(ValueError):
        s.apply(D("9♠"))            # защищаться, когда ходит атакующий
    with pytest.raises(ValueError):
        s.apply(A("6♠"))            # чужая карта
    assert (s.hands, s.table, s.turn) == before


# ---------- подкидывание ----------

def test_throw_only_ranks_on_table():
    s = make([["7♠", "7♣", "9♦", "Q♣"], ["8♠", "A♣", "K♦", "J♦", "10♦"]], deck=["8♥", "10♣"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    assert s.turn == 0
    assert set(s.legal_moves()) == {A("7♣"), MOVE_PASS}   # 7 и 8 на столе, 9 и Д - нет


def test_throw_order_starts_with_attacker_and_skips_defender():
    # трое: 0 атакует 1, подкидывают 0, потом 2
    s = make([["7♠", "Q♣"], ["8♠", "A♣", "K♦"], ["7♦", "9♣"]], deck=["8♥", "10♣"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    assert s.turn == 0
    assert s.legal_moves() == [MOVE_PASS]   # нечего подкинуть - только пас
    s.apply(MOVE_PASS)
    assert s.turn == 2
    s.apply(A("7♦"))
    assert s.turn == 1
    s.apply(MOVE_TAKE)
    # после «беру» снова круг с атакующего
    assert s.taking and s.turn == 0


def test_new_card_gives_everyone_a_new_round():
    s = make([["7♠", "7♥"], ["8♠", "9♥", "K♦"], ["8♦", "Q♣"]], deck=["6♥", "10♣"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(MOVE_PASS)          # 0 пасует (но 7♥ у него есть)
    s.apply(A("8♦"))            # 2 подкидывает
    defend(s, "9♥")            # защитник бьёт козырем
    assert s.turn == 0          # и 0 снова может подкинуть
    assert A("7♥") in s.legal_moves()


def test_pass_by_all_ends_bout_bito_defender_attacks_next():
    s = make([["7♠", "Q♣"], ["8♠", "A♣"]], deck=["6♥", "10♣", "J♣", "J♠", "J♦"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(MOVE_PASS)
    assert s.discard & H("7♠", "8♠") == H("7♠", "8♠")
    assert not s.table
    assert s.attacker == 1 and s.defender == 0 and s.turn == 1


ATT7 = ["6♠", "7♣", "8♠", "9♣", "10♠", "J♣", "Q♠"]
DEF7 = ["7♠", "8♣", "9♠", "10♣", "J♠", "Q♣", "K♥"]
CHAIN = [("7♣", "8♣"), ("8♠", "9♠"), ("9♣", "10♣"), ("10♠", "J♠"), ("J♣", "Q♣")]


def test_table_at_most_six():
    s = make([ATT7, DEF7], deck=["A♥", "K♣"])
    s.apply(A("6♠"))
    s.apply(D("7♠"))
    for a, d in CHAIN:
        assert A(a) in s.legal_moves()
        s.apply(A(a))
        defend(s, d)
    # шесть пар: отбой кончился сам, хотя у атакующего осталась Д♠, а дама на столе
    assert not s.table and s.bout == 1
    assert s.discard & H("Q♣") and s.hands[1].bit_count() == 1


def test_first_bout_five_cards_switch():
    for five, pairs in ((True, 5), (False, 6)):
        s = make([ATT7, DEF7], deck=["A♥", "K♣"], first_bout_five=five)
        s.apply(A("6♠"))
        s.apply(D("7♠"))
        done = 1
        for a, d in CHAIN:
            if not s.table:
                break
            s.apply(A(a))
            defend(s, d)
            done += 1
        assert done == pairs and not s.table


def test_undefended_not_more_than_defender_cards():
    # у защитника 2 карты: больше двух не побитых на столе быть не может
    s = make([["7♠", "7♣", "7♦", "Q♣"], ["8♠", "A♣"]], deck=["6♥", "10♣"])
    s.apply(A("7♠"))
    s.apply(MOVE_TAKE)
    assert s.turn == 0
    s.apply(A("7♣"))
    # не побиты 2 карты = 2 карты у защитника -> подкидывать больше нельзя, отбой кончился
    assert not s.table
    assert s.hands[1] & H("7♠", "7♣") == H("7♠", "7♣")


# ---------- «беру» ----------

def test_take_others_throw_then_next_after_defender_attacks():
    s = make([["7♠", "7♣", "Q♣"], ["8♠", "A♣", "K♦", "Q♦"], ["7♦", "9♣", "J♦"]],
             deck=["6♥", "10♣", "J♣", "J♠", "8♦", "8♣", "9♠", "9♦", "10♠", "10♦"])
    s.apply(A("7♠"))
    s.apply(MOVE_TAKE)
    assert s.turn == 0
    s.apply(A("7♣"))
    assert s.turn == 0            # защитник берёт - отвечать не нужно, круг заново
    s.apply(MOVE_PASS)
    assert s.turn == 2
    s.apply(A("7♦"))
    s.apply(MOVE_PASS)            # 0
    s.apply(MOVE_PASS)            # 2
    assert s.hands[1] & H("7♠", "7♣", "7♦") == H("7♠", "7♣", "7♦")
    assert s.attacker == 2 and s.defender == 0   # 1 пропускает ход
    s.check()


def test_defended_cards_also_go_to_taker():
    s = make([["7♠", "7♣", "Q♣"], ["8♠", "A♣", "K♦"]], deck=["6♥", "10♣"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(A("7♣"))
    s.apply(MOVE_TAKE)
    s.apply(MOVE_PASS)
    assert s.hands[1] & H("7♠", "8♠", "7♣") == H("7♠", "8♠", "7♣")
    assert s.attacker == 0


# ---------- добор ----------

def test_draw_order_attacker_throwers_defender_last_trump_last():
    # трое, в колоде 3 карты: атакующий берёт 2, подкидывавший 1, защитнику не хватает
    s = make([["7♠", "Q♣", "A♦", "K♦", "J♦", "10♦"],
              ["8♠", "9♣", "A♣", "K♣", "J♣", "10♣"],
              ["7♣", "6♦", "7♦", "8♦", "9♦", "Q♦"]],
             deck=["6♥", "7♥", "8♥"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(MOVE_PASS)     # 0
    s.apply(A("7♣"))       # 2
    defend(s, "9♣")
    s.apply(MOVE_PASS)     # 0
    s.apply(MOVE_PASS)     # 2
    assert s.hands[0].bit_count() == 6 and s.hands[0] & H("8♥")   # верх колоды - первому
    assert s.hands[2].bit_count() == 6
    assert s.hands[1].bit_count() == 5      # защитнику последняя карта - козырь
    assert not s.deck
    draws = [e for e in s.log if e[0] == "draw"]
    assert draws == [("draw", 0, 1, False), ("draw", 2, 1, False), ("draw", 1, 1, True)] \
        or draws[-1][3] is True


def test_draw_order_exact():
    s = make([["7♠", "Q♣", "A♦", "K♦", "J♦", "10♦"],
              ["8♠", "9♣", "A♣", "K♣", "J♣", "10♣"],
              ["7♣", "6♦", "7♦", "8♦", "9♦", "Q♦"]],
             deck=["6♥", "7♥", "8♥", "9♥", "10♥"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(MOVE_PASS)
    s.apply(A("7♣"))
    defend(s, "9♣")
    s.apply(MOVE_PASS)
    s.apply(MOVE_PASS)
    draws = [e for e in s.log if e[0] == "draw"]
    assert draws == [("draw", 0, 1, False), ("draw", 2, 1, False), ("draw", 1, 2, False)]
    assert [e[1] for e in draws] == [0, 2, 1]
    assert s.hands[0] & H("10♥") and s.hands[2] & H("9♥")
    assert s.hands[1] & H("8♥", "7♥") == H("8♥", "7♥")
    assert s.deck == [C.parse("6♥")]          # козырь уходит последним


def test_trump_card_goes_to_last_drawer_and_is_logged():
    s = make([["7♠", "Q♣", "K♣", "A♣", "J♣", "10♦"], ["8♠", "9♦", "J♦", "Q♦", "K♦"]],
             deck=["6♥", "10♣", "8♣"])
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(MOVE_PASS)
    assert s.hands[0] & H("8♣") and s.hands[1] & H("10♣", "6♥") == H("10♣", "6♥")
    assert ("draw", 1, 2, True) in s.log and ("draw", 0, 1, False) in s.log


# ---------- выход, дурак, ничья ----------

def test_out_and_fool():
    # колода пуста: 0 ходит последней картой, 1 бьёт - у 1 остаётся карта, он дурак
    s = make([["7♠"], ["8♠", "A♣"]], trump="♥")
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    assert s.over and s.fool == 1 and s.out == [0]
    assert s.outcome(0) == 1 and s.outcome(1) == -1


def test_draw_when_last_two_finish_together():
    s = make([["7♠"], ["8♠"]], trump="♥")
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    assert s.over and s.fool == DRAW
    assert s.outcome(0) == 0 and s.outcome(1) == 0


def test_defender_out_then_next_attacks():
    # трое, колода пуста: 1 отбился последней картой и вышел, ходит 2
    s = make([["7♠", "Q♣"], ["8♠"], ["J♦", "K♣"]], trump="♥")
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    assert s.out == [1] and not s.over
    assert s.attacker == 2 and s.defender == 0


def test_taker_keeps_cards_attacker_out_taker_fool():
    s = make([["7♠"], ["8♣", "A♣"]], trump="♥")
    s.apply(A("7♠"))
    s.apply(MOVE_TAKE)
    assert s.over and s.fool == 1


# ---------- переводной ----------

def test_transfer_allowed_same_rank_when_next_has_cards():
    s = make([["7♠", "Q♣"], ["7♦", "A♣"], ["9♦", "K♣", "J♣"]], deck=["6♥", "10♣"],
             transfer=True)
    s.apply(A("7♠"))
    assert T("7♦") in s.legal_moves()
    s.apply(T("7♦"))
    assert s.attacker == 1 and s.defender == 2 and s.turn == 2
    assert len(s.table) == 2 and s.undefended() == 2
    s.check()


def test_no_transfer_when_switched_off():
    s = make([["7♠", "Q♣"], ["7♦", "A♣"], ["9♦", "K♣", "J♣"]], deck=["6♥", "10♣"])
    s.apply(A("7♠"))
    assert not any(m[0] == TRANSFER for m in s.legal_moves())


def test_no_transfer_when_next_has_too_few_cards():
    s = make([["7♠", "Q♣"], ["7♦", "A♣"], ["9♦"]], deck=["6♥", "10♣"], transfer=True)
    s.apply(A("7♠"))
    assert not any(m[0] == TRANSFER for m in s.legal_moves())   # у 2 одна карта, нужно 2


def test_no_transfer_after_a_card_is_beaten():
    s = make([["7♠", "7♣", "Q♣"], ["8♠", "7♦", "A♣"], ["9♦", "K♣", "J♣", "J♠"]],
             deck=["6♥", "10♣"], transfer=True)
    s.apply(A("7♠"))
    s.apply(D("8♠"))
    s.apply(A("7♣"))
    assert s.turn == 1
    assert not any(m[0] == TRANSFER for m in s.legal_moves())


def test_transfer_back_in_two_player_game():
    s = make([["7♠", "7♣", "Q♣"], ["7♦", "A♣", "K♦", "Q♦"]], deck=["6♥", "10♣"], transfer=True)
    s.apply(A("7♠"))
    s.apply(T("7♦"))
    assert s.defender == 0 and s.turn == 0
    assert T("7♣") in s.legal_moves()
    s.apply(T("7♣"))
    assert s.defender == 1 and len(s.table) == 3


def test_defend_chosen_slot_after_transfer():
    s = make([["7♠", "Q♣"], ["7♦", "A♣"], ["9♦", "8♠", "J♣"]], deck=["6♥", "10♣"],
             transfer=True)
    s.apply(A("7♠"))
    s.apply(T("7♦"))
    moves = s.legal_moves()
    assert D("8♠", 0) in moves and D("9♦", 1) in moves
    assert D("8♠", 1) not in moves
    s.apply(D("9♦", 1))
    assert s.table[1][1] == C.parse("9♦") and s.turn == 2


# ---------- случайные партии ----------

def random_agent(rng):
    def agent(state):
        return rng.choice(state.legal_moves())
    return agent


@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.booleans())
def test_random_games_keep_invariants_and_end(seed, n, transfer, five):
    rng = random.Random(seed)
    s = State.new(Rules(players=n, transfer=transfer, first_bout_five=five), seed=seed)
    moves = 0
    while not s.over:
        s.check()
        legal = s.legal_moves()
        assert legal and len(set(legal)) == len(legal)
        p = s.turn
        if s.phase() == "attack":
            assert all(m[0] == ATTACK for m in legal)
        if s.phase() == "throw":
            assert MOVE_PASS in legal and p != s.defender
        if s.phase() == "defend":
            assert MOVE_TAKE in legal and p == s.defender
        s.apply(rng.choice(legal))
        moves += 1
        assert moves < 2000
    s.check()
    assert s.fool == DRAW or 0 <= s.fool < n
    assert len(s.out) == n - (0 if s.fool == DRAW else 1)
    assert sum(s.outcome(p) == -1 for p in range(n)) == (0 if s.fool == DRAW else 1)


@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans())
def test_clone_is_independent_and_plays_the_same(seed, n, transfer):
    rng = random.Random(seed)
    s = State.new(Rules(players=n, transfer=transfer), seed=seed)
    for _ in range(rng.randrange(0, 30)):
        if s.over:
            break
        s.apply(rng.choice(s.legal_moves()))
    c = s.clone()
    snapshot = (s.hands[:], s.deck[:], [p[:] for p in s.table], s.turn, s.discard)
    r1, r2 = random.Random(1), random.Random(1)
    while not c.over:
        c.apply(r1.choice(c.legal_moves()))
    assert (s.hands, s.deck, s.table, s.turn, s.discard) == snapshot
    d = s.clone()
    while not d.over:
        d.apply(r2.choice(d.legal_moves()))
    assert d.fool == c.fool and d.hands == c.hands


def test_play_helper_finishes():
    rng = random.Random(3)
    s = play(State.new(Rules(players=3), seed=3), [random_agent(rng)] * 3)
    assert s.over


def test_take_and_pass_kinds():
    assert MOVE_TAKE[0] == TAKE and MOVE_PASS[0] == PASS
