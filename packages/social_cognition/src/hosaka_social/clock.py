from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def wall_time(self) -> datetime:
        ...

    def monotonic(self) -> float:
        ...


class SystemClock:
    def wall_time(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        import time

        return time.monotonic()


class FakeClock:
    """Deterministic clock. Tests advance time; they must not sleep()."""

    def __init__(self, start: datetime | None = None, *, mono: float = 0.0) -> None:
        self._wall = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self._mono = mono

    def wall_time(self) -> datetime:
        return self._wall

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot rewind FakeClock")
        self._mono += seconds
        self._wall = self._wall + timedelta(seconds=seconds)

    def advance_ms(self, milliseconds: float) -> None:
        self.advance(milliseconds / 1000.0)
