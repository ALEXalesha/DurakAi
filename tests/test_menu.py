"""Своё стартовое меню «карточный стол», боковая панель партии в его стиле и настройки на всю
ширину (автор 17.10: у каждой игры меню своё, «боковые меню тоже разнообразить»; настройки - как
статистика).

Законы:
- окно открывается меню; сукно с веером живёт, пока меню на экране, и стоит на других страницах
  и на паузе вкладки оболочки;
- меню цело (ничего за краем, текст и жирная выбранная фишка влезают, соседи не налезают) от
  минимального окна до 4K, в обеих темах, на двух языках; карты фона не заходят на колонку;
- боковая панель партии - в стиле меню и цела на всех размерах, вдвоём и вчетвером;
- карточка настроек занимает почти всю ширину страницы.
"""
import time

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from aikit.menu import SIZES, Backdrop, fill_share, layout_problems
from game import APP_NAME, GAME_INFO, create_widget
from game.ui import menu as M


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    w.game.change("anim_ms", 0)
    w.game.change("delay_ms", 0)
    yield w
    w.game.shutdown()
    w.close()
    w.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def resize(win, w, h):
    win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))


def test_window_opens_with_the_menu_and_felt_lives_only_there(app, win):
    g = win.game
    assert g.current_page() == "menu"
    assert isinstance(g.menu, Backdrop) and g.menu.running()
    t0 = g.menu.t
    pump(app, 0.2)
    assert g.menu.t > t0
    g.show_page("stats")
    assert not g.menu.running()
    g.show_page("menu")
    g.pause()
    assert not g.menu.running()
    g.resume()
    assert g.menu.running()


def test_menu_has_its_own_style(app, win):
    g = win.game
    assert isinstance(g.menu, M.Felt)
    css = g.menu.styleSheet()
    assert "Georgia" in css and "QFrame#rail" in css and "dashed" in css
    assert all(isinstance(b, M.CardButton) for b in g.menu.buttons)
    assert [b.suit for b in g.menu.buttons] == list(M.SUIT_ORDER[:3])


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_menu_is_whole_at_every_size(app, win, theme, lang):
    g = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    for level in ("novice", "medium", "strong"):          # выбранная фишка - жирная
        g.change("level", level)
        for w, h in SIZES:
            resize(win, w, h)
            pump(app, 0.03)
            g.menu.grab()
            assert layout_problems(g.menu) == [], (theme, lang, level, win.size())
            col = g.menu.column_rect()
            zone = g.menu.zone(g.menu.width(), g.menu.height())
            assert zone.right() <= col.left(), win.size()


def test_fan_opens_and_closes():
    assert M.fan_open(0) == 0.0
    assert abs(M.fan_open(4.5) - 1.0) < 1e-9
    assert M.fan_open(2.0) < M.fan_open(3.0)


def test_menu_scales_up_on_big_windows(app, win):
    g = win.game
    resize(win, 1280, 800)
    pump(app, 0.03)
    small = (g.menu.play_button.width(), g.menu.title.px)
    resize(win, 3840, 2160)
    pump(app, 0.03)
    assert g.menu.play_button.width() > small[0] * 1.8 and g.menu.title.px > small[1] * 1.8


def test_settings_card_stretches_like_stats(app, win):
    g = win.game
    g.show_page("settings")
    for w, h in SIZES:
        resize(win, w, h)
        pump(app, 0.03)
        page = g.settings_page
        assert fill_share(page.box, page) > 0.9, (win.size(), page.box.width(), page.width())


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_side_panel_in_menu_style_and_whole(app, win, theme, lang):
    g = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    pal = M.palette(theme)
    assert "Georgia" in g.play.side.styleSheet() and pal["rim"] in g.play.side.styleSheet()
    assert pal["felt_edge"] in g.play.styleSheet()
    for players, thoughts in ((2, True), (4, False)):
        g.change("players", players)
        g.change("show_thoughts", thoughts)
        g.start_game(seed=3)
        for w, h in SIZES:
            resize(win, w, h)
            pump(app, 0.03)
            g.play.side.grab()
            assert g.play.body.width() <= g.play.scroll.viewport().width()
            assert layout_problems(g.play.body) == [], (players, win.size())
        g.show_page("menu")
    g.change("players", 2)
    g.change("show_thoughts", False)


def test_background_cards_stay_left_of_the_column(app, win):
    g = win.game
    for w, h in SIZES:
        resize(win, w, h)
        pump(app, 0.03)
        col = g.menu.column_rect()
        fan, (cw, ch) = g.menu.fan_rects(g.menu.width(), g.menu.height(), 4.5)
        for _, centre, _ in fan:
            assert centre.x() + ch * 1.1 < col.left() + 1 or g.menu.zone(g.menu.width(), g.menu.height()).width() < 120
        zone = g.menu.zone(g.menu.width(), g.menu.height())
        assert QRectF(g.menu.rect()).contains(zone)
        assert zone.width() >= 120, win.size()           # стол с картами виден при любом окне
