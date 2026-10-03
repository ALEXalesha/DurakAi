"""Обучение по команде:

    python -m game.train --iters 30 --games 3000 --workers 4          # с нуля
    python -m game.train --iters 30 --resume                          # продолжить со снимка
    python -m game.train --trial                                      # пробный круг и оценка времени
    python -m game.train --publish                                    # сеть из снимка -> game/models

Потоки ограничены: каждый работник считает в одном потоке BLAS, работников --workers
(по умолчанию 4) - ПК делят и другие задачи. Журнал и снимок - в --run (runs/durak).
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import tempfile  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train")
    ap.add_argument("--run", default=os.path.join("runs", "durak"))
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--games", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--eps", type=float, default=0.1)
    ap.add_argument("--eval-every", type=int, default=5)
    ap.add_argument("--eval-games", type=int, default=200)
    ap.add_argument("--policy", choices=("novice", "greedy"), default="novice",
                    help="кто играет партии для данных: простые правила или взгляд на отбой с сетью")
    ap.add_argument("--hidden", default="256,128", help="размеры скрытых слоёв")
    ap.add_argument("--init", help="начать с весов другого снимка (дообучение)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--trial", action="store_true", help="один малый круг и оценка времени")
    ap.add_argument("--publish", action="store_true", help="сеть из снимка в game/models")
    args = ap.parse_args(argv)

    from game.train.selfplay import Trainer
    from game.ai.net import DEFAULT_MODEL, MODEL_DIR
    hidden = tuple(int(x) for x in args.hidden.split(","))

    if args.publish:
        t = Trainer(args.run)
        t.load_snapshot()
        os.makedirs(MODEL_DIR, exist_ok=True)
        t.net.save(os.path.join(MODEL_DIR, DEFAULT_MODEL))
        print(f"сеть круга {t.iteration} -> {MODEL_DIR}\\{DEFAULT_MODEL}")
        return 0

    if args.trial:
        # пробный круг пишет во временную папку Python и ничего не удаляет
        run = tempfile.mkdtemp(prefix="durak-trial-")
        t = Trainer(run, workers=args.workers, games=max(args.workers * 250, 1000), eps=args.eps,
                    eval_every=0, policy=args.policy, hidden=hidden)
        with mp.Pool(args.workers) as pool:
            r0 = t.iterate(pool)          # круг 0: формула, сети ещё нет
            r1 = t.iterate(pool)          # круг 1: с сетью - так идут все остальные
            started = time.perf_counter()
            score = t.evaluate(pool, games=40)
            eval_s = time.perf_counter() - started
        per_game = r1["play_s"] / t.games
        per_iter = per_game * args.games + (r1["iter_s"] - r1["play_s"]) * args.games / t.games
        evals = args.iters // args.eval_every if args.eval_every else 0
        total = per_iter * args.iters + eval_s / 40 * args.eval_games * evals
        print(json.dumps({"round0": r0, "round1": r1, "trial_eval": round(score, 3),
                          "sec_per_game": round(per_game, 4),
                          "estimate_hours": round(total / 3600, 2)}, ensure_ascii=False))
        return 0

    t = Trainer(args.run, workers=args.workers, games=args.games, eps=args.eps,
                eval_every=args.eval_every, eval_games=args.eval_games, policy=args.policy,
                hidden=hidden)
    if args.resume and os.path.exists(t.snapshot_path):
        t.load_snapshot()
        print(f"продолжаю с круга {t.iteration}", flush=True)
    elif args.init:
        t.init_from(args.init)
        print(f"веса из {args.init}", flush=True)
    with mp.Pool(args.workers) as pool:
        while t.iteration < args.iters:
            r = t.iterate(pool)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
