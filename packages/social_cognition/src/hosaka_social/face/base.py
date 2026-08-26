from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class FaceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    CHAMBERED = "chambered"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    EXCITED = "excited"
    CONFUSED = "confused"
    SLEEPING = "sleeping"


class FaceEvent(str, Enum):
    HUMAN_SPEECH = "human_speech"
    AGENT_SPEECH = "agent_speech"
    INTERRUPTION = "interruption"


@runtime_checkable
class FaceController(Protocol):
    async def show(self) -> None:
        ...

    async def hide(self) -> None:
        ...

    async def set_state(self, state: FaceState) -> None:
        ...

    async def react(self, event: FaceEvent) -> None:
        ...


class NullFaceController:
    def __init__(self) -> None:
        self.states: list[FaceState] = []
        self.events: list[FaceEvent] = []
        self.visible = False

    async def show(self) -> None:
        self.visible = True

    async def hide(self) -> None:
        self.visible = False

    async def set_state(self, state: FaceState) -> None:
        self.states.append(state)

    async def react(self, event: FaceEvent) -> None:
        self.events.append(event)


class BrokenFaceController:
    """Used in tests to prove face failures do not crash cognition."""

    async def show(self) -> None:
        raise RuntimeError("face down")

    async def hide(self) -> None:
        raise RuntimeError("face down")

    async def set_state(self, state: FaceState) -> None:
        raise RuntimeError("face down")

    async def react(self, event: FaceEvent) -> None:
        raise RuntimeError("face down")
