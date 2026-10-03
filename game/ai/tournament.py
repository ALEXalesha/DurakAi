"""Турнир: N партий с зерном, итог для паспорта модели.

Партия i играется колодой с зерном seed * 1_000_003 + i. Вдвоём раздачи идут парами:
та же колода дважды, места меняются - удача раздачи гасится, остаётся разница в игре.
Втроём и вчетвером испытуемый садится на места по кругу.

Решение агента зависит только от наблюдения и зерна хода; зерно хода выводится из зерна
партии и номера хода, так что тот же турнир с тем же зерном даёт тот же итог.
"""
from dataclasses import dataclass, field

from game.core.durak import DRAW, Rules, State
from game.core.observation import observation


def move_seed(game_seed, k):
    return (game_seed * 2_654_435_761 + k * 40_503 + 12_345) % (2 ** 32)


def play_game(agents, rules, deck_seed, first=None, max_moves=3000):
    """agents[p] - агент места p. Возвращает оконченное состояние."""
    s = State.new(rules, seed=deck_seed, first=first)
    k = 0
    while not s.over:
        p = s.turn
        legal = s.legal_moves()
        if len(legal) == 1:
            move = legal[0]
        else:
            move = agents[p].choose(observation(s, p), seed=move_seed(deck_seed, k))
        s.apply(move)
        k += 1
        if k > max_moves:
            raise RuntimeError("партия не кончилась")
    return s


@dataclass
class MatchResult:
    games: int = 0
    wins: int = 0          # испытуемый не дурак, а дурак - кто-то другой
    fools: int = 0         # испытуемый остался дураком
    draws: int = 0
    details: list = field(default_factory=list)

    @property
    def win_rate(self):
        return self.wins / self.games if self.games else 0.0

    @property
    def fool_rate(self):
        return self.fools / self.games if self.games else 0.0

    def score(self):
        """Доля очков вдвоём: победа 1, ничья 1/2."""
        return (self.wins + 0.5 * self.draws) / self.games if self.games else 0.0


def match(hero, villain, games, seed=0, players=2, transfer=False, first_bout_five=False,
          progress=None, indices=None):
    """hero против villain-ов. games - число партий (вдвоём - чётное, парами).
    indices - только эти номера партий (для деления турнира между процессами)."""
    rules = Rules(players=players, transfer=transfer, first_bout_five=first_bout_five)
    res = MatchResult()
    for i in (range(games) if indices is None else indices):
        if players == 2:
            deck_seed = seed * 1_000_003 + i // 2
            seat = i % 2
        else:
            deck_seed = seed * 1_000_003 + i
            seat = i % players
        agents = [villain] * players
        agents[seat] = hero
        s = play_game(agents, rules, deck_seed)
        res.games += 1
        if s.fool == DRAW:
            res.draws += 1
        elif s.fool == seat:
            res.fools += 1
        else:
            res.wins += 1
        res.details.append((deck_seed, seat, s.fool))
        if progress:
            progress(i + 1, games)
    return res
