"""Игроки-ИИ. Каждый получает только наблюдение (game.core.observation) и зерно.

choose(obs, seed) -> ход из obs.legal. Одно наблюдение и одно зерно - один ход: так
проверяется закон честности и пересчитывается паспорт модели.

Уровни:
- random - случайный допустимый ход (для проверок силы);
- novice - простые правила: ходить младшей, отбиваться младшей подходящей, беречь козыри;
- medium - учёт карт и небольшой поиск по раскладкам (game.ai.search);
- strong - учёт карт, поиск по раскладкам с оценкой сетью, точный перебор в конце.
"""
import random

from game.core import cards as C
from game.core.durak import ATTACK, DEFEND, MOVE_PASS, MOVE_TAKE, PASS, TAKE, TRANSFER

LEVELS = ("random", "novice")


def strength(c, trump):
    """Цена карты: достоинство, козыри дороже любой некозырной."""
    return c % 9 + (9 if c // 9 == trump else 0)


def novice_move(legal, hand, trump, deck_size, table, taking):
    """Ход простого бота. Отдельная функция от состояния-наблюдения: её зовёт и поиск
    в своих раскладках, где наблюдения нет."""
    if len(legal) == 1:
        return legal[0]
    kind0 = legal[0][0]
    if kind0 == ATTACK and MOVE_PASS not in legal:
        # первый ход отбоя: младшая некозырная, при равенстве - та, что парная
        best = None
        for m in legal:
            c = m[1]
            pair = (hand & C.RANK_MASK[c % 9]).bit_count() > 1
            key = (strength(c, trump), not pair, c)
            if best is None or key < best[0]:
                best = (key, m)
        return best[1]
    if MOVE_PASS in legal:
        # подкидывание: дешёвые некозырные; в конце колоды - любые некозырные
        cheap = None
        for m in legal:
            if m[0] != ATTACK:
                continue
            c = m[1]
            if c // 9 == trump:
                continue
            if deck_size > 0 and c % 9 > 4 and not taking:
                continue              # валет и старше бережём, пока есть колода
            if cheap is None or strength(c, trump) < strength(cheap[1], trump):
                cheap = m
        return cheap if cheap is not None else MOVE_PASS
    # защита
    transfers = [m for m in legal if m[0] == TRANSFER and m[1] // 9 != trump]
    if transfers:
        return min(transfers, key=lambda m: strength(m[1], trump))
    defends = [m for m in legal if m[0] == DEFEND]
    undefended_slots = {i for i, (a, d) in enumerate(table) if d < 0}
    if {m[2] for m in defends} != undefended_slots:
        return MOVE_TAKE           # что-то не побить вовсе - нет смысла тратить карты
    best = min(defends, key=lambda m: (strength(m[1], trump), m[2]))
    c = best[1]
    if c // 9 == trump and deck_size > 6 and c % 9 >= 5:
        attack = table[best[2]][0]
        if attack // 9 != trump and len(table) <= 2:
            return MOVE_TAKE       # старшим козырем мелочь не бьём, пока колода большая
    return best


class RandomAgent:
    level = "random"

    def choose(self, obs, seed=0):
        return random.Random(seed).choice(obs.legal)


class NoviceAgent:
    level = "novice"

    def choose(self, obs, seed=0):
        return novice_move(list(obs.legal), obs.hand, obs.trump, obs.deck_size,
                           obs.table, obs.taking)


def make_agent(level, **kw):
    if level == "random":
        return RandomAgent()
    if level == "novice":
        return NoviceAgent()
    if level in ("medium", "strong"):
        from game.ai.search import SearchAgent
        return SearchAgent.for_level(level, **kw)
    raise ValueError(f"нет уровня {level}")


__all__ = ["LEVELS", "make_agent", "novice_move", "strength", "RandomAgent", "NoviceAgent",
           "PASS", "TAKE"]
