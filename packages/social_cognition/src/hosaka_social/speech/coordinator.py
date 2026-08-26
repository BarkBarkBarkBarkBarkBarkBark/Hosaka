from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4

from hosaka_social.clock import Clock
from hosaka_social.config import BargeInConfig
from hosaka_social.events import SpeechDucked, SpeechInterrupted, SpeechStarted
from hosaka_social.models import SpeechRequest, ThoughtCandidate
from hosaka_social.speech.base import SpeechSink


class SpeechState(str, Enum):
    IDLE = "idle"
    AUTHORIZED = "authorized"
    STARTING = "starting"
    SPEAKING = "speaking"
    DUCKING = "ducking"
    CANCELLING = "cancelling"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"


class SpeechCoordinator:
    """Authoritative speech state machine. At most one active speech_id."""

    def __init__(self, sink: SpeechSink, clock: Clock, barge_in: BargeInConfig) -> None:
        self.sink = sink
        self.clock = clock
        self.barge_in = barge_in
        self.state = SpeechState.IDLE
        self.speech_id: UUID | None = None
        self.candidate_id: UUID | None = None
        self.started_mono: float | None = None
        self._barge_start_mono: float | None = None
        self._cancel_token = 0

    @property
    def is_active(self) -> bool:
        return self.state in {
            SpeechState.AUTHORIZED,
            SpeechState.STARTING,
            SpeechState.SPEAKING,
            SpeechState.DUCKING,
            SpeechState.CANCELLING,
        }

    async def start(self, candidate: ThoughtCandidate) -> SpeechStarted | None:
        if self.is_active:
            return None
        self.state = SpeechState.AUTHORIZED
        self.speech_id = uuid4()
        self.candidate_id = candidate.id
        self._barge_start_mono = None
        self._cancel_token += 1
        token = self._cancel_token
        request = SpeechRequest(
            speech_id=self.speech_id,
            candidate_id=candidate.id,
            text=candidate.content,
        )
        self.state = SpeechState.STARTING
        await self.sink.speak(request)
        if token != self._cancel_token:
            return None
        self.state = SpeechState.SPEAKING
        self.started_mono = self.clock.monotonic()
        return SpeechStarted(speech_id=self.speech_id, candidate_id=candidate.id)

    async def complete(self) -> UUID | None:
        if self.state not in {
            SpeechState.AUTHORIZED,
            SpeechState.STARTING,
            SpeechState.SPEAKING,
            SpeechState.DUCKING,
        }:
            return None
        speech_id = self.speech_id
        self.state = SpeechState.COMPLETED
        self._reset()
        if hasattr(self.sink, "mark_completed"):
            self.sink.mark_completed()
        return speech_id

    async def cancel(self, *, interrupted_by: str | None = None) -> SpeechInterrupted | None:
        if not self.is_active and self.state not in {SpeechState.SPEAKING, SpeechState.DUCKING}:
            return None
        self.state = SpeechState.CANCELLING
        self._cancel_token += 1
        await self.sink.cancel()
        speech_id = self.speech_id
        fraction = 0.0
        if self.started_mono is not None:
            fraction = min(1.0, max(0.0, (self.clock.monotonic() - self.started_mono) / 4.0))
        event = SpeechInterrupted(
            speech_id=speech_id or uuid4(),
            interrupted_by=interrupted_by,
            spoken_fraction=fraction,
        )
        self.state = SpeechState.INTERRUPTED
        self._reset()
        return event

    def note_human_audio(self, now_mono: float) -> None:
        if self.state in {SpeechState.SPEAKING, SpeechState.DUCKING, SpeechState.STARTING}:
            if self._barge_start_mono is None:
                self._barge_start_mono = now_mono

    def clear_human_audio(self) -> None:
        self._barge_start_mono = None

    async def evaluate_barge_in(
        self, now_mono: float, *, human_speaking: bool
    ) -> list[SpeechDucked | SpeechInterrupted]:
        emitted: list[SpeechDucked | SpeechInterrupted] = []
        if not human_speaking or self._barge_start_mono is None:
            return emitted
        if not self.is_active and self.state != SpeechState.DUCKING:
            return emitted
        elapsed_ms = (now_mono - self._barge_start_mono) * 1000.0
        if elapsed_ms >= self.barge_in.cancel_after_ms:
            interrupted = await self.cancel(interrupted_by="human")
            if interrupted is not None:
                emitted.append(interrupted)
            return emitted
        if elapsed_ms >= self.barge_in.duck_after_ms and self.state == SpeechState.SPEAKING:
            self.state = SpeechState.DUCKING
            duck = getattr(self.sink, "duck", None)
            if duck is not None:
                await duck()
            if self.speech_id is not None:
                emitted.append(SpeechDucked(speech_id=self.speech_id))
        return emitted

    def _reset(self) -> None:
        self.speech_id = None
        self.candidate_id = None
        self.started_mono = None
        self._barge_start_mono = None
        if self.state in {SpeechState.INTERRUPTED, SpeechState.COMPLETED}:
            # terminal snapshot then idle
            self.state = SpeechState.IDLE
        else:
            self.state = SpeechState.IDLE
