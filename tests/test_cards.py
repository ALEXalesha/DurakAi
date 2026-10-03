"""Карты и колода: 36 карт, перетасовка с зерном, раздача, козырь, кто кого бьёт."""
from hypothesis import given, strategies as st

from game.core import cards as C

card = st.integers(0, 35)
suit = st.integers(0, 3)


def test_deck_has_36_distinct_cards():
    deck = C.new_deck(1)
    assert sorted(deck) == list(range(36))


def test_same_seed_same_deck_other_seed_other_deck():
    assert C.new_deck(5) == C.new_deck(5)
    assert C.new_deck(5) != C.new_deck(6)


def test_names_and_parts():
    assert C.name(C.card(0, 0)) == "6♠"
    assert C.name(C.card(3, 8)) == "A♥"
    assert C.name(C.card(2, 4)) == "10♦"
    for c in range(36):
        assert C.card(C.suit(c), C.rank(c)) == c
    assert C.parse("10♦") == C.card(2, 4) and C.parse("Q♣") == C.card(1, 6)


def test_deal_six_each_trump_is_bottom_card():
    for n in (2, 3, 4):
        deck = C.new_deck(3)
        bottom = deck[0]
        hands, rest = C.deal(deck, n)
        assert len(hands) == n and all(C.count(h) == 6 for h in hands)
        assert len(rest) == 36 - 6 * n and rest[0] == bottom
        union = 0
        for h in hands:
            assert union & h == 0
            union |= h
        assert sorted(C.cards_of(union) + rest) == list(range(36))


def test_beats_examples():
    t = 3  # козырь - червы
    assert C.beats(C.parse("7♠"), C.parse("9♠"), t)
    assert not C.beats(C.parse("9♠"), C.parse("7♠"), t)
    assert not C.beats(C.parse("7♠"), C.parse("A♣"), t)       # другая масть, не козырь
    assert C.beats(C.parse("A♠"), C.parse("6♥"), t)           # любой козырь бьёт некозырную
    assert not C.beats(C.parse("7♥"), C.parse("A♠"), t)       # козырь бьётся только козырем
    assert C.beats(C.parse("7♥"), C.parse("8♥"), t)
    assert not C.beats(C.parse("8♥"), C.parse("7♥"), t)


@given(card, card, suit)
def test_beats_is_antisymmetric_and_irreflexive(a, b, t):
    assert not (C.beats(a, b, t) and C.beats(b, a, t))
    assert not C.beats(a, a, t)


@given(card, card, suit)
def test_beats_law(a, b, t):
    same = C.suit(a) == C.suit(b)
    expected = (same and C.rank(b) > C.rank(a)) or (C.suit(b) == t and C.suit(a) != t)
    assert C.beats(a, b, t) == expected


@given(st.sets(card))
def test_mask_roundtrip(cs):
    m = C.mask(cs)
    assert C.cards_of(m) == sorted(cs) and C.count(m) == len(cs)
