"""Кадры для README: окно без экрана, партия в нескольких состояниях.

    python tools/make_previews.py [папка]     # по умолчанию docs/
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aikit import offscreen  # noqa: E402

offscreen.setup(force=True)
os.environ["DURAKAI_HOME"] = tempfile.mkdtemp(prefix="durakai-previews-")


def wait_ai(app, g, limit=30):
    end = time.time() + limit
    while g.session.ai_turn() and time.time() < end:
        app.processEvents()
        time.sleep(0.002)


def play_until(app, g, cond, bot, limit=400):
    for _ in range(limit):
        s = g.session
        if s.over or cond(s):
            return
        if s.human_turn():
            g.on_move_chosen(bot.choose(s.obs(s.human)))
        wait_ai(app, g)


def settle(app, g, ms=1600):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main(out):
    from PySide6.QtWidgets import QApplication

    from aikit.host import make_window
    from game import APP_NAME, GAME_INFO, create_widget
    from game.ai.agents import NoviceAgent

    os.makedirs(out, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=os.environ["DURAKAI_HOME"])
    window.resize(1280, 800)
    window.show()
    g = window.game
    bot = NoviceAgent()
    shots = []
    # настоящие партии для графиков статистики: бот-новичок за человека против среднего ИИ
    g.change("anim_ms", 0)
    g.change("delay_ms", 0)
    g.change("players", 2)
    for k in range(16):
        g.change("level", ("medium", "novice", "strong")[k % 3])
        g.start_game(seed=200 + k)
        play_until(app, g, lambda s: False, bot)
    for theme_name in ("dark", "light"):
        ctx.set_theme(theme_name)
        suffix = "" if theme_name == "dark" else "_light"
        g.change("anim_ms", 0)
        g.change("delay_ms", 0)
        g.show_page("menu")
        g.menu.set_time(4.5)                    # веер раскрыт
        settle(app, g, 200)
        shots.append((window.grab(), f"preview_menu{suffix}.png"))
        # вдвоём: середина партии, ход человека, на столе пара
        g.change("players", 2)
        g.change("level", "strong")
        g.change("show_thoughts", True)
        g.start_game(seed=11)
        play_until(app, g, lambda s: s.human_turn() and s.state.table and s.state.bout >= 2, bot)
        settle(app, g, 2500)
        shots.append((window.grab(), f"preview_game2{suffix}.png"))
        # «ИИ против ИИ» с «Мыслями ИИ»: кадр в тот миг, когда мысли к этому ходу пришли
        g.change("mode", "demo")
        g.start_game(seed=17)
        end = time.time() + 90
        while time.time() < end:
            app.processEvents()
            time.sleep(0.003)
            th = g.thoughts
            if (th is not None and g.thoughts_token == g.token and th["scores"]
                    and len(g.session.moves) >= 6 and not g.play.table.animating()):
                break
        shots.append((window.grab(), f"preview_thoughts{suffix}.png"))
        g.change("mode", "play")
        # вчетвером
        g.change("players", 4)
        g.change("show_thoughts", False)
        g.start_game(seed=5)
        play_until(app, g, lambda s: s.human_turn() and len(s.state.table) >= 2, bot)
        settle(app, g, 600)
        shots.append((window.grab(), f"preview_game4{suffix}.png"))
        g.show_page("stats")
        settle(app, g, 200)
        shots.append((window.grab(), f"preview_stats{suffix}.png"))
        charts_card = g.stats.chart_grid.parentWidget()
        h = charts_card.heightForWidth(1180)
        charts_card.resize(1180, h if h > 0 else charts_card.sizeHint().height())
        shots.append((charts_card.grab(), f"preview_charts{suffix}.png"))
    # картинка для списка игр в ИИ-Игротеке: 16:9
    ctx.set_theme("dark")
    window.resize(1280, 720)
    g.change("players", 2)
    g.change("show_thoughts", True)
    g.start_game(seed=11)
    play_until(app, g, lambda s: s.human_turn() and s.state.table and s.state.bout >= 2, bot)
    settle(app, g, 2500)
    shots.append((window.grab(), "preview.png"))
    g.change("show_thoughts", False)
    for pix, name in shots:
        pix.save(os.path.join(out, name))
        print(name)
    g.shutdown()
    window.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs"))
