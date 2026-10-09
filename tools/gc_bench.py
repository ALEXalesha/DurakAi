"""Замер к 1.0.0: нужен ли окну игры gc.freeze().

    python tools/gc_bench.py              # без gc.freeze (как с 1.0.0)
    python tools/gc_bench.py --freeze     # как в 0.9.0: gc.freeze() перед созданием виджета

В 0.9.0 виджет звал gc.freeze(): всё созданное уходило в постоянное поколение, чтобы полный
проход сборщика не останавливал окно посреди поиска. Но сборщик общий на процесс, и во
вкладке оболочки это замораживало навсегда и её объекты. Здесь меряется, что даёт заморозка.

Порядок: в памяти --host мелких объектов (так выглядит большая программа-оболочка), затем
виджет игры, затем сильный ИИ без предела времени (24 раскладки) выбирает ход в --positions
одних и тех же позициях. Время - процессорное время потока (time.thread_time), а не часы:
на машине идут и другие задачи, а работа сборщика считается в поток, который его вызвал.
Печатается: процессорные секунды поиска, полные проходы сборщика (поколение 2) за поиск и их
цена, цена одного полного прохода в конце - столько окно стояло бы, попади он в окно.
"""
import argparse
import gc
import os
import random
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def positions(n, seed=5):
    """n позиций, где у ходящего больше одного хода: случайные партии новичков."""
    from game.ai.agents import NoviceAgent
    from game.core.durak import Rules, State
    from game.core.observation import observation
    rng = random.Random(seed)
    bot = NoviceAgent()
    out = []
    game = 0
    while len(out) < n:
        s = State.new(Rules(players=2), seed=seed * 1000 + game)
        game += 1
        while not s.over and len(out) < n:
            obs = observation(s, s.turn)
            if len(obs.legal) > 1 and rng.random() < 0.25:
                out.append(obs)
            s.apply(bot.choose(obs))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true", help="gc.freeze() перед созданием виджета")
    ap.add_argument("--host", type=int, default=300_000, help="объектов «оболочки» в памяти")
    ap.add_argument("--positions", type=int, default=40)
    args = ap.parse_args(argv)
    for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(k, "1")
    from aikit import offscreen
    offscreen.setup(force=True)
    from PySide6.QtWidgets import QApplication

    from aikit.host import Context
    from game import create_widget
    from game.ai.search import SearchAgent

    app = QApplication.instance() or QApplication([])  # noqa: F841
    host = [{"i": i, "v": [i, str(i)]} for i in range(args.host)]  # noqa: F841 - память оболочки
    if args.freeze:
        gc.freeze()
    widget = create_widget(Context(tempfile.mkdtemp(prefix="durak-gcbench-"), "dark", "ru", 0))
    widget.resize(1180, 780)
    widget.show()
    work = positions(args.positions)
    agent = SearchAgent.for_level("strong")
    agent.choose(work[0], seed=1)                      # сеть загружена, кэши прогреты
    gc.collect()

    passes = []
    started = {}

    def on_gc(phase, info):
        if info["generation"] != 2:
            return
        if phase == "start":
            started["t"] = time.thread_time()
        elif "t" in started:
            passes.append(time.thread_time() - started.pop("t"))

    gc.callbacks.append(on_gc)
    t0 = time.thread_time()
    for i, obs in enumerate(work):
        agent.choose(obs, seed=i)
    search = time.thread_time() - t0
    gc.callbacks.remove(on_gc)
    t0 = time.thread_time()
    gc.collect()
    full = time.thread_time() - t0
    mode = "gc.freeze " if args.freeze else "без freeze"
    print(f"{mode}: поиск {search:.2f} с ЦП на {len(work)} ходов; полных проходов {len(passes)}, "
          f"на них {sum(passes) * 1000:.0f} мс; полный проход сейчас {full * 1000:.0f} мс; "
          f"объектов {len(gc.get_objects())}, заморожено {gc.get_freeze_count()}", flush=True)
    widget.deleteLater()
    return 0


if __name__ == "__main__":
    sys.exit(main())
