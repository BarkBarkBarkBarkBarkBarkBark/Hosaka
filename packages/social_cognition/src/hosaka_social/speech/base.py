from __future__ import annotations

from typing import Protocol, runtime_checkable

from hosaka_social.models import SpeechRequest


@runtime_checkable
class SpeechSink(Protocol):
    async def speak(self, request: SpeechRequest) -> None:
        ...

    async def cancel(self) -> None:
        ...

    def is_speaking(self) -> bool:
        ...


class MockSpeechSink:
    def __init__(self) -> None:
        self.requests: list[SpeechRequest] = []
        self.cancel_count = 0
        self.duck_count = 0
        self._speaking = False
        self.last_request: SpeechRequest | None = None

    async def speak(self, request: SpeechRequest) -> None:
        self.requests.append(request)
        self.last_request = request
        self._speaking = True

    async def cancel(self) -> None:
        self.cancel_count += 1
        self._speaking = False

    async def duck(self) -> None:
        self.duck_count += 1

    def is_speaking(self) -> bool:
        return self._speaking

    def mark_completed(self) -> None:
        self._speaking = False
