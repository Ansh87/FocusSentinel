"""Clock abstraction so the rules engine and its tests never call time.time()
or datetime.now() directly. This is what lets a 45-minute limit be exercised
in a few milliseconds of test time (see tests/test_rules_engine.py), and lets
the API inject a real, timezone-aware clock in production.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class Clock(ABC):
    @abstractmethod
    def now(self, tz: str = "UTC") -> datetime:
        """Return the current timezone-aware datetime in the given IANA tz."""


class RealClock(Clock):
    def now(self, tz: str = "UTC") -> datetime:
        return datetime.now(ZoneInfo(tz))


class SimulatedClock(Clock):
    """A controllable clock for tests. Starts at `start` (UTC-aware) and only
    advances when `advance()` is called, so tests can compress a 45-minute
    limit, a cross-midnight session, or a DST transition into instant
    assertions instead of real sleeps.
    """

    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("SimulatedClock requires a timezone-aware start datetime")
        self._current = start

    def now(self, tz: str = "UTC") -> datetime:
        return self._current.astimezone(ZoneInfo(tz))

    def advance(self, **timedelta_kwargs) -> None:
        self._current = self._current + timedelta(**timedelta_kwargs)

    def set(self, new_time: datetime) -> None:
        if new_time.tzinfo is None:
            raise ValueError("SimulatedClock.set requires a timezone-aware datetime")
        self._current = new_time
