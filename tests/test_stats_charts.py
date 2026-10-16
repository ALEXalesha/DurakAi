"""Графики статистики из общего aikit.charts (1.0.4; правило автора 10.10 - графики во всех
играх с ИИ, и в карточных).

Законы: на странице статистики графики aikit, в сетке без наложений; без партий - заглушки
словами (не пустая сетка с одной точкой); подписи целы (chart.clipped пуст) в обеих темах, на
обоих языках, в широком и самом узком окне; серии побед и рекорд - по журналу партий."""
from aikit.charts import ChartCard, all_charts
from tests.test_ui import app, win  # noqa: F401 - фикстуры окна


def record(g, outcomes):
    for i, o in enumerate(outcomes):
        g.history.record({"players": 2, "level": ("novice", "medium", "strong")[i % 3], "outcome": o,
                          "moves": 30 + i, "margin": (i % 5) - 2})


def labels_intact(app, win, g):
    for theme in ("dark", "light"):
        for lang in ("ru", "en"):
            win.ctx.set_theme(theme)
            win.ctx.set_lang(lang)
            for width in (1400, win.minimumWidth()):
                win.resize(width, 820)
                app.processEvents()
                for c in all_charts(g.stats):
                    c.grab()
                    assert c.clipped == [], (theme, lang, width, c.title, c.clipped)
                rects = [c.geometry() for c in g.stats.chart_grid.charts()]
                assert not any(a.intersects(b) for i, a in enumerate(rects) for b in rects[i + 1:])
    win.ctx.set_theme("dark")
    win.ctx.set_lang("ru")


def test_charts_are_aikit_and_stubs_without_games(app, win):
    g = win.game
    g.show_page("stats")
    charts = all_charts(g.stats)
    assert len(charts) >= 6 and all(isinstance(c, ChartCard) for c in charts)
    st = g.stats
    for c in (st.share_chart, st.levels_chart, st.moves_chart, st.margin_chart, st.streak_chart):
        c.grab()
        assert c.shown_empty and c.empty_text, c.title
    record(g, ["win"])                               # одна партия - ещё не график
    g.show_page("stats")
    for c in (st.share_chart, st.moves_chart, st.streak_chart):
        c.grab()
        assert c.shown_empty, c.title
    labels_intact(app, win, g)


def test_streaks_and_record_follow_the_log(app, win):
    g = win.game
    record(g, ["win", "win", "draw", "win", "loss", "win", "win", "win"])
    g.show_page("stats")
    st = g.stats.streak_chart
    assert [y for _, y in st.points] == [1, 2, 0, 1, 0, 1, 2, 3]
    assert [y for _, y in st.second] == [1, 2, 2, 2, 2, 2, 2, 3]
    for c in all_charts(g.stats):
        c.grab()
        assert not c.shown_empty, c.title
    labels_intact(app, win, g)
