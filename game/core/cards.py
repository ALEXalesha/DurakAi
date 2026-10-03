"""Карты, колода и раздача.

Карта - число 0..35: масть * 9 + достоинство. Масти: 0 пики, 1 трефы, 2 бубны, 3 червы.
Достоинства 0..8: 6, 7, 8, 9, 10, В, Д, К, Т. Рука - битовая маска (int): бит c стоит,
если карта c в руке. Маски быстры в переборе, а ИИ перебирает очень много позиций.

Колода - список, верх в конце (берётся pop()), низ в начале: deck[0] - открытый козырь,
он уходит последним.
"""
import numpy as np

SUITS = "♠♣♦♥"
RANKS = ("6", "7", "8", "9", "10", "J", "Q", "K", "A")
RANKS_RU = ("6", "7", "8", "9", "10", "В", "Д", "К", "Т")
HAND = 6
ALL = (1 << 36) - 1


def card(suit, rank):
    return suit * 9 + rank


def suit(c):
    return c // 9


def rank(c):
    return c % 9


def name(c):
    return RANKS[rank(c)] + SUITS[suit(c)]


def parse(text):
    return card(SUITS.index(text[-1]), RANKS.index(text[:-1]))


def beats(attack, defense, trump):
    """Бьёт ли defense карту attack при козырной масти trump."""
    sa, sd = attack // 9, defense // 9
    if sa == sd:
        return defense % 9 > attack % 9
    return sd == trump


def mask(cs):
    m = 0
    for c in cs:
        m |= 1 << c
    return m


def cards_of(m):
    """Карты маски по возрастанию."""
    out = []
    while m:
        low = m & -m
        out.append(low.bit_length() - 1)
        m ^= low
    return out


def count(m):
    return m.bit_count()


SUIT_MASK = tuple(((1 << 9) - 1) << (9 * s) for s in range(4))
RANK_MASK = tuple(sum(1 << (9 * s + r) for s in range(4)) for r in range(9))


def new_deck(seed):
    """Перетасованная колода. Одно зерно - одна колода."""
    rng = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)
    return [int(c) for c in rng.permutation(36)]


def deal(deck, n):
    """По одной карте каждому, пока у всех не станет по 6. Возвращает (руки-маски, остаток)."""
    deck = list(deck)
    hands = [0] * n
    for _ in range(HAND):
        for p in range(n):
            hands[p] |= 1 << deck.pop()
    return hands, deck
