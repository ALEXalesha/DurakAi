"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл. Окно
создаётся offscreen, данные игрока - во временной папке, статистику игрока она не трогает.
Проверяется: правила (случайные партии с инвариантами), модель и паспорт, окно - ИИ
отвечает на ходы простого бота, который играет за человека через окно.
"""
import os
import random
import tempfile
import time
import traceback


def selftest(out_path):
    lines = []
    code = 0
    try:
        from aikit import offscreen
        offscreen.setup(force=True)
        home = tempfile.mkdtemp(prefix="durakai-selftest-")
        os.environ["DURAKAI_HOME"] = home
        from PySide6.QtWidgets import QApplication

        import aikit
        from aikit.host import make_window
        from game import APP_NAME, GAME_INFO, create_widget
        from game.ai.agents import NoviceAgent
        from game.ai.net import default_net
        from game.core.durak import Rules, State
        from game.version import VERSION

        lines.append(f"DurakAi {VERSION} самопроверка (aikit {aikit.__version__})")
        lines.append(f"собранная версия: {'да' if aikit.frozen() else 'нет'}")
        started = time.time()
        rng = random.Random(1)
        for i in range(200):
            s = State.new(Rules(players=2 + i % 3, transfer=i % 2 == 1), seed=i)
            while not s.over:
                s.check()
                s.apply(rng.choice(s.legal_moves()))
        lines.append(f"правила: 200 случайных партий без нарушений, {time.time() - started:.2f} с")
        net = default_net()
        lines.append("сеть: " + ("загружена" if net is not None else "нет (сильный играет по формуле)"))

        app = QApplication.instance() or QApplication([])
        window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
        window.show()
        g = window.game
        g.change("anim_ms", 0)
        g.change("delay_ms", 0)
        for players, level in ((2, "strong"), (3, "medium")):
            g.change("players", players)
            g.change("level", level)
            g.start_game(seed=7)
            bot = NoviceAgent()
            t0 = time.time()
            moves = 0
            while not g.session.over:
                s = g.session
                if s.human_turn():
                    g.on_move_chosen(bot.choose(s.obs(s.human)))
                    moves += 1
                end = time.time() + 30
                while g.session.ai_turn() and time.time() < end:
                    app.processEvents()
                    time.sleep(0.002)
                if g.session.ai_turn():
                    raise RuntimeError("ИИ не ответил за 30 с")
                if time.time() - t0 > 240:
                    raise RuntimeError("партия идёт дольше 4 минут")
            image = window.grab().toImage()
            if image.isNull() or image.width() < 300:
                raise RuntimeError("окно не нарисовалось")
            lines.append(f"{players} игрока, ИИ {level}: {moves} ходов бота за человека, "
                         f"итог «{g.play.status.text()}», кадр {image.width()}x{image.height()}, "
                         f"{time.time() - t0:.2f} с")
        t0 = time.time()
        window.close()
        app.processEvents()
        lines.append(f"окно закрыто за {time.time() - t0:.2f} с")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
