"""Учёт карт: где может лежать каждая карта, которую игрок не видит.

Всё строится из наблюдения (своя рука, стол, отбой, журнал публичных событий):

- свои карты, отбой и стол известны точно;
- взятые со стола карты и открытый козырь у добравшего известны всем (obs.known);
- остальное (невидимое) лежит в неизвестных местах рук соперников или в закрытой колоде.

Вывод из «не отбился»: защитник сказал «беру», когда на столе лежала карта a, - значит,
скорее всего, бить её ему было нечем: вес карт, которые бьют a, у него падает до TAKE_W.
Это не запрет: взять можно и нарочно. Когда он добирает карты, подозрение слабеет в той
доле, в какой рука обновилась.

belief(obs) -> матрица P[36, n + 2]: столбцы 0..n-1 - игроки, n - колода, n + 1 - вне игры
(отбой и стол). Каждая строка - распределение одной карты, сумма 1. Столбцы дают ровно
число карт в каждом месте. Пропорции между ними подгоняются чередованием нормировок строк
и столбцов (Синкхорн): это распределение с наибольшей неопределённостью при данных весах.

sample(obs, rng) -> раскладка: неизвестные карты по рукам соперников и по колоде - то, что
перебирает поиск (детерминизация).
"""
import numpy as np

from game.core import cards as C

TAKE_W = 0.15
SINKHORN_STEPS = 60


def beaters(a, trump):
    """Маска всех карт, которые бьют a."""
    s, r = a // 9, a % 9
    m = 0
    for rr in range(r + 1, 9):
        m |= 1 << (s * 9 + rr)
    if s != trump:
        m |= C.SUIT_MASK[trump]
    return m


def suspicion(obs):
    """Вес каждой карты у каждого игрока из выводов «не отбился»: массив [n, 36], 1 - без
    подозрений."""
    n = obs.n
    w = np.ones((n, 36))
    table = []
    sizes = [0] * n
    for e in obs.log:
        kind = e[0]
        if kind == "attack" or kind == "transfer":
            table.append([e[2], -1])
            sizes[e[1]] -= 1
        elif kind == "defend":
            table[e[3]][1] = e[2]
            sizes[e[1]] -= 1
        elif kind == "take":
            q = e[1]
            for a, d in table:
                if d < 0:
                    for c in C.cards_of(beaters(a, obs.trump)):
                        w[q, c] = min(w[q, c], TAKE_W)
        elif kind == "pickup":
            sizes[e[1]] += e[2].bit_count()
            table = []
        elif kind == "bito":
            table = []
        elif kind == "draw":
            q, k = e[1], e[2]
            old = max(sizes[q], 0)
            sizes[q] = old + k
            keep = old / sizes[q] if sizes[q] else 0.0
            w[q] = 1.0 - (1.0 - w[q]) * keep
        elif kind == "start":
            sizes = list(e[4])
    return w


def slots(obs):
    """Сколько неизвестных карт у каждого игрока и в колоде (свои - 0)."""
    n = obs.n
    out = []
    for q in range(n):
        if q == obs.player:
            out.append(0)
        else:
            out.append(obs.hand_sizes[q] - obs.known[q].bit_count())
    deck = obs.deck_size - (1 if obs.deck_size and obs.trump_card >= 0 else 0)
    out.append(deck)
    return out


def belief(obs):
    n = obs.n
    P = np.zeros((36, n + 2))
    gone = obs.discard | obs.table_mask()
    for c in C.cards_of(gone):
        P[c, n + 1] = 1.0
    for c in C.cards_of(obs.hand):
        P[c, obs.player] = 1.0
    for q in range(n):
        if q != obs.player:
            for c in C.cards_of(obs.known[q]):
                P[c, q] = 1.0
    if obs.deck_size and obs.trump_card >= 0:
        P[obs.trump_card, n] = 1.0
    unseen = C.cards_of(obs.unseen())
    if not unseen:
        return P
    sl = np.array(slots(obs), dtype=float)
    if abs(sl.sum() - len(unseen)) > 1e-9:
        raise AssertionError(f"мест {sl.sum()}, а невидимых карт {len(unseen)}")
    w = suspicion(obs)
    W = np.ones((len(unseen), n + 1))
    W[:, :n] = w[:, unseen].T
    W[:, sl == 0] = 0.0
    M = W.copy()
    for _ in range(SINKHORN_STEPS):
        M /= M.sum(axis=1, keepdims=True)
        col = M.sum(axis=0)
        scale = np.divide(sl, col, out=np.zeros_like(sl), where=col > 0)
        M *= scale
    M /= M.sum(axis=1, keepdims=True)
    P[unseen, :n + 1] = M
    return P


def sample(obs, rng, P=None):
    """Одна раскладка неизвестного: (руки соперников - маски с известными картами, колода -
    список с открытым козырем на дне). Своя рука - как есть.

    Соперники заполняются по очереди в случайном порядке: каждому - его число неизвестных
    карт, выбранных с весами из belief без возврата. Остаток - в колоду, вперемешку.
    """
    n = obs.n
    if P is None:
        P = belief(obs)
    unseen = C.cards_of(obs.unseen())
    sl = slots(obs)
    hands = [0] * n
    for q in range(n):
        hands[q] = obs.hand if q == obs.player else obs.known[q]
    pool = np.array(unseen, dtype=int)
    alive = np.ones(len(pool), dtype=bool)
    order = [q for q in range(n) if q != obs.player and sl[q] > 0]
    rng.shuffle(order)
    for q in order:
        k = sl[q]
        idx = np.flatnonzero(alive)
        p = P[pool[idx], q] + 1e-9
        p /= p.sum()
        pick = rng.choice(idx, size=k, replace=False, p=p)
        alive[pick] = False
        hands[q] |= C.mask(int(x) for x in pool[pick])
    rest = [int(x) for x in pool[alive]]
    rng.shuffle(rest)
    deck = ([obs.trump_card] if obs.deck_size and obs.trump_card >= 0 else []) + rest
    return hands, deck
