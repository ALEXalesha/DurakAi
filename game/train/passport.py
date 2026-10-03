"""Паспорт модели: проверки силы (spec §4) и сведения об обучении.

    python -m game.train.passport            # 1000 партий на проверку, 4 процесса
    python -m game.train.passport --games 200

Вдвоём - доля очков испытуемого (победа 1, ничья 1/2) на парах раздач: та же колода
дважды с обменом мест. Втроём и вчетвером - как часто испытуемый остаётся дураком среди
новичков. Первые SAMPLE партий каждой проверки записываются поштучно: тесты пересчитывают
их с теми же зёрнами.
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

SAMPLE = 12
# (уровень, проверка, противник, игроков, зерно)
CHECKS = [
    ("strong", "vs_random", "random", 2, 101),
    ("strong", "vs_novice", "novice", 2, 102),
    ("strong", "vs_medium", "medium", 2, 103),
    ("strong", "3p", "novice", 3, 104),
    ("strong", "4p", "novice", 4, 105),
    ("medium", "vs_random", "random", 2, 111),
    ("medium", "vs_novice", "novice", 2, 112),
    ("medium", "3p", "novice", 3, 114),
    ("medium", "4p", "novice", 4, 115),
    ("novice", "vs_random", "random", 2, 121),
    ("novice", "3p", "random", 3, 124),
    ("novice", "4p", "random", 4, 125),
]


def run_part(job):
    level, villain, players, seed, games, indices = job
    from game.ai.agents import make_agent
    from game.ai.tournament import match
    r = match(make_agent(level), make_agent(villain), games, seed=seed, players=players,
              indices=indices)
    return r.wins, r.draws, r.fools, r.games, r.details


def run_check(pool, workers, level, villain, players, seed, games):
    parts = [list(range(w, games, workers)) for w in range(workers)]
    jobs = [(level, villain, players, seed, games, idx) for idx in parts if idx]
    res = pool.map(run_part, jobs) if pool else [run_part(j) for j in jobs]
    wins = sum(r[0] for r in res)
    draws = sum(r[1] for r in res)
    fools = sum(r[2] for r in res)
    n = sum(r[3] for r in res)
    details = sorted((d for r in res for d in r[4]), key=lambda d: (d[0], d[1]))
    by_index = {}
    for r, idx in zip(res, [j[5] for j in jobs]):
        for i, d in zip(idx, r[4]):
            by_index[i] = d
    sample = [list(by_index[i]) for i in range(min(SAMPLE, games))]
    return {"wins": wins, "draws": draws, "fools": fools, "games": n,
            "score": (wins + 0.5 * draws) / n, "fool_rate": fools / n, "sample": sample}


def training_info(run_dir):
    info = {"games": 0, "positions": 0, "iterations": 0, "seconds": 0.0}
    log = os.path.join(run_dir, "train.log")
    if os.path.exists(log):
        for line in open(log, encoding="utf-8"):
            r = json.loads(line)
            info["games"] += r["games"]
            info["positions"] += r["positions"]
            info["iterations"] = r["iter"]
            info["seconds"] = r["total_s"]
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train.passport")
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--run", default=os.path.join("runs", "durak"))
    ap.add_argument("--only", default="", help="только проверки с этим словом")
    args = ap.parse_args(argv)
    from game.ai.net import DEFAULT_MODEL, FEATURES, MODEL_DIR, default_net
    from game.ai.search import LEVEL_SETTINGS
    net = default_net()
    if net is None:
        print("нет сети в game/models - сначала python -m game.train --publish")
        return 1
    out_path = os.path.join(MODEL_DIR, DEFAULT_MODEL.replace(".npz", ".json"))
    old = {}
    if os.path.exists(out_path):
        old = json.load(open(out_path, encoding="utf-8"))
    params = sum(p.size for _, p, _ in net.params())
    passport = {
        "model": DEFAULT_MODEL,
        "network": {"features": FEATURES, "hidden": list(net.hidden), "parameters": int(params),
                    "output": "tanh: +1 не дурак, -1 дурак"},
        "training": old.get("training") or {},
        "levels": {k: v for k, v in LEVEL_SETTINGS.items()},
        "games_per_check": args.games,
        "checks": [],
    }
    tr = training_info(args.run)
    if tr["games"]:
        tr["policy"] = "простые правила с 10% случайных ходов, цель - исход партии"
        tr["workers"] = 4
        passport["training"] = tr
    started = time.time()
    with mp.Pool(args.workers) as pool:
        for level, check, villain, players, seed in CHECKS:
            if args.only and args.only not in f"{level} {check}":
                prev = [c for c in old.get("checks", []) if c["level"] == level and c["check"] == check]
                passport["checks"] += prev
                continue
            t0 = time.time()
            r = run_check(pool, args.workers, level, villain, players, seed, args.games)
            r.update({"level": level, "check": check, "villain": villain, "players": players,
                      "seed": seed, "seconds": round(time.time() - t0, 1)})
            passport["checks"].append(r)
            print(f"{level:7} {check:10} очки {r['score']:.3f} дурак {r['fool_rate']:.3f} "
                  f"({r['games']} партий, {r['seconds']} с)", flush=True)
    passport["check_seconds"] = round(time.time() - started, 1)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(passport, f, ensure_ascii=False, indent=1)
    print(f"паспорт -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
