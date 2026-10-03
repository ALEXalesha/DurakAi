"""Движок партии «Дурак»: подкидной и переводной, от 2 до 4 игроков.

Партия - последовательность ходов одного игрока за раз. Кто ходит, решает движок:

- стол пуст -> ходит главный атакующий (ATTACK, любая карта);
- на столе есть не побитая карта и защитник не сказал «беру» -> защитник
  (DEFEND карта на место, TRANSFER в переводном, TAKE);
- все карты побиты или защитник берёт -> подкидывают по очереди, начиная с главного
  атакующего, все с картами, кроме защитника (ATTACK картой достоинства со стола или PASS).
  Подкинутая карта даёт всем новый круг. Когда все отказались или подкидывать уже нельзя
  (на столе 6 карт, или 5 в первом отбое, или не побитых столько, сколько карт у защитника),
  отбой кончается: «бито» или защитник забирает стол.

Игрок без подходящей карты всё равно получает очередь, и единственный его ход - PASS.
Так очередь не выдаёт, у кого какие карты: пропуск «нечем» и «не хочу» выглядят одинаково.

После отбоя добор до 6: главный атакующий, потом остальные подкидывавшие, защитник
последним. Кто остался без карт при пустой колоде - вышел. Последний с картами - дурак;
если последние двое вышли одновременно - ничья (fool == -1).

Все публичные события пишутся в журнал log - из него строится то, что видит игрок
(game.core.observation). Для поиска журнал отключается (log=None), копии дешёвые.
"""
from game.core import cards as C

ATTACK, DEFEND, TRANSFER, TAKE, PASS = range(5)
KIND_NAMES = ("attack", "defend", "transfer", "take", "pass")

MOVE_TAKE = (TAKE, -1, -1)
MOVE_PASS = (PASS, -1, -1)

DRAW = -1   # fool в ничьей


class Rules:
    """Настройки правил. Неизменяемы по смыслу: копии состояния делят один объект."""
    __slots__ = ("players", "transfer", "first_bout_five")

    def __init__(self, players=2, transfer=False, first_bout_five=False):
        if not 2 <= players <= 4:
            raise ValueError("игроков от 2 до 4")
        self.players = players
        self.transfer = transfer
        self.first_bout_five = first_bout_five

    def __eq__(self, other):
        return isinstance(other, Rules) and self.key() == other.key()

    def __hash__(self):
        return hash(self.key())

    def key(self):
        return (self.players, self.transfer, self.first_bout_five)

    def __repr__(self):
        return f"Rules(players={self.players}, transfer={self.transfer}, first_bout_five={self.first_bout_five})"


def first_attacker(hands, trump):
    """Младший козырь ходит первым. Если козырей ни у кого нет - младшая карта."""
    best = None
    for p, h in enumerate(hands):
        t = h & C.SUIT_MASK[trump]
        if t:
            low = (t & -t).bit_length() - 1
            if best is None or low < best[0]:
                best = (low, p)
    if best is not None:
        return best[1]
    keyed = []
    for p, h in enumerate(hands):
        if h:
            keyed.append((min((C.rank(c), C.suit(c)) for c in C.cards_of(h)), p))
    return min(keyed)[1]


class State:
    __slots__ = ("rules", "n", "hands", "deck", "trump", "trump_card", "discard", "table",
                 "attacker", "defender", "taking", "passed", "out", "bout", "turn",
                 "fool", "log", "moves_made")

    # ---------- создание ----------

    @classmethod
    def new(cls, rules=None, seed=0, first=None, log=True):
        """Новая партия. first - кто ходит первым; None - младший козырь."""
        rules = rules or Rules()
        deck = C.new_deck(seed)
        hands, deck = C.deal(deck, rules.players)
        return cls.from_parts(rules, hands, deck, first=first, log=log)

    @classmethod
    def from_parts(cls, rules, hands, deck, first=None, trump=None, log=True):
        """Партия из готовых рук и колоды (верх колоды в конце, deck[0] - открытый козырь).
        Нужна для ручных раздач в проверках. trump задаётся, если колода пуста."""
        s = cls.__new__(cls)
        s.rules = rules
        s.n = rules.players
        s.hands = list(hands)
        s.deck = list(deck)
        if s.deck:
            s.trump_card = s.deck[0]
            s.trump = C.suit(s.trump_card)
        else:
            if trump is None:
                raise ValueError("при пустой колоде козырь задаётся явно")
            s.trump_card = -1
            s.trump = trump
        used = 0
        for h in s.hands:
            used |= h
        s.discard = C.ALL & ~used & ~C.mask(s.deck)
        s.table = []
        s.taking = False
        s.passed = 0
        s.out = [p for p in range(s.n) if not s.hands[p] and not s.deck]
        s.bout = 0
        s.fool = None
        s.moves_made = 0
        s.log = [] if log else None
        if s._check_over():
            s.attacker = s.defender = -1
            s.turn = -1
            return s
        s.attacker = first if first is not None else first_attacker(s.hands, s.trump)
        if s.attacker in s.out:
            s.attacker = s.next_active(s.attacker)
        s.defender = s.next_active(s.attacker)
        s.turn = s.attacker
        if s.log is not None:
            s.log.append(("start", s.attacker, s.trump_card, s.trump,
                          tuple(h.bit_count() for h in s.hands)))
        return s

    def clone(self, log=False):
        """Копия для поиска. Журнал по умолчанию не копируется - он нужен только живой партии."""
        s = State.__new__(State)
        s.rules = self.rules
        s.n = self.n
        s.hands = self.hands[:]
        s.deck = self.deck[:]
        s.trump = self.trump
        s.trump_card = self.trump_card
        s.discard = self.discard
        s.table = [pair[:] for pair in self.table]
        s.attacker = self.attacker
        s.defender = self.defender
        s.taking = self.taking
        s.passed = self.passed
        s.out = self.out[:]
        s.bout = self.bout
        s.turn = self.turn
        s.fool = self.fool
        s.moves_made = self.moves_made
        s.log = (self.log[:] if self.log is not None else None) if log else None
        return s

    # ---------- справки ----------

    @property
    def over(self):
        return self.fool is not None

    def active(self, p):
        return p not in self.out

    def next_active(self, p):
        """Следующий по кругу игрок, который ещё в игре (не p, если есть другие)."""
        for i in range(1, self.n + 1):
            q = (p + i) % self.n
            if q not in self.out:
                return q
        return p

    def limit(self):
        return 5 if (self.rules.first_bout_five and self.bout == 0) else 6

    def table_mask(self):
        m = 0
        for a, d in self.table:
            m |= 1 << a
            if d >= 0:
                m |= 1 << d
        return m

    def table_ranks(self):
        """Маска всех карт тех достоинств, что лежат на столе."""
        m = 0
        for a, d in self.table:
            m |= C.RANK_MASK[a % 9]
            if d >= 0:
                m |= C.RANK_MASK[d % 9]
        return m

    def undefended(self):
        return sum(1 for a, d in self.table if d < 0)

    def throw_order(self):
        """Порядок подкидывания: главный атакующий, дальше по кругу, без защитника."""
        out = []
        for i in range(self.n):
            q = (self.attacker + i) % self.n
            if q != self.defender and q not in self.out:
                out.append(q)
        return out

    def can_throw_more(self):
        """Публичное условие: можно ли вообще подкинуть ещё карту (не глядя в руки)."""
        return (len(self.table) < self.limit()
                and self.undefended() < self.hands[self.defender].bit_count())

    def phase(self):
        if self.over:
            return "over"
        if not self.table:
            return "attack"
        if not self.taking and self.undefended():
            return "defend"
        return "throw"

    def outcome(self, p):
        """+1 - не дурак, -1 - дурак, 0 - ничья. Только для оконченной партии."""
        if self.fool == DRAW:
            return 0
        return -1 if self.fool == p else 1

    # ---------- ходы ----------

    def legal_moves(self):
        if self.over:
            return []
        p = self.turn
        hand = self.hands[p]
        ph = self.phase()
        if ph == "attack":
            return [(ATTACK, c, -1) for c in C.cards_of(hand)]
        if ph == "defend":
            moves = []
            trump = self.trump
            for slot, (a, d) in enumerate(self.table):
                if d >= 0:
                    continue
                sa = a // 9
                same = hand & C.SUIT_MASK[sa]
                for c in C.cards_of(same):
                    if c % 9 > a % 9:
                        moves.append((DEFEND, c, slot))
                if sa != trump:
                    for c in C.cards_of(hand & C.SUIT_MASK[trump]):
                        moves.append((DEFEND, c, slot))
            if self._transfer_allowed():
                r = self.table[0][0] % 9
                for c in C.cards_of(hand & C.RANK_MASK[r]):
                    moves.append((TRANSFER, c, -1))
            moves.append(MOVE_TAKE)
            return moves
        # подкидывание
        moves = [(ATTACK, c, -1) for c in C.cards_of(hand & self.table_ranks())]
        moves.append(MOVE_PASS)
        return moves

    def _transfer_allowed(self):
        if not self.rules.transfer or self.taking:
            return False
        r = self.table[0][0] % 9
        for a, d in self.table:
            if d >= 0 or a % 9 != r:
                return False
        nxt = self.next_active(self.defender)
        if nxt == self.defender:
            return False
        k = len(self.table) + 1
        return k <= self.limit() and self.hands[nxt].bit_count() >= k

    def apply(self, move):
        """Сделать ход. Неверный ход - ValueError, состояние не меняется."""
        if move not in self.legal_moves():
            raise ValueError(f"недопустимый ход {move} для игрока {self.turn}")
        self.apply_unchecked(move)

    def apply_unchecked(self, move):
        """Ход без проверки допустимости - для поиска, который берёт ходы из legal_moves()."""
        kind, c, slot = move
        p = self.turn
        log = self.log
        self.moves_made += 1
        if kind == ATTACK:
            self.hands[p] &= ~(1 << c)
            self.table.append([c, -1])
            self.passed = 0
            if log is not None:
                log.append(("attack", p, c))
        elif kind == DEFEND:
            self.hands[p] &= ~(1 << c)
            self.table[slot][1] = c
            self.passed = 0
            if log is not None:
                log.append(("defend", p, c, slot))
        elif kind == TRANSFER:
            self.hands[p] &= ~(1 << c)
            self.table.append([c, -1])
            self.attacker = p
            self.defender = self.next_active(p)
            self.passed = 0
            if log is not None:
                log.append(("transfer", p, c))
        elif kind == TAKE:
            self.taking = True
            self.passed = 0
            if log is not None:
                log.append(("take", p))
        else:  # PASS
            self.passed |= 1 << p
            if log is not None:
                log.append(("pass", p))
        self._settle()

    # ---------- ход очереди и конец отбоя ----------

    def _settle(self):
        if not self.table:
            self.turn = self.attacker
            return
        if not self.taking and self.undefended():
            self.turn = self.defender
            return
        if self.can_throw_more():
            for q in self.throw_order():
                if not (self.passed >> q) & 1 and self.hands[q]:
                    self.turn = q
                    return
        self._finish_bout()

    def _finish_bout(self):
        log = self.log
        tm = self.table_mask()
        order = self.throw_order()
        d = self.defender
        if self.taking:
            self.hands[d] |= tm
            if log is not None:
                log.append(("pickup", d, tm))
        else:
            self.discard |= tm
            if log is not None:
                log.append(("bito", tm))
        self.table = []
        self.passed = 0
        self.bout += 1
        # добор: главный атакующий, остальные подкидывавшие, защитник последним
        for q in order + [d]:
            need = C.HAND - self.hands[q].bit_count()
            if need <= 0 or not self.deck:
                continue
            k = min(need, len(self.deck))
            got_trump = k == len(self.deck)
            for _ in range(k):
                self.hands[q] |= 1 << self.deck.pop()
            if log is not None:
                log.append(("draw", q, k, got_trump))
        # выход без карт при пустой колоде
        if not self.deck:
            for q in order + [d]:
                if not self.hands[q] and q not in self.out:
                    self.out.append(q)
                    if log is not None:
                        log.append(("out", q))
        took = self.taking
        self.taking = False
        if self._check_over():
            self.turn = -1
            return
        if took:
            att = self.next_active(d)
        else:
            att = d if d not in self.out else self.next_active(d)
        self.attacker = att
        self.defender = self.next_active(att)
        self.turn = att

    def _check_over(self):
        alive = [p for p in range(self.n) if p not in self.out]
        if len(alive) <= 1:
            self.fool = alive[0] if alive else DRAW
            if self.log is not None:
                self.log.append(("over", self.fool))
            return True
        return False

    # ---------- проверка целостности ----------

    def check(self):
        """Инварианты: все 36 карт на месте, без повторов; очередь осмысленна."""
        seen = 0
        total = 0
        parts = list(self.hands) + [C.mask(self.deck), self.discard, self.table_mask()]
        for m in parts:
            if seen & m:
                raise AssertionError("карта в двух местах")
            seen |= m
            total += m.bit_count()
        if seen != C.ALL or total != 36:
            raise AssertionError(f"карт {total}, а не 36")
        if len(self.deck) != len(set(self.deck)):
            raise AssertionError("повтор в колоде")
        if self.deck and self.deck[0] != self.trump_card:
            raise AssertionError("козырь не на дне колоды")
        if len(self.table) > 6:
            raise AssertionError("на столе больше 6 карт")
        for a, d in self.table:
            if d >= 0 and not C.beats(a, d, self.trump):
                raise AssertionError("защита не бьёт атаку")
        if not self.over:
            if self.turn in self.out or self.turn < 0:
                raise AssertionError("ходит вышедший")
            if self.attacker == self.defender:
                raise AssertionError("атакует сам себя")
        return True


def play(state, agents, max_moves=2000):
    """Доиграть партию: agents[p](state) -> ход. Возвращает state."""
    for _ in range(max_moves):
        if state.over:
            return state
        state.apply(agents[state.turn](state))
    raise RuntimeError("партия не кончилась за max_moves ходов")
