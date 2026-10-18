"""Настройки и статистика в стиле «карточного стола» (aikit.skin, правило автора 17.10): свой вид,
не общий aikit; ничего не обрезано от 900x640 до 4K в обеих темах и на двух языках."""
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from aikit.menu import SIZES
from aikit.skin import DEFAULT, SkinPage, difference, page_problems
from game import APP_NAME, GAME_INFO, create_widget
from game.ui.skin import SKIN


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    yield w
    w.game.shutdown()
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(app, seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def test_pages_are_skin_pages_unlike_aikit(app, win):
    g = win.game
    assert isinstance(g.stats, SkinPage) and isinstance(g.settings_page, SkinPage)
    assert all(c.skin is SKIN for c in g.stats.charts)
    for theme in ("dark", "light"):
        for name in ("stats", "settings"):
            g.show_page(name)
            pump(app)
            page = g.pages[name]
            page.set_theme(theme)
            own = page.grab()
            page.skin = DEFAULT
            page.set_theme(theme)
            plain = page.grab()
            page.skin = SKIN
            page.set_theme(theme)
            assert difference(own, plain) > 0.3, (theme, name)


def test_charts_follow_theme(app, win):
    g = win.game
    assert g.settings_page.styleSheet() == SKIN.qss("dark") == g.stats.styleSheet()
    win.ctx.set_theme("light")
    assert g.settings_page.styleSheet() == SKIN.qss("light") == g.stats.styleSheet()
    assert all(c.theme == "light" for c in g.stats.charts)
    win.ctx.set_theme("dark")
    assert all(c.theme == "dark" for c in g.stats.charts)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_pages_clean_from_narrow_to_4k(app, win, theme, lang):
    g = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    for name in ("stats", "settings"):
        g.show_page(name)
        for w, h in SIZES:
            win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))
            pump(app, 0.03)
            assert page_problems(g.pages[name]) == [], (name, w, h)


def test_settings_groups_and_tiles(app, win):
    g = win.game
    g.show_page("settings")
    assert [x.text() for x in g.settings_page.box.groups] == [g.t("group_view").upper(), g.t("group_rules").upper()]
    g.show_page("stats")
    assert [t[2].text() for t in g.stats.tiles.tiles] == [g.t("tile_games"), g.t("tile_wins"), g.t("tile_fools"),
                                                          g.t("tile_streak")]
