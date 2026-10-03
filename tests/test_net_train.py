"""Сеть оценки и обучение: вход, градиенты, сохранение, снимок и продолжение с места."""
import json
import os

import numpy as np

from aikit.nn.optim import Adam
from game.ai.net import FEATURES, ValueNet, features, rotate
from game.core import cards as C
from game.core.durak import Rules, State
from game.train.selfplay import Trainer, play_one


def test_features_shape_and_content():
    s = State.new(Rules(players=3, transfer=True), seed=4)
    v = features(s, 1)
    assert v.shape == (FEATURES,) and v.dtype == np.float32
    assert v[:36].sum() == 6 and v[36:72].sum() == 6 and v[72:108].sum() == 6
    assert v[108:144].sum() == len(s.deck)
    assert v[153 + 1] == 1.0 and v[156] == 1.0
    assert v[149:153].sum() == 1 and v[160:164].sum() == 1


def test_trump_rotation_makes_features_trump_invariant():
    """Та же раскладка со сдвинутыми по кругу мастями (козырь переезжает) - тот же вход."""
    s = State.new(Rules(), seed=8)
    for k in (1, 2, 3):
        check_shift(s, [(x + k) % 4 for x in range(4)])
    assert rotate(C.SUIT_MASK[s.trump], s.trump) == C.SUIT_MASK[3]


def check_shift(s, perm):
    def move(m):
        out = 0
        for c in C.cards_of(m):
            out |= 1 << (perm[c // 9] * 9 + c % 9)
        return out
    t = s.clone()
    t.hands = [move(h) for h in s.hands]
    t.deck = [perm[c // 9] * 9 + c % 9 for c in s.deck]
    t.trump = perm[s.trump]
    assert np.array_equal(features(s, 0), features(t, 0))


def test_backward_matches_numeric_gradient():
    rng = np.random.default_rng(0)
    net = ValueNet(seed=1, hidden=(8, 4))
    for layer in net.dense():
        layer.W[...] = layer.W.astype(np.float64)
    X = rng.normal(size=(5, FEATURES)).astype(np.float32)
    y = rng.uniform(-1, 1, size=5).astype(np.float32)

    def loss():
        return float(np.mean((net.forward(X) - y) ** 2))
    pred = net.forward(X)
    net.backward((2.0 / len(y)) * (pred - y))
    d0 = net.dense()[0]
    analytic = d0.dW.copy()
    eps = 1e-2
    for (i, j) in [(0, 0), (3, 2), (100, 5), (163, 7)]:
        old = d0.W[i, j]
        d0.W[i, j] = old + eps
        up = loss()
        d0.W[i, j] = old - eps
        down = loss()
        d0.W[i, j] = old
        num = (up - down) / (2 * eps)
        assert abs(num - analytic[i, j]) < 1e-3 + 0.05 * abs(num), (i, j, num, analytic[i, j])


def test_predict_equals_forward_and_save_load(tmp_path):
    rng = np.random.default_rng(1)
    net = ValueNet(seed=2)
    X = rng.random((7, FEATURES)).astype(np.float32)
    assert np.allclose(net.predict(X), net.forward(X), atol=1e-5)
    p = tmp_path / "v.npz"
    net.save(p)
    back = ValueNet.load(p)
    assert np.allclose(back.predict(X), net.predict(X))


def test_training_fits_a_simple_rule():
    """Сеть учится: «больше козырей - лучше» выучивается за пару сотен шагов."""
    rng = np.random.default_rng(3)
    X = (rng.random((2000, FEATURES)) < 0.15).astype(np.float32)
    y = np.tanh(X[:, 27:36].sum(axis=1) - 1.3).astype(np.float32)
    net = ValueNet(seed=0, hidden=(32, 16))
    opt = Adam(net.params(), lr=3e-3)
    first = net.train_batch(X[:256], y[:256], opt)
    for _ in range(300):
        idx = rng.integers(0, 2000, 256)
        last = net.train_batch(X[idx], y[idx], opt)
    assert last < 0.3 * first


def test_play_one_gives_positions_and_outcomes():
    X, y, rules = play_one(None, seed=5, eps=0.1, policy="novice")
    assert X.shape[1] == FEATURES and len(X) == len(y) > 0
    assert set(np.unique(y)) <= {-1.0, 0.0, 1.0}
    # дурак один на партию: на каждой границе отбоя одна позиция у него (-1), прочие +1
    bouts = 0
    for seed in range(20):
        _, yy, r = play_one(None, seed=seed, eps=0.1, policy="novice")
        if 0.0 in yy:
            continue
        losers = (yy == -1).sum()
        assert 0 < losers < len(yy)
        bouts += 1
    assert bouts >= 15
    X2, y2, _ = play_one(None, seed=5, eps=0.1, policy="novice")
    assert np.array_equal(X, X2) and np.array_equal(y, y2)       # зерно - та же партия
    Xg, yg, _ = play_one(ValueNet(seed=0, hidden=(8, 4)), seed=6, eps=0.1, policy="greedy")
    assert len(Xg) == len(yg) > 0


def test_snapshot_resume_and_log(tmp_path):
    run = str(tmp_path / "run")
    t = Trainer(run, workers=1, games=6, eval_every=0, hidden=(16, 8))
    r1 = t.iterate(None)
    assert r1["iter"] == 1 and os.path.exists(t.snapshot_path)
    t.iterate(None)
    t2 = Trainer(run, workers=1, games=6, eval_every=0, hidden=(16, 8))
    t2.load_snapshot()
    assert t2.iteration == 2 and t2.trained and t2.opt.t == t.opt.t
    for a, b in zip(t.net.params(), t2.net.params()):
        assert np.array_equal(a[1], b[1])
    r3 = t2.iterate(None)
    assert r3["iter"] == 3
    lines = open(os.path.join(run, "train.log"), encoding="utf-8").read().splitlines()
    assert [json.loads(x)["iter"] for x in lines] == [1, 2, 3]


def test_evaluation_runs(tmp_path):
    t = Trainer(str(tmp_path / "r"), workers=1, games=4, eval_every=0, hidden=(16, 8),
                eval_samples=2)
    t.iterate(None)
    score = t.evaluate(None, games=4)
    assert 0.0 <= score <= 1.0


def test_threads_limited_in_training_entry():
    src = open(os.path.join(os.path.dirname(__file__), "..", "game", "train", "__main__.py"),
               encoding="utf-8").read()
    head = src.split("import argparse")[0]
    assert 'os.environ[_var] = "1"' in head          # до импорта numpy
