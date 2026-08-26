from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hosaka_social.clock import FakeClock
from hosaka_social.engine import SocialEngine
from hosaka_social.events import AudioActivityEnded, AudioActivityStarted, EventBase, TranscriptFinalized
from hosaka_social.models import CandidateKind, ThoughtCandidate
from hosaka_social.social.governor import DecisionOutcome, DecisionTrace


def make_candidate(
    content: str,
    *,
    clock: FakeClock,
    kind: CandidateKind = CandidateKind.CHAMBERED_THOUGHT,
    relevance: float = 0.9,
    importance: float = 0.8,
    confidence: float = 0.8,
    urgency: float = 0.1,
    humor_value: float = 0.0,
    social_risk: float = 0.0,
    novelty: float = 0.6,
    topic_id: str | None = None,
    target_speaker_id: str | None = None,
) -> ThoughtCandidate:
    now = clock.wall_time()
    return ThoughtCandidate(
        kind=kind,
        content=content,
        relevance=relevance,
        importance=importance,
        confidence=confidence,
        urgency=urgency,
        humor_value=humor_value,
        social_risk=social_risk,
        novelty=novelty,
        topic_id=topic_id,
        target_speaker_id=target_speaker_id,
        created_at=now,
        expires_at=now,
    )


@dataclass
class ScriptTurn:
    at_ms: int
    speaker_id: str | None = None
    text: str | None = None
    topic_ids: list[str] = field(default_factory=list)
    vad: str | None = None
    candidate: ThoughtCandidate | None = None
    complete_speech: bool = False
    asr_confidence: float = 1.0


@dataclass
class SimulationReport:
    events: list[EventBase]
    traces: list[DecisionTrace]
    spoken_texts: list[str]
    agent_turn_share: float
    interrupt_count: int
    discarded_reasons: list[str]
    chamber_content: str | None
    outcomes: list[DecisionOutcome]

    @property
    def spoke(self) -> bool:
        return bool(self.spoken_texts)

    def discarded(self, reason_substr: str) -> bool:
        return any(reason_substr in r for r in self.discarded_reasons)


class ConversationSimulator:
    def __init__(self, engine: SocialEngine, clock: FakeClock, *, step_ms: int = 25) -> None:
        self.engine = engine
        self.clock = clock
        self.step_ms = step_ms

    async def run(self, script: list[ScriptTurn]) -> SimulationReport:
        for step in sorted(script, key=lambda s: s.at_ms):
            await self._advance_to(step.at_ms)
            if step.vad == "start":
                await self.engine.handle(
                    AudioActivityStarted(speaker_hint=step.speaker_id, confidence=1.0)
                )
            if step.text is not None and step.speaker_id is not None:
                wall: datetime = self.clock.wall_time()
                await self.engine.handle(
                    TranscriptFinalized(
                        speaker_id=step.speaker_id,
                        text=step.text,
                        asr_confidence=step.asr_confidence,
                        started_at=wall,
                        ended_at=wall,
                        topic_ids=list(step.topic_ids),
                    )
                )
            if step.vad == "end":
                await self.engine.handle(AudioActivityEnded(duration_ms=0))
            if step.candidate is not None:
                await self.engine.inject_candidate(step.candidate)
            if step.complete_speech:
                await self.engine.notify_speech_completed()
        await self.engine.tick()
        discarded = [
            e.reason
            for e in self.engine.emitted
            if e.event_type == "thought_candidate_discarded"
        ]
        interrupts = sum(
            1 for e in self.engine.emitted if e.event_type == "speech_interrupted"
        )
        chamber = self.engine.chamber.current
        return SimulationReport(
            events=list(self.engine.emitted),
            traces=list(self.engine.traces),
            spoken_texts=self.engine.spoken_texts(),
            agent_turn_share=self.engine.state.agent_turn_share,
            interrupt_count=interrupts,
            discarded_reasons=discarded,
            chamber_content=chamber.content if chamber else None,
            outcomes=[t.outcome for t in self.engine.traces],
        )

    async def _advance_to(self, target_ms: int) -> None:
        now_ms = int(round(self.clock.monotonic() * 1000))
        while now_ms < target_ms:
            step = min(self.step_ms, target_ms - now_ms)
            self.clock.advance_ms(step)
            await self.engine.tick()
            now_ms = int(round(self.clock.monotonic() * 1000))
