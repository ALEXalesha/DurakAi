"""Обучение сети оценки в игре с собой.

Круг обучения:
1. Работники (процессы, по одному потоку BLAS) играют партии. Каждый игрок в партии
   смотрит на все свои ходы на один отбой вперёд: делает ход, доигрывает отбой простыми
   правилами и спрашивает текущую сеть, как хороша позиция. Берёт лучший ход, изредка
   случайный (eps) - иначе сеть не увидит позиций, куда сама не ходит. Часть мест играет
   простыми правилами, чтобы позиции были разнообразнее. Здесь карты видны: это сбор
   данных, а не живая игра - в живой игре сеть оценивает только миры из раскладок учёта.
2. На каждой границе отбоя пишется позиция с точки зрения каждого игрока в игре, а цель -
   чем партия для него кончилась: +1 не дурак, -1 дурак, 0 ничья (Монте-Карло).
3. Сеть учится на последних кругах (буфер), Adam, среднеквадратичная ошибка.
4. Раз в несколько кругов - проверка: поиск с этой сетью против простого бота.

Журнал - train.log (JSON по строке на круг), снимок - snapshot.npz после каждого круга:
веса, состояние Adam, номер круга. --resume продолжает со снимка; буфер позиций при этом
начинается заново (он большой, и пары кругов хватает, чтобы его набрать).
"""
import json
import os
import time

import numpy as np

from aikit.nn import io
from aikit.nn.optim import Adam
from game.ai.net import FEATURES, ValueNet, features
from game.ai.search import Evaluator, default_move, finish_bout
from game.core.durak import DRAW, Rules, State

MIX = ((2, 0.5), (3, 0.25), (4, 0.25))     # сколько игроков и с какой долей
TRANSFER_SHARE = 0.3
NOVICE_SEAT = 0.15


def pick_rules(rng):
    r = rng.random()
    acc = 0.0
    for n, share in MIX:
        acc += share
        if r < acc:
            break
    return Rules(players=n, transfer=rng.random() < TRANSFER_SHARE,
                 first_bout_five=rng.random() < 0.2)


def greedy_move(s, evaluator, rng, eps):
    legal = s.legal_moves()
    if len(legal) == 1:
        return legal[0]
    if rng.random() < eps:
        return legal[rng.integers(len(legal))]
    me = s.turn
    leaves = []
    for m in legal:
        c = s.clone()
        c.apply_unchecked(m)
        leaves.append(finish_bout(c))
    v = evaluator(leaves, me)
    best = np.flatnonzero(v >= v.max() - 1e-9)
    return legal[best[rng.integers(len(best))]]


def play_one(net, seed, eps, policy="greedy"):
    """Одна партия. Возвращает (позиции [k, FEATURES], цели [k], правила).
    policy: greedy - взгляд на отбой вперёд с сетью, novice - все играют простыми правилами
    (с eps случайных ходов)."""
    rng = np.random.default_rng(seed)
    rules = pick_rules(rng)
    s = State.new(rules, seed=int(rng.integers(2 ** 31)), log=False)
    evaluator = Evaluator(net)
    if policy == "novice":
        novice = np.ones(rules.players, dtype=bool)
    else:
        novice = rng.random(rules.players) < NOVICE_SEAT
    rows, who = [], []
    last_bout = -1
    moves = 0
    while not s.over:
        if s.bout != last_bout and not s.table:
            last_bout = s.bout
            for q in range(s.n):
                if q not in s.out:
                    rows.append(features(s, q))
                    who.append(q)
        if novice[s.turn]:
            legal = s.legal_moves()
            if len(legal) > 1 and rng.random() < eps:
                m = legal[rng.integers(len(legal))]
            else:
                m = default_move(s)
        else:
            m = greedy_move(s, evaluator, rng, eps)
        s.apply_unchecked(m)
        moves += 1
        if moves > 3000:          # переводной вдвоём может ходить по кругу - бросаем партию
            return np.zeros((0, FEATURES), np.float32), np.zeros(0, np.float32), rules
    y = np.array([0.0 if s.fool == DRAW else (-1.0 if s.fool == q else 1.0) for q in who],
                 np.float32)
    X = np.array(rows, np.float32) if rows else np.zeros((0, FEATURES), np.float32)
    return X, y, rules


def _net_from(arrays):
    if arrays is None:
        return None
    net = ValueNet(hidden=tuple(int(x) for x in arrays["hidden"]))
    io.restore(net.layers, arrays)
    return net


def worker_games(job):
    """Работник: job = (веса или None, первое зерно, число партий, eps)."""
    arrays, seed0, count, eps, policy = job
    net = _net_from(arrays)
    Xs, ys = [], []
    for i in range(count):
        X, y, _ = play_one(net, seed0 + i, eps, policy)
        Xs.append(X)
        ys.append(y)
    return np.concatenate(Xs), np.concatenate(ys)


def worker_eval(job):
    """Работник проверки: поиск с сетью против простого бота на части раздач."""
    arrays, seed, start, count, samples = job
    from game.ai.agents import NoviceAgent
    from game.ai.search import SearchAgent
    from game.ai.tournament import play_game
    net = _net_from(arrays)
    hero = SearchAgent(level="strong", samples=samples, net=net, use_net=net is not None)
    villain = NoviceAgent()
    rules = Rules(players=2)
    wins = draws = 0
    for i in range(start, start + count):
        deck_seed = seed * 1_000_003 + i // 2
        seat = i % 2
        agents = [villain, villain]
        agents[seat] = hero
        s = play_game(agents, rules, deck_seed)
        if s.fool == DRAW:
            draws += 1
        elif s.fool != seat:
            wins += 1
    return wins, draws, count


class Trainer:
    def __init__(self, run_dir, workers=4, games=2000, eps=0.1, buffer_iters=3, epochs=2,
                 batch=512, lr=1e-3, eval_every=5, eval_games=200, eval_samples=8, seed=1,
                 hidden=(256, 128), policy="novice"):
        self.policy = policy
        self.run_dir = run_dir
        self.workers = workers
        self.games = games
        self.eps = eps
        self.buffer_iters = buffer_iters
        self.epochs = epochs
        self.batch = batch
        self.lr = lr
        self.eval_every = eval_every
        self.eval_games = eval_games
        self.eval_samples = eval_samples
        self.seed = seed
        self.net = ValueNet(seed=seed, hidden=hidden)
        self.opt = Adam(self.net.params(), lr=lr)
        self.iteration = 0
        self.trained = False          # итерация 0 играет формулой, пока сеть не училась
        self.buffer = []
        self.elapsed = 0.0
        os.makedirs(run_dir, exist_ok=True)

    # ---------- снимок ----------

    @property
    def snapshot_path(self):
        return os.path.join(self.run_dir, "snapshot.npz")

    def save_snapshot(self):
        a = self.net.arrays()
        for i, (m, v) in enumerate(zip(self.opt.m, self.opt.v)):
            a[f"adam.m{i}"] = m
            a[f"adam.v{i}"] = v
        a["adam.t"] = np.array(self.opt.t)
        a["iteration"] = np.array(self.iteration)
        a["trained"] = np.array(int(self.trained))
        a["elapsed"] = np.array(self.elapsed)
        io.save(self.snapshot_path, a)

    def load_snapshot(self):
        a = io.load(self.snapshot_path)
        self.net = ValueNet(hidden=tuple(int(x) for x in a["hidden"]))
        io.restore(self.net.layers, a)
        self.opt = Adam(self.net.params(), lr=self.lr)
        for i in range(len(self.opt.m)):
            self.opt.m[i][...] = a[f"adam.m{i}"]
            self.opt.v[i][...] = a[f"adam.v{i}"]
        self.opt.t = int(a["adam.t"])
        self.iteration = int(a["iteration"])
        self.trained = bool(int(a["trained"]))
        self.elapsed = float(a["elapsed"])

    def init_from(self, path):
        """Только веса из чужого снимка: дообучение другой политикой с готовой сети."""
        a = io.load(path)
        io.restore(self.net.layers, a)
        self.trained = True

    def log(self, record):
        with open(os.path.join(self.run_dir, "train.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ---------- круг ----------

    def _map(self, pool, fn, jobs):
        if pool is None:
            return [fn(j) for j in jobs]
        return pool.map(fn, jobs)

    def split(self, total):
        w = max(1, self.workers)
        base, extra = divmod(total, w)
        return [base + (1 if i < extra else 0) for i in range(w) if base + (1 if i < extra else 0)]

    def iterate(self, pool):
        started = time.perf_counter()
        arrays = self.net.arrays() if self.trained else None
        seed0 = self.seed * 10_000_000 + self.iteration * 100_000
        jobs = []
        off = 0
        for k in self.split(self.games):
            jobs.append((arrays, seed0 + off, k, self.eps, self.policy))
            off += k
        parts = self._map(pool, worker_games, jobs)
        X = np.concatenate([p[0] for p in parts])
        y = np.concatenate([p[1] for p in parts])
        play_time = time.perf_counter() - started
        self.buffer.append((X, y))
        self.buffer = self.buffer[-self.buffer_iters:]
        BX = np.concatenate([b[0] for b in self.buffer])
        By = np.concatenate([b[1] for b in self.buffer])
        rng = np.random.default_rng(seed0)
        losses = []
        for _ in range(self.epochs):
            order = rng.permutation(len(By))
            for i in range(0, len(order), self.batch):
                idx = order[i:i + self.batch]
                losses.append(self.net.train_batch(BX[idx], By[idx], self.opt))
        self.trained = True
        self.iteration += 1
        record = {"iter": self.iteration, "games": self.games, "positions": int(len(y)),
                  "buffer": int(len(By)), "loss": round(float(np.mean(losses)), 5),
                  "play_s": round(play_time, 1)}
        if self.eval_every and self.iteration % self.eval_every == 0:
            record["vs_novice"] = round(self.evaluate(pool), 4)
        took = time.perf_counter() - started
        self.elapsed += took
        record["iter_s"] = round(took, 1)
        record["total_s"] = round(self.elapsed, 1)
        self.save_snapshot()
        self.log(record)
        return record

    def evaluate(self, pool, games=None, seed=9001):
        games = games or self.eval_games
        arrays = self.net.arrays()
        jobs = []
        start = 0
        for k in self.split(games):
            if k % 2:
                k += 1
            jobs.append((arrays, seed, start, k, self.eval_samples))
            start += k
        res = self._map(pool, worker_eval, jobs)
        wins = sum(r[0] for r in res)
        draws = sum(r[1] for r in res)
        n = sum(r[2] for r in res)
        return (wins + 0.5 * draws) / n
