"""Игроки-ИИ. Каждый получает только наблюдение (game.core.observation) и зерно.

choose(obs, seed) -> ход из obs.legal. Одно наблюдение и одно зерно - один ход: так
проверяется закон честности и пересчитывается паспорт модели.
"""
import random

LEVELS = ("random",)


class RandomAgent:
    level = "random"

    def choose(self, obs, seed=0):
        return random.Random(seed).choice(obs.legal)


def make_agent(level, **kw):
    if level == "random":
        return RandomAgent()
    raise ValueError(f"нет уровня {level}")
