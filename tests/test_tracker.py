"""Учёт карт: вероятности по рукам и колоде, выводы из «не отбился», раскладки."""
import random

import numpy as np
from hypothesis import given, settings, strategies as st

from game.ai import tracker
from game.core import cards as C
from game.core.durak import MOVE_PASS, MOVE_TAKE, Rules, State
from game.core.observation import observation
from tests.test_durak import A, D, H, make
from tests.test_honesty import random_position


@settings(max_examples=120)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.integers(0, 3))
def test_rows_sum_to_one_columns_match_counts(seed, n, transfer, who):
    s = random_position(seed, n, transfer)
    if s is None:
        return
    p = who % n
    o = observation(s, p)
    P = tracker.belief(o)
    assert P.shape == (36, n + 2)
    assert np.allclose(P.sum(axis=1), 1.0)
    assert (P >= -1e-12).all()
    cols = P.sum(axis=0)
    for q in range(n):
        assert abs(cols[q] - s.hands[q].bit_count()) < 1e-6
    assert abs(cols[n] - len(s.deck)) < 1e-6
    assert abs(cols[n + 1] - (s.discard | s.table_mask()).bit_count()) < 1e-6


@settings(max_examples=120)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.integers(0, 3))
def test_impossible_cards_get_zero_and_true_place_positive(seed, n, transfer, who):
    s = random_position(seed, n, transfer)
    if s is None:
        return
    p = who % n
    P = tracker.belief(observation(s, p))
    for c in range(36):
        # настоящее место карты всегда возможно
        if s.hands[p] >> c & 1:
            assert P[c, p] == 1.0
        elif (s.discard | s.table_mask()) >> c & 1:
            assert P[c, n + 1] == 1.0
        else:
            true = next((q for q in range(n) if s.hands[q] >> c & 1), n)
            assert P[c, true] > 0
            assert P[c, p] == 0.0 and P[c, n + 1] == 0.0
    if s.deck:
        assert P[s.trump_card, n] == 1.0


def test_two_players_empty_deck_everything_known():
    s = make([["7♠", "Q♣", "K♦"], ["8♠", "A♣", "J♦", "9♥"]], trump="♥")
    P = tracker.belief(observation(s, 0))
    for c in C.cards_of(s.hands[1]):
        assert P[c, 1] == 1.0


def test_not_beating_lowers_higher_cards_and_trumps():
    # 0 ходит 9♠, 1 берёт. Пики старше 9 и козыри (червы) у 1 теперь маловероятны.
    s = make([["9♠", "6♣", "7♣", "8♣", "9♣", "10♣"],
              ["6♦", "7♦", "8♦", "9♦", "10♦", "J♦"]],
             deck=["6♥", "J♣", "Q♣", "K♣", "A♣", "J♠", "Q♠", "K♠", "A♠", "7♥", "8♥", "9♥",
                   "10♥", "J♥", "Q♥", "K♥", "A♥", "6♠", "7♠", "8♠", "10♠", "Q♦", "K♦", "A♦"])
    o_before = observation(s, 0)
    P0 = tracker.belief(o_before)
    s.apply(A("9♠"))
    s.apply(MOVE_TAKE)
    s.apply(MOVE_PASS)
    P1 = tracker.belief(observation(s, 0))
    for name in ("10♠", "A♠", "7♥", "A♥"):
        c = C.parse(name)
        assert P1[c, 1] < 0.5 * P0[c, 1], name
    # младшие пики и другие масти - наоборот, вероятнее
    for name in ("6♠", "K♦"):
        c = C.parse(name)
        assert P1[c, 1] > P0[c, 1], name


def test_beaters():
    t = 3
    assert tracker.beaters(C.parse("9♠"), t) == H("10♠", "J♠", "Q♠", "K♠", "A♠") | C.SUIT_MASK[3]
    assert tracker.beaters(C.parse("K♥"), t) == H("A♥")


@settings(max_examples=80)
@given(st.integers(0, 10 ** 6), st.integers(2, 4), st.booleans(), st.integers(0, 10 ** 6))
def test_sample_is_consistent_with_observation(seed, n, transfer, seed2):
    s = random_position(seed, n, transfer)
    if s is None:
        return
    p = s.turn
    o = observation(s, p)
    hands, deck = tracker.sample(o, np.random.default_rng(seed2))
    assert hands[p] == s.hands[p]
    assert [h.bit_count() for h in hands] == [h.bit_count() for h in s.hands]
    assert len(deck) == len(s.deck)
    if s.deck:
        assert deck[0] == s.trump_card
    for q in range(n):
        assert hands[q] & o.known[q] == o.known[q]
    # вместе с отбоем и столом - ровно 36 разных карт
    allc = 0
    for h in hands:
        assert allc & h == 0
        allc |= h
    assert allc & C.mask(deck) == 0
    allc |= C.mask(deck) | s.discard | s.table_mask()
    assert allc == C.ALL


def test_sample_follows_belief():
    """Частоты в раскладках близки к вероятностям учёта."""
    s = make([["9♠", "6♣", "7♣", "8♣", "9♣", "10♣"],
              ["6♦", "7♦", "8♦", "9♦", "10♦", "J♦"]],
             deck=["6♥", "J♣", "Q♣", "K♣", "A♣", "J♠", "Q♠", "K♠", "A♠", "7♥", "8♥", "9♥",
                   "10♥", "J♥", "Q♥", "K♥", "A♥", "6♠", "7♠", "8♠", "10♠", "Q♦", "K♦", "A♦"])
    s.apply(A("9♠"))
    s.apply(MOVE_TAKE)
    s.apply(MOVE_PASS)
    o = observation(s, 0)
    P = tracker.belief(o)
    rng = np.random.default_rng(0)
    freq = np.zeros(36)
    N = 1500
    for _ in range(N):
        hands, _ = tracker.sample(o, rng)
        for c in C.cards_of(hands[1] & ~o.known[1]):
            freq[c] += 1
    freq /= N
    unseen = C.cards_of(o.unseen())
    err = max(abs(freq[c] - P[c, 1]) for c in unseen)
    assert err < 0.08, err
