"""Ход ИИ и «Мысли ИИ» в отдельном потоке: окно не подвисает.

Каждый запрос получает номер (token). Ответ со старым номером (партию начали заново,
вышли в меню) выбрасывается. Остановка - флагом threading.Event: поиск проверяет его
между раскладками; при закрытии окна потоки ждут не дольше 2 секунд (контракт aikit).

В поток уходит только наблюдение (observation) - не состояние партии: ИИ и тут не может
подсмотреть чужие карты.
"""
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal

from game.ai import tracker
from game.ai.agents import make_agent

MOVE_TIME = {"novice": None, "medium": 1.0, "strong": 1.5}
THOUGHT_SAMPLES = 16


class _Job(QThread):
    done = Signal(int, str, object)

    def __init__(self, token, kind, fn, parent=None):
        super().__init__(parent)
        self.token = token
        self.kind = kind
        self.fn = fn
        self.stop_event = threading.Event()

    def run(self):
        try:
            payload = self.fn(self.stop_event)
        except Exception as e:  # noqa: BLE001 - ошибку покажет окно, поток не должен падать молча
            payload = e
        if not self.stop_event.is_set():
            self.done.emit(self.token, self.kind, payload)


class AiController(QObject):
    """request_move(token, obs, level, seed) и request_thoughts(token, obs, level, seed).
    Ответ - сигнал ready(token, 'move' | 'thoughts', результат или ошибка)."""

    ready = Signal(int, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = []

    @staticmethod
    def agent(level):
        """Новый агент на каждый запрос: у точного перебора своя память, а отменённый
        поиск может ещё досчитываться в старом потоке. Сеть общая и только читается."""
        kw = {}
        if level in ("medium", "strong"):
            kw["time_limit"] = MOVE_TIME[level]
        return make_agent(level, **kw)

    def _start(self, token, kind, fn):
        self._reap()
        job = _Job(token, kind, fn, self)
        job.done.connect(self.ready)
        self.jobs.append(job)
        job.start()
        return job

    def _reap(self):
        self.jobs = [j for j in self.jobs if j.isRunning()]

    def request_move(self, token, obs, level, seed):
        agent = self.agent(level)

        def fn(stop):
            if level in ("medium", "strong"):
                return agent.choose(obs, seed=seed, stop=stop)
            return agent.choose(obs, seed=seed)
        return self._start(token, "move", fn)

    def request_thoughts(self, token, obs, seed):
        """Учёт карт и оценка каждого допустимого хода сильным поиском - для игрока obs."""
        from game.ai.search import SearchAgent
        thinker = SearchAgent.for_level("strong", samples=THOUGHT_SAMPLES, time_limit=1.0)

        def fn(stop):
            belief = tracker.belief(obs)
            scores = thinker.analyze(obs, seed=seed, stop=stop) if len(obs.legal) > 1 else \
                [(m, 0.0) for m in obs.legal]
            return {"player": obs.player, "belief": belief, "scores": scores}
        return self._start(token, "thoughts", fn)

    def cancel(self):
        for j in self.jobs:
            j.stop_event.set()

    def busy(self):
        self._reap()
        return bool(self.jobs)

    def shutdown(self, timeout_ms=2000):
        """Остановить все поиски и дождаться потоков (не дольше timeout_ms на всё)."""
        self.cancel()
        deadline = time.monotonic() + timeout_ms / 1000
        for j in self.jobs:
            left = max(0, int((deadline - time.monotonic()) * 1000))
            j.wait(left)
        self._reap()
        return not self.jobs
