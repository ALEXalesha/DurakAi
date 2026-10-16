"""Графики статистики (общий aikit/charts.py, с 1.0.4) и журнал партий (game/ui/history.py).

Графики рисуются без экрана (Qt offscreen) на пустых данных, на одной точке и на 1000 точках
и не падают; пустой график говорит словами, откуда возьмутся данные. Ряды для графиков
считаются из журнала партий чистыми функциями - их законы проверяются отдельно.
"""
import json
import math
import random

import pytest
from hypothesis import given, settings, strategies as st
from PySide6.QtWidgets import QApplication

from aikit import charts
from game.ui import history


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def render(w, size=(560, 230)):
    w.resize(*size)
    img = w.grab().toImage()
    assert not img.isNull() and img.width() == size[0]
    return img


def distinct_colours(img, step=7):
    seen = set()
    for x in range(0, img.width(), step):
        for y in range(0, img.height(), step):
            seen.add(img.pixel(x, y))
    return len(seen)


# --- виджеты ---


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("percent", [True, False])
def test_line_chart_empty_one_and_thousand_points(app, theme, percent):
    c = charts.LineChart("Доля побед", "Сыграйте две партии", x_label="партия", percent=percent,
                         names=("за 20", "за все"))
    c.set_theme(theme)
    c.set_points([])
    assert not c.has_data() and c.empty_text
    render(c)
    c.set_points([(1, 0.5)])
    assert not c.has_data()
    render(c)
    rng = random.Random(1)
    pts = [(i, rng.random() if percent else rng.randint(-30, 120)) for i in range(1, 1001)]
    c.set_points(pts, second=pts[::-1])
    assert c.has_data()
    img = render(c, (900, 230))
    assert distinct_colours(img) > 6           # что-то нарисовано, не одна заливка


def test_line_chart_survives_garbage(app):
    c = charts.LineChart("x", "пусто", percent=False)
    c.set_points([(1, float("nan")), (2, float("inf")), "мусор", (3,), (True, 1), (4, 2.0), (5, 3.0)])
    assert c.points == [(4.0, 2.0), (5.0, 3.0)]
    render(c)
    c.set_points([(1, 5.0), (2, 5.0)])           # ровная линия: шкала не делит на ноль
    render(c)
    c.set_points([(7, -3.0), (7, 4.0)])          # один x
    render(c)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_bar_chart_empty_one_and_many_groups(app, theme):
    b = charts.BarChart("По уровням", "Сыграйте партию против ИИ")
    b.set_theme(theme)
    b.set_data([], [])
    assert not b.has_data() and b.empty_text
    render(b)
    b.set_data(["новичок"], [("победы", "good", [0.4]), ("ничьи", "warn", [0.1]), ("дурак", "bad", [0.5])])
    assert b.has_data()
    render(b)
    groups = [f"g{i}" for i in range(1000)]
    b.set_data(groups, [("a", "good", [random.random() for _ in groups]), ("b", "bad", [2.0, -1.0])])
    assert all(0.0 <= v <= 1.0 for _, _, vals in b.series for v in vals)
    render(b, (900, 230))


def test_empty_chart_draws_its_text(app):
    """Пустой холст - дефект: без данных на карточке видна надпись."""
    c = charts.LineChart("Длина партии", "Здесь появится длина каждой партии", percent=False)
    c.set_points([])
    blank = charts.LineChart("Длина партии", "", percent=False)
    blank.set_points([])
    assert render(c) != render(blank)


@settings(max_examples=300)
@given(st.floats(-1e6, 1e6), st.floats(0, 1e6))
def test_y_scale_covers_data_with_round_steps(lo, span):
    hi = lo + span
    y0, y1, ticks, step = charts.y_scale(lo, hi)
    tol = 1e-6 * (span + abs(lo) + 1)              # меньше пикселя: шкала прощает только это
    assert y0 <= lo + tol and y1 >= hi - tol
    assert ticks[0] == pytest.approx(y0) and ticks[-1] == pytest.approx(y1, rel=1e-9, abs=1e-9)
    assert 2 <= len(ticks) <= 12
    mant = step / 10 ** math.floor(math.log10(step))
    assert any(abs(mant - m) < 1e-6 for m in (1, 2, 2.5, 5, 10))


# --- журнал партий и ряды для графиков ---


def rec(outcome, moves=40, margin=0, level="strong", players=2):
    return {"players": players, "level": level, "outcome": outcome, "moves": moves, "margin": margin}


def test_history_record_reload_and_cap(tmp_path):
    path = tmp_path / "games.json"
    h = history.GameLog(str(path), cap=50)
    for i in range(70):
        h.record(rec("win" if i % 2 else "loss", moves=i))
    assert len(h.games) == 50 and h.games[0]["moves"] == 20 and h.games[-1]["moves"] == 69
    again = history.GameLog(str(path), cap=50)
    assert again.games == h.games
    assert [g["n"] for g in again.games] == list(range(21, 71))   # номер партии - сквозной


def test_history_survives_broken_file(tmp_path):
    path = tmp_path / "games.json"
    path.write_text("{не json", encoding="utf-8")
    assert history.GameLog(str(path)).games == []
    path.write_text(json.dumps({"games": [dict(rec("win"), n=3), {"outcome": "ура"}, dict(rec("draw", moves=-5), n=4), 7,
                                          dict(rec("loss", level="бог"), n=5), rec("loss")]}), encoding="utf-8")
    h = history.GameLog(str(path))
    assert [g["outcome"] for g in h.games] == ["win"]
    assert h.record(rec("draw"))["n"] == 4          # номер продолжается после лучшей записи
    with pytest.raises(ValueError):
        h.record(rec("ура"))


def test_rolling_share_matches_brute_force():
    rng = random.Random(3)
    games = [rec(rng.choice(["win", "loss", "draw"])) for _ in range(137)]
    for i, g in enumerate(games, 1):
        g["n"] = i
    pts = history.rolling_share(games, window=20)
    value = {"win": 1.0, "draw": 0.5, "loss": 0.0}
    assert len(pts) == len(games)
    for k, (x, y) in enumerate(pts):
        part = games[max(0, k - 19):k + 1]
        assert x == games[k]["n"]
        assert y == pytest.approx(sum(value[g["outcome"]] for g in part) / len(part))
    total = history.rolling_share(games, window=None)
    assert total[-1][1] == pytest.approx(sum(value[g["outcome"]] for g in games) / len(games))


def test_by_level_shares_sum_to_one_and_skip_empty_levels():
    games = [rec("win", level="novice")] * 3 + [rec("loss", level="novice"), rec("draw", level="strong")]
    groups, series = history.by_level(games, ("novice", "medium", "strong"))
    assert groups == ["novice", "strong"]
    by = {name: vals for name, vals in series}
    assert by["win"] == [0.75, 0.0] and by["loss"] == [0.25, 0.0] and by["draw"] == [0.0, 1.0]
    for i in range(len(groups)):
        assert sum(v[i] for v in by.values()) == pytest.approx(1.0)


def test_series_for_length_and_margin():
    games = [dict(rec("win", moves=30 + i, margin=i - 2), n=i + 1) for i in range(5)]
    assert history.series(games, "moves") == [(1, 30), (2, 31), (3, 32), (4, 33), (5, 34)]
    assert history.series(games, "margin") == [(1, -2), (2, -1), (3, 0), (4, 1), (5, 2)]
    assert history.series([], "moves") == []


def test_margin_sign_follows_outcome():
    assert history.margin([0, 5], 1, 0, "win") == 5
    assert history.margin([3, 0, 0], 0, 0, "loss") == -3
    assert history.margin([0, 0], -2, 0, "draw") == 0
    assert history.margin([0, 0, 4, 0], 2, 0, "win") == 4
