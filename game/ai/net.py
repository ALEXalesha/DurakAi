"""Сеть оценки позиции на numpy: насколько вероятно, что игрок не останется дураком.

Оценивается полная раскладка - та, что получается в поиске после детерминизации
(game.ai.tracker.sample), а не наблюдение: поиск перебирает правдоподобные миры, и в каждом
мире карты видны. Своих чужих карт сеть в живой игре не видит никогда: в мир их кладёт
раскладка по учёту, а не настоящая партия.

Оценка всегда на границе отбоя (стол пуст, ходит атакующий): поиск доигрывает отбой до
конца, а дальше спрашивает сеть. Масти поворачиваются так, что козырь всегда на месте
червей: сеть одна на все четыре козыря и учится вчетверо быстрее.

Вход (FEATURES = 164):
  0..35    своя рука
  36..71   рука следующего по кругу (вдвоём - соперника)
  72..107  руки остальных вместе (вдвоём - нули)
  108..143 закрытая колода с открытым козырем
  144      размер колоды / 24
  145..148 число карт: моё и мест 1..3 по кругу, / 12
  149..152 кто атакует - место по кругу от меня
  153..155 игроков 2 / 3 / 4
  156      переводной
  157..159 места 1..3 ещё в игре
  160..163 кто защищается - место по кругу от меня
Выход - tanh: +1 «не дурак», -1 «дурак», 0 - ничья.
"""
import os

import numpy as np

from aikit.nn import io
from aikit.nn.layers import Dense, ReLU, Tanh

FEATURES = 164
HIDDEN = (128, 64)

# поворот мастей: козырь -> 3
_ROT = [[(s - t - 1) % 4 for s in range(4)] for t in range(4)]
_BITS9 = np.array([[(v >> i) & 1 for i in range(9)] for v in range(512)], dtype=np.float32)


def rotate(m, trump):
    rot = _ROT[trump]
    out = 0
    for s in range(4):
        out |= ((m >> (9 * s)) & 511) << (9 * rot[s])
    return out


def put_mask(v, off, m, trump):
    rot = _ROT[trump]
    for s in range(4):
        block = (m >> (9 * s)) & 511
        if block:
            o = off + 9 * rot[s]
            v[o:o + 9] = _BITS9[block]


def features(state, me, out=None):
    v = np.zeros(FEATURES, np.float32) if out is None else out
    if out is not None:
        v[:] = 0.0
    n = state.n
    t = state.trump
    hands = state.hands
    put_mask(v, 0, hands[me], t)
    put_mask(v, 36, hands[(me + 1) % n], t)
    others = 0
    for k in range(2, n):
        others |= hands[(me + k) % n]
    put_mask(v, 72, others, t)
    deckm = 0
    for c in state.deck:
        deckm |= 1 << c
    put_mask(v, 108, deckm, t)
    v[144] = len(state.deck) / 24.0
    for k in range(n):
        v[145 + k] = hands[(me + k) % n].bit_count() / 12.0
    if state.attacker >= 0:
        v[149 + (state.attacker - me) % n] = 1.0
        v[160 + (state.defender - me) % n] = 1.0
    v[153 + n - 2] = 1.0
    v[156] = 1.0 if state.rules.transfer else 0.0
    for k in range(1, n):
        if (me + k) % n not in state.out:
            v[156 + k] = 1.0
    return v


class ValueNet:
    def __init__(self, seed=0, hidden=HIDDEN):
        rng = np.random.default_rng(seed)
        sizes = (FEATURES,) + tuple(hidden) + (1,)
        self.layers = {}
        seq = []
        for i in range(len(sizes) - 1):
            d = Dense(sizes[i], sizes[i + 1], rng)
            self.layers[f"d{i}"] = d
            seq.append(d)
            seq.append(ReLU() if i < len(sizes) - 2 else Tanh())
        self.seq = seq
        self.hidden = tuple(hidden)
        self._last = None

    def dense(self):
        return [self.layers[f"d{i}"] for i in range(len(self.hidden) + 1)]

    def predict(self, X):
        """Быстрый проход без запоминания промежуточного - для поиска."""
        h = X
        ds = self.dense()
        for d in ds[:-1]:
            h = h @ d.W + d.b
            np.maximum(h, 0.0, out=h)
        return np.tanh(h @ ds[-1].W + ds[-1].b)[:, 0]

    def forward(self, X):
        h = X
        for layer in self.seq:
            h = layer.forward(h)
        return h[:, 0]

    def backward(self, dy):
        g = dy[:, None].astype(np.float32)
        for layer in reversed(self.seq):
            g = layer.backward(g)

    def params(self):
        return [p for layer in self.seq for p in layer.params()]

    def train_batch(self, X, y, opt):
        """Один шаг Adam на среднеквадратичную ошибку. Возвращает потерю."""
        pred = self.forward(X)
        diff = pred - y
        self.backward((2.0 / len(y)) * diff)
        opt.step()
        return float(np.mean(diff * diff))

    def arrays(self):
        a = io.collect(self.layers)
        a["hidden"] = np.array(self.hidden)
        return a

    def save(self, path):
        io.save(path, self.arrays())

    @classmethod
    def load(cls, path):
        arrays = io.load(path)
        net = cls(hidden=tuple(int(x) for x in arrays["hidden"]))
        io.restore(net.layers, arrays)
        return net


MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
DEFAULT_MODEL = "durak-value.npz"

_cache = {}


def default_net():
    """Готовая сеть из game/models или None, если её ещё нет (до обучения)."""
    path = os.path.join(MODEL_DIR, DEFAULT_MODEL)
    if path not in _cache:
        _cache[path] = ValueNet.load(path) if os.path.exists(path) else None
    return _cache[path]
