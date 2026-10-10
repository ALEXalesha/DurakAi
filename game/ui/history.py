"""Журнал партий игрока против ИИ - данные для графиков статистики.

Файл games.json в ctx.data_dir: {"next": номер следующей партии, "games": [...]}, в каждой
партии - n (сквозной номер), players, level, outcome ('win' / 'loss' / 'draw' для
человека), moves (сколько ходов сделали все вместе), margin (разница карт в конце: при
победе - сколько карт осталось у дурака, при поражении - минус ваши карты, ничья - 0).
Хранятся последние cap партий. Битый файл - пустой журнал, битая запись пропускается.
Пишутся только те партии, что идут и в статистику: без подглядывания, не показ.

Ряды для графиков считаются здесь же чистыми функциями: их законы проверяются без Qt.
"""
from aikit.storage import is_int, load_json, save_json

OUTCOMES = ("win", "loss", "draw")
LEVELS = ("novice", "medium", "strong")
VALUE = {"win": 1.0, "draw": 0.5, "loss": 0.0}
CAP = 5000


def valid(g):
    return (isinstance(g, dict) and g.get("outcome") in OUTCOMES and g.get("level") in LEVELS
            and is_int(g.get("players")) and 2 <= g["players"] <= 4
            and is_int(g.get("moves")) and g["moves"] >= 0 and is_int(g.get("margin")))


class GameLog:
    def __init__(self, path=None, cap=CAP):
        self.path = path
        self.cap = cap
        self.games = []
        self.next = 1
        raw = load_json(path) if path else None
        if isinstance(raw, dict) and isinstance(raw.get("games"), list):
            for g in raw["games"]:
                if valid(g) and is_int(g.get("n")) and g["n"] >= 1:
                    self.games.append({k: g[k] for k in ("n", "players", "level", "outcome", "moves", "margin")})
            self.games = self.games[-cap:]
            last = max((g["n"] for g in self.games), default=0)
            self.next = max(last + 1, raw["next"] if is_int(raw.get("next")) else 1)

    def record(self, game):
        g = {k: game.get(k) for k in ("players", "level", "outcome", "moves", "margin")}
        if not valid(g):
            raise ValueError(f"битая запись партии: {game!r}")
        g["n"] = self.next
        self.next += 1
        self.games.append(g)
        del self.games[:-self.cap]
        self.save()
        return g

    def save(self):
        if self.path is None:
            return False
        return save_json(self.path, {"next": self.next, "games": self.games})


def margin(left, fool, human, outcome):
    """Разница карт в конце для человека: победа - сколько карт осталось у дурака, поражение -
    минус свои оставшиеся карты, ничья - 0. left - число карт на руках у каждого."""
    if outcome == "win":
        return left[fool] if fool >= 0 else 0
    if outcome == "loss":
        return -left[human]
    return 0


def rolling_share(games, window=20):
    """Доля очков (победа 1, ничья 1/2) по последним window партиям; None - за все партии."""
    out = []
    total = 0.0
    vals = [VALUE[g["outcome"]] for g in games]
    for k, g in enumerate(games):
        total += vals[k]
        if window is not None and k >= window:
            total -= vals[k - window]
        n = k + 1 if window is None else min(k + 1, window)
        out.append((g["n"], total / n))
    return out


def by_level(games, levels=LEVELS):
    """Доли побед, ничьих и поражений по уровням ИИ. Уровни без партий не показываются.
    Возвращает (уровни, [(итог, [доли по уровням])])."""
    count = {lv: {o: 0 for o in OUTCOMES} for lv in levels}
    for g in games:
        if g["level"] in count:
            count[lv := g["level"]][g["outcome"]] += 1
    groups = [lv for lv in levels if sum(count[lv].values())]
    series = [(o, [count[lv][o] / sum(count[lv].values()) for lv in groups]) for o in ("win", "draw", "loss")]
    return groups, series


def series(games, key):
    """(номер партии, значение поля) - для длины партии и разницы карт."""
    return [(g["n"], g[key]) for g in games]
