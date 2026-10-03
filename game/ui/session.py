"""Партия в окне без Qt: кто человек, какие уровни у ИИ, ходы, итог.

Режимы: 'play' - человек (место 0) против ИИ, 'demo' - ИИ против ИИ, карты открыты.
"""
from game.core.durak import DRAW, Rules, State
from game.core.observation import observation

MODES = ("play", "demo")


class Session:
    def __init__(self, players=2, level="strong", mode="play", transfer=False, five=False,
                 seed=0, first=None):
        if mode not in MODES:
            raise ValueError(mode)
        self.rules = Rules(players=players, transfer=transfer, first_bout_five=five)
        self.mode = mode
        self.level = level
        self.human = 0 if mode == "play" else -1
        self.seed = seed
        self.state = State.new(self.rules, seed=seed, first=first)
        self.moves = []
        self.recorded = False
        self.peeked = False          # человек смотрел чужие карты - в статистику не идёт

    @property
    def n(self):
        return self.rules.players

    @property
    def over(self):
        return self.state.over

    def human_turn(self):
        return not self.over and self.state.turn == self.human

    def ai_turn(self):
        return not self.over and self.state.turn != self.human

    def legal(self):
        return self.state.legal_moves()

    def obs(self, player):
        return observation(self.state, player)

    def apply(self, move):
        self.state.apply(move)
        self.moves.append((self.state.log[-1] if self.state.log else None, move))

    def fool(self):
        return self.state.fool

    def outcome_for_human(self):
        """'win' / 'loss' / 'draw' для человека или None (партия идёт или это показ)."""
        if not self.over or self.human < 0:
            return None
        if self.state.fool == DRAW:
            return "draw"
        return "loss" if self.state.fool == self.human else "win"

    def stats_key(self):
        return f"{self.n}p/{self.level}"
