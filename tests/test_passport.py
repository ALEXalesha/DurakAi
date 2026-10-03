"""Паспорт модели: числа проверок силы на месте, и малая выборка пересчитывается с теми же
зёрнами - партия в партию."""
import json
import os

import pytest

from game.ai.agents import make_agent
from game.ai.net import default_net
from game.ai.tournament import match
from game.train.passport import CHECKS

PASSPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "game", "models", "durak-value.json")
REPLAY = 4


@pytest.fixture(scope="module")
def passport():
    if not os.path.exists(PASSPORT):
        pytest.skip("модель ещё не обучена")
    with open(PASSPORT, encoding="utf-8") as f:
        return json.load(f)


def find(pp, level, check):
    return next(c for c in pp["checks"] if c["level"] == level and c["check"] == check)


def test_passport_has_every_check_and_training_facts(passport):
    assert default_net() is not None
    for level, check, villain, players, seed in CHECKS:
        c = find(passport, level, check)
        assert c["games"] == passport["games_per_check"] and c["villain"] == villain
        assert c["players"] == players and c["seed"] == seed
    tr = passport["training"]
    assert tr["games"] > 0 and tr["positions"] > 0 and tr["seconds"] > 0
    net = passport["network"]
    assert net["parameters"] == sum(p.size for _, p, _ in default_net().params())


def test_strength_claims(passport):
    """Сильный бьёт случайного и новичка, не хуже среднего; втроём и вчетвером
    остаётся дураком реже, чем 1/N."""
    assert find(passport, "strong", "vs_random")["score"] > 0.9
    assert find(passport, "strong", "vs_novice")["score"] > 0.6
    assert find(passport, "strong", "vs_medium")["score"] > 0.5
    assert find(passport, "medium", "vs_random")["score"] > 0.9
    for level in ("strong", "medium", "novice"):
        for check, n in (("3p", 3), ("4p", 4)):
            assert find(passport, level, check)["fool_rate"] < 1 / n


@pytest.mark.parametrize("level,check,villain,players,seed", CHECKS)
def test_sample_replays_with_same_seeds(passport, level, check, villain, players, seed):
    c = find(passport, level, check)
    r = match(make_agent(level), make_agent(villain), c["games"], seed=seed, players=players,
              indices=range(REPLAY))
    assert [list(d) for d in r.details] == c["sample"][:REPLAY]
