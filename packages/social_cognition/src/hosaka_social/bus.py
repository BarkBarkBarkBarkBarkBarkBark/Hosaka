from __future__ import annotations

import asyncio
from collections import deque
from uuid import UUID

from hosaka_social.clock import Clock
from hosaka_social.events import CANCEL_EVENT_TYPES, AnyEvent, EventBase


class EventBus:
    """In-process bus. Cancellation-class events sort first. Duplicate ids are ignored."""

    def __init__(self, clock: Clock, *, seen_limit: int = 4096) -> None:
        self._clock = clock
        self._seq = 0
        self._queue: asyncio.PriorityQueue[tuple[int, int, EventBase]] = (
            asyncio.PriorityQueue()
        )
        self._seen: deque[UUID] = deque(maxlen=seen_limit)
        self._seen_set: set[UUID] = set()

    def wrap(self, event: EventBase) -> EventBase:
        self._seq += 1
        event.sequence_number = self._seq
        event.wall_time = self._clock.wall_time()
        event.monotonic_time = self._clock.monotonic()
        return event

    def publish(self, event: EventBase) -> bool:
        if event.event_id in self._seen_set:
            return False
        if event.sequence_number == 0 or event.monotonic_time is None:
            self.wrap(event)
        self._remember(event.event_id)
        priority = 0 if event.event_type in CANCEL_EVENT_TYPES else 10  # type: ignore[attr-defined]
        self._queue.put_nowait((priority, event.sequence_number, event))
        return True

    async def get(self) -> EventBase:
        _priority, _seq, event = await self._queue.get()
        return event

    def empty(self) -> bool:
        return self._queue.empty()

    def _remember(self, event_id: UUID) -> None:
        if len(self._seen) == self._seen.maxlen and self._seen:
            oldest = self._seen[0]
            self._seen_set.discard(oldest)
        self._seen.append(event_id)
        self._seen_set.add(event_id)


__all__ = ["EventBus", "AnyEvent"]
