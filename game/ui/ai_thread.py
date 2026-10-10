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


_ORPHANS = []
_UNDERTAKER = None


class _Undertaker(QObject):
    """Живёт в потоке окна: сигнал finished сироты приходит сюда очередью, а не в сам поток."""

    def bury(self):
        for j in list(_ORPHANS):
            if j.isFinished():
                j.wait()
                _ORPHANS.remove(j)


def _undertaker():
    global _UNDERTAKER
    if _UNDERTAKER is None:
        _UNDERTAKER = _Undertaker()
    return _UNDERTAKER


class _Job(QThread):
    done = Signal(int, str, object)

    def __init__(self, token, kind, fn):
        super().__init__()
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
        # Без родителя: поток живёт, пока на него есть ссылка в self.jobs (или в _ORPHANS).
        # В 0.9.0 он был дочерним объектом контроллера и копился до закрытия окна (около 45
        # за партию вдвоём, вместе с агентом и наблюдением). А разрушение окна с ещё
        # работающим дочерним QThread - это qFatal «Destroyed while thread is still
        # running» и падение всей программы.
        job = _Job(token, kind, fn)
        job.done.connect(self.ready)
        job.finished.connect(self._reap)        # слот контроллера: выполняется в потоке окна
        self.jobs.append(job)
        job.start()
        return job

    def _reap(self):
        """Кончившиеся потоки - из списка; последняя ссылка уходит, объект удаляется."""
        alive = []
        for j in self.jobs:
            if j.isFinished():
                j.wait()                        # поток вышел целиком, удалять безопасно
            elif j.isRunning():
                alive.append(j)
        self.jobs = alive

    def request_move(self, token, obs, level, seed):
        agent = self.agent(level)

        def fn(stop):
            if level in ("medium", "strong"):
                return agent.choose(obs, seed=seed, stop=stop)
            return agent.choose(obs, seed=seed)
        return self._start(token, "move", fn)

    def request_thoughts(self, token, obs, seed, level="strong"):
        """Учёт карт и оценка каждого допустимого хода сильным поиском - для игрока obs.
        level="novice": новичок ходы не оценивает, вместо оценок - ход, который выбирают
        его правила (поле "novice")."""
        from game.ai.search import SearchAgent
        thinker = SearchAgent.for_level("strong", samples=THOUGHT_SAMPLES, time_limit=1.0)

        def fn(stop):
            belief = tracker.belief(obs)
            if level == "novice":
                return {"player": obs.player, "belief": belief, "scores": [],
                        "novice": make_agent("novice").choose(obs) if obs.legal else None}
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
        # Не успевшие остановиться (машина перегружена) уходят в _ORPHANS: окно можно
        # разрушать, поток доработает до флага остановки сам и только потом удалится.
        for j in self.jobs:
            j.done.disconnect(self.ready)
            _ORPHANS.append(j)
            j.finished.connect(_undertaker().bury)
        self.jobs = []
        _undertaker().bury()
        return not _ORPHANS
