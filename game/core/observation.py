"""Что видит игрок: единственное, что получает ИИ.

observation(state, player) собирает своё (рука) и публичное (размеры рук, стол, отбой,
козырь, размер колоды, очередь, журнал публичных событий). Порядок колоды и чужие руки
сюда не попадают. Наблюдение неизменяемо и не держит ссылок на состояние, поэтому ИИ не
может подсмотреть даже случайно.

known[q] - карты, про которые все знают, что они у игрока q: взятые со стола и открытый
козырь у того, кто его добрал, пока он их не сыграл. Это следует из журнала, а не из рук.
"""
from dataclasses import dataclass

from game.core import cards as C


@dataclass(frozen=True)
class Observation:
    player: int
    n: int
    rules: tuple            # (игроков, переводной, первый отбой 5)
    hand: int               # своя рука, маска
    hand_sizes: tuple
    deck_size: int
    trump: int
    trump_card: int         # открытый козырь (известен и после того, как его добрали)
    discard: int
    table: tuple            # ((атака, защита или -1), ...)
    attacker: int
    defender: int
    turn: int
    taking: bool
    passed: int
    out: tuple
    bout: int
    fool: object            # None, номер дурака или -1 (ничья)
    legal: tuple            # свои допустимые ходы, если сейчас мой ход
    known: tuple            # маски известных всем карт у каждого игрока
    log: tuple              # публичные события партии

    @property
    def over(self):
        return self.fool is not None

    def phase(self):
        if self.fool is not None:
            return "over"
        if not self.table:
            return "attack"
        if not self.taking and any(d < 0 for _, d in self.table):
            return "defend"
        return "throw"

    def table_mask(self):
        m = 0
        for a, d in self.table:
            m |= 1 << a
            if d >= 0:
                m |= 1 << d
        return m

    def unseen(self):
        """Карты, которых игрок не видит: у соперников (кроме известных) и в колоде."""
        seen = self.hand | self.discard | self.table_mask()
        if self.deck_size and self.trump_card >= 0:
            seen |= 1 << self.trump_card       # открытый козырь на дне колоды
        for q, k in enumerate(self.known):
            if q != self.player:
                seen |= k
        return C.ALL & ~seen


def known_cards(log, n, trump_card):
    known = [0] * n
    for e in log:
        kind = e[0]
        if kind in ("attack", "defend", "transfer"):
            known[e[1]] &= ~(1 << e[2])
        elif kind == "pickup":
            known[e[1]] |= e[2]
        elif kind == "draw" and e[3] and trump_card >= 0:
            known[e[1]] |= 1 << trump_card
    return tuple(known)


def observation(state, player):
    log = tuple(state.log) if state.log is not None else ()
    return Observation(
        player=player,
        n=state.n,
        rules=state.rules.key(),
        hand=state.hands[player],
        hand_sizes=tuple(h.bit_count() for h in state.hands),
        deck_size=len(state.deck),
        trump=state.trump,
        trump_card=state.trump_card,
        discard=state.discard,
        table=tuple((a, d) for a, d in state.table),
        attacker=state.attacker,
        defender=state.defender,
        turn=state.turn,
        taking=state.taking,
        passed=state.passed,
        out=tuple(state.out),
        bout=state.bout,
        fool=state.fool,
        legal=tuple(state.legal_moves()) if state.turn == player else (),
        known=known_cards(log, state.n, state.trump_card),
        log=log,
    )
