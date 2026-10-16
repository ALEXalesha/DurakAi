"""Партия в окне без Qt: кто человек, какие уровни у ИИ, ходы, итог.

Режимы: 'play' - человек (место 0) против ИИ, 'demo' - ИИ против ИИ, карты открыты.

Подсчёт (решение автора 16.10): партия идёт в статистику после первого настоящего хода
человека (автоматический пас, когда подкинуть нечего, - не его ход). Брошенная после него -
дурак, а если человек уже вышел (избавился от карт) - «не дурак». Вышел, пока другие ещё
играли, - «не дурак» при любом конце, и при ничьей доигрывающих тоже.
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
        self.human_moves = 0         # настоящих ходов человека: с первого партия считается
        self.out_early = False       # человек вышел, а другие ещё играли: он не дурак
        self.abandoned = False       # брошена до конца (итог записан в этот момент)

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

    def apply(self, move, auto=False):
        """auto - ход сделан за человека (единственный пас): его ходом не считается."""
        if not auto and self.human >= 0 and self.state.turn == self.human:
            self.human_moves += 1
        self.state.apply(move)
        self.moves.append((self.state.log[-1] if self.state.log else None, move))
        if self.human >= 0 and self.human in self.state.out and not self.state.over:
            self.out_early = True

    def fool(self):
        return self.state.fool

    def outcome_for_human(self):
        """'win' / 'loss' / 'draw' для человека или None (партия идёт или это показ)."""
        if not self.over or self.human < 0:
            return None
        if self.out_early:
            return "win"
        if self.state.fool == DRAW:
            return "draw"
        return "loss" if self.state.fool == self.human else "win"

    def abandon_outcome(self):
        """Итог, если партию бросить сейчас: None - не считается (показ, партия уже кончилась
        или у человека ещё не было хода), 'win' - человек уже вышел, иначе 'loss'."""
        if self.human < 0 or self.over or self.human_moves == 0:
            return None
        return "win" if self.human in self.state.out else "loss"

    def stats_key(self):
        return f"{self.n}p/{self.level}"
