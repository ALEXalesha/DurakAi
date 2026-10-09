"""Поиск по раскладкам (PIMC) и точный перебор в конце.

Игрок не видит чужих карт, поэтому поиск идёт так:

1. Учёт карт (game.ai.tracker) даёт вероятность каждой невидимой карты в каждом месте.
2. Много раз раскладываем невидимые карты по рукам соперников и по колоде - каждая
   раскладка не противоречит известному (детерминизация).
3. В каждой раскладке карты видны, и каждый свой ход проверяется: ход делается, отбой
   доигрывается простыми правилами за всех, позиция на границе отбоя оценивается -
   сетью (сильный) или формулой (средний). Ход с лучшей средней оценкой и выбирается.
4. Когда колода пуста и в игре двое, неизвестного не остаётся: все невидимые карты - у
   соперника. Тогда партия просчитывается до конца точно (минимакс с запоминанием).

Все раскладки в одном решении - из генератора с зерном хода, поэтому одно наблюдение и одно
зерно дают один ход. Время ограничено: при time_limit поиск останавливается раньше, но
не меньше двух раскладок.
"""
import time

import numpy as np

from game.ai import tracker
from game.ai.agents import novice_move, strength
from game.core import cards as C
from game.core.durak import DRAW, Rules, State

WIN, LOSS = 1.0, -1.0


def state_from(obs, hands, deck):
    """Полное состояние из наблюдения и одной раскладки невидимого."""
    s = State.__new__(State)
    s.rules = Rules(*obs.rules)
    s.n = obs.n
    s.hands = list(hands)
    s.deck = list(deck)
    s.trump = obs.trump
    s.trump_card = obs.trump_card
    s.discard = obs.discard
    s.table = [[a, d] for a, d in obs.table]
    s.attacker = obs.attacker
    s.defender = obs.defender
    s.taking = obs.taking
    s.passed = obs.passed
    s.out = list(obs.out)
    s.bout = obs.bout
    s.turn = obs.turn
    s.fool = obs.fool
    s.moves_made = 0
    s.log = None
    return s


def value_of_outcome(s, me):
    if s.fool == DRAW:
        return 0.0
    return LOSS if s.fool == me else WIN


def default_move(s):
    legal = s.legal_moves()
    return novice_move(legal, s.hands[s.turn], s.trump, len(s.deck), s.table, s.taking)


def finish_bout(s, limit=200):
    """Доиграть текущий отбой простыми правилами за всех. s меняется."""
    bout = s.bout
    for _ in range(limit):
        if s.over or (s.bout != bout and not s.table):
            return s
        s.apply_unchecked(default_move(s))
    return s


def heuristic(s, me):
    """Оценка формулой: меньше карт и сильнее карты - лучше. От -1 до 1."""
    t = s.trump
    n_alive = 0
    others = 0.0
    mine = 0.0
    for q in range(s.n):
        if q in s.out:
            continue
        bad = 0.0
        for c in C.cards_of(s.hands[q]):
            bad += 0.8 - strength(c, t) / 17.0
        if q == me:
            mine = bad
        else:
            others += bad
            n_alive += 1
    if me in s.out:
        return WIN
    if n_alive == 0:
        return LOSS
    weight = 0.35 + 0.65 * (1.0 - len(s.deck) / 24.0)
    return float(np.tanh(0.45 * weight * (others / n_alive - mine)))


class Evaluator:
    """Оценка позиции на границе отбоя: сеть или формула."""

    def __init__(self, net=None):
        self.net = net

    def __call__(self, states, me):
        out = np.empty(len(states))
        todo = []
        for i, s in enumerate(states):
            if s.over:
                out[i] = value_of_outcome(s, me)
            elif self.net is None:
                out[i] = heuristic(s, me)
            else:
                todo.append(i)
        if todo:
            from game.ai.net import FEATURES, features
            X = np.empty((len(todo), FEATURES), np.float32)
            for j, i in enumerate(todo):
                features(states[i], me, X[j])
            out[todo] = self.net.predict(X)
        return out


# ---------- точный перебор: колода пуста, в игре двое ----------

class Exact:
    """Минимакс с запоминанием для двоих при пустой колоде - карты всех известны.
    Значения -1/0/1; ветка обрывается, как только найден выигрыш. Если узлов больше
    node_limit, поднят флаг stop или прошёл срок deadline (time.perf_counter) - отказ
    (None), и решает обычный поиск. Флаг и срок смотрятся каждые 64 узла: без них перебор
    шёл до 2.8 с при пределе хода 1.5 с, и закрытие окна могло не уложиться в 2 с."""

    def __init__(self, node_limit=20000):
        self.node_limit = node_limit

    def solve(self, s, me, stop=None, deadline=None):
        self.memo = {}
        self.onpath = set()
        self.nodes = 0
        self.me = me
        self.stop = stop
        self.deadline = deadline
        try:
            scores = []
            for m in self._ordered(s):
                c = s.clone()
                c.apply_unchecked(m)
                scores.append((m, self._value(c)))
            return scores
        except _TooBig:
            return None

    def _key(self, s):
        return (tuple(s.hands), tuple((a, d) for a, d in s.table), s.attacker, s.defender,
                s.taking, s.passed, s.turn)

    def _ordered(self, s):
        legal = s.legal_moves()
        first = default_move(s)
        return [first] + [m for m in legal if m != first]

    def _value(self, s):
        if s.over:
            return value_of_outcome(s, self.me)
        key = self._key(s)
        v = self.memo.get(key)
        if v is not None:
            return v
        if key in self.onpath:
            # В переводном вдвоём карты могут ходить по кругу: взял - перевёл обратно -
            # взял. Повтор позиции на пути считается ничьей, иначе перебор не кончится.
            return 0.0
        self.nodes += 1
        if self.nodes > self.node_limit:
            raise _TooBig
        if self.nodes % 64 == 0 and ((self.stop is not None and self.stop.is_set()) or
                                     (self.deadline is not None and time.perf_counter() > self.deadline)):
            raise _TooBig
        self.onpath.add(key)
        maximize = s.turn == self.me
        best = None
        for m in self._ordered(s):
            c = s.clone()
            c.apply_unchecked(m)
            v = self._value(c)
            if best is None or (v > best if maximize else v < best):
                best = v
                if best == (WIN if maximize else LOSS):
                    break
        self.onpath.discard(key)
        self.memo[key] = best
        return best


class _TooBig(Exception):
    pass


EXACT_MAX_CARDS = 14


def exact_applicable(obs):
    """Колода пуста, в игре двое и карт на руках немного - перебор посилен."""
    alive = obs.n - len(obs.out)
    if obs.deck_size or alive != 2:
        return False
    return sum(obs.hand_sizes) <= EXACT_MAX_CARDS


# ---------- агент ----------

LEVEL_SETTINGS = {
    "medium": dict(samples=8, use_net=False, exact=False),
    "strong": dict(samples=24, use_net=True, exact=True),
}


class SearchAgent:
    def __init__(self, level="strong", samples=24, net=None, use_net=True, exact=True,
                 time_limit=None, node_limit=20000):
        self.level = level
        self.samples = samples
        if use_net and net is None:
            from game.ai.net import default_net
            net = default_net()
        self.evaluator = Evaluator(net if use_net else None)
        self.exact = Exact(node_limit) if exact else None
        self.time_limit = time_limit

    @classmethod
    def for_level(cls, level, **kw):
        cfg = dict(LEVEL_SETTINGS[level])
        cfg.update(kw)
        return cls(level=level, **cfg)

    def choose(self, obs, seed=0, stop=None):
        legal = obs.legal
        if len(legal) == 1:
            return legal[0]
        scores = self.analyze(obs, seed, stop)
        best = max(range(len(legal)), key=lambda i: (scores[i][1], -i))
        return legal[best]

    def analyze(self, obs, seed=0, stop=None):
        """Оценка каждого допустимого хода: [(ход, средняя оценка от -1 до 1)]."""
        legal = list(obs.legal)
        me = obs.player
        started = time.perf_counter()
        if self.exact is not None and exact_applicable(obs):
            hands = [0] * obs.n
            hands[me] = obs.hand
            opp = next(q for q in range(obs.n) if q != me and q not in obs.out)
            hands[opp] = obs.known[opp] | obs.unseen()
            s = state_from(obs, hands, [])
            deadline = started + self.time_limit if self.time_limit else None
            res = self.exact.solve(s, me, stop=stop, deadline=deadline)
            if res is not None:
                got = dict(res)
                return [(m, got[m]) for m in legal]
        rng = np.random.default_rng(seed)
        P = tracker.belief(obs)
        total = np.zeros(len(legal))
        done = 0
        for k in range(self.samples):
            if k >= 2 and ((stop is not None and stop.is_set()) or
                           (self.time_limit and time.perf_counter() - started > self.time_limit)):
                break
            hands, deck = tracker.sample(obs, rng, P)
            base = state_from(obs, hands, deck)
            leaves = []
            for m in legal:
                c = base.clone()
                c.apply_unchecked(m)
                leaves.append(finish_bout(c))
            total += self.evaluator(leaves, me)
            done += 1
        avg = total / max(done, 1)
        return [(m, float(v)) for m, v in zip(legal, avg)]
