from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hosaka_social.bus import EventBus
from hosaka_social.clock import Clock, FakeClock
from hosaka_social.config import SocialConfig
from hosaka_social.events import (
    AgentAddressed,
    AudioActivityEnded,
    AudioActivityStarted,
    EventBase,
    FaceStateChanged,
    SpeechAuthorized,
    SpeechCompleted,
    SpeechInterrupted,
    SpeechOpportunityDetected,
    SpeechStarted,
    SpeechSuppressed,
    ThoughtCandidateCreated,
    ThoughtCandidateDiscarded,
    ThoughtCandidateUpdated,
    TranscriptFinalized,
    TranscriptPartial,
)
from hosaka_social.face.base import FaceController, FaceEvent, FaceState, NullFaceController
from hosaka_social.models import (
    CandidateKind,
    CandidateStatus,
    ConversationState,
    InternalState,
    Message,
    ReflectionResult,
    ThoughtCandidate,
    Utterance,
)
from hosaka_social.providers.base import LLMProvider, StructuredOutputError
from hosaka_social.providers.mock import MockLLMProvider
from hosaka_social.social.chamber import Chamber
from hosaka_social.social.governor import DecisionOutcome, DecisionTrace, SocialGovernor
from hosaka_social.social.turn_taking import floor_available
from hosaka_social.speech.base import MockSpeechSink, SpeechSink
from hosaka_social.speech.coordinator import SpeechCoordinator
from hosaka_social.state import ConversationStore


class SocialEngine:
    """Authoritative owner of conversation state, chamber, and speech decisions."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        config: SocialConfig | None = None,
        provider: LLMProvider | None = None,
        speech_sink: SpeechSink | None = None,
        face: FaceController | None = None,
        auto_reflect: bool = True,
        on_decision: Callable[[DecisionTrace], None] | None = None,
    ) -> None:
        self.clock = clock or FakeClock()
        self.config = config or SocialConfig()
        self.provider = provider or MockLLMProvider()
        self.speech_sink = speech_sink or MockSpeechSink()
        self.face = face or NullFaceController()
        self.auto_reflect = auto_reflect
        self.on_decision = on_decision
        self.bus = EventBus(self.clock)
        self.store = ConversationStore(self.config.memory, self.clock)
        self.chamber = Chamber(self.config, self.clock)
        self.governor = SocialGovernor(self.config)
        self.speech = SpeechCoordinator(
            self.speech_sink, self.clock, self.config.barge_in
        )
        self.emitted: list[EventBase] = []
        self.traces: list[DecisionTrace] = []
        self.metrics: dict[str, int] = {
            "utterances_received_total": 0,
            "direct_responses_generated_total": 0,
            "candidates_generated_total": 0,
            "candidates_spoken_total": 0,
            "candidates_expired_total": 0,
            "candidates_replaced_total": 0,
            "speech_suppressed_total": 0,
            "speech_interrupted_total": 0,
            "reflection_noop_total": 0,
            "reflection_fail_closed_total": 0,
        }
        self._last_activity_mono = self.clock.monotonic()
        self._last_utterance_mono: float | None = None
        self._last_face: FaceState | None = None
        self._partial_stable_text: str | None = None

    @property
    def state(self) -> ConversationState:
        snap = self.store.conversation.model_copy(deep=True)
        snap.chamber = (
            self.chamber.current.model_copy(deep=True) if self.chamber.current else None
        )
        return snap

    @property
    def internal(self) -> InternalState:
        inward = self.store.internal.model_copy(deep=True)
        current = self.chamber.current
        inward.chamber_candidate_id = current.id if current else None
        inward.urge_to_speak = current.relevance if current else 0.0
        inward.suppression = 1.0 if self.store.conversation.human_speaking else 0.2
        if self.store.conversation.recent_utterances:
            inward.attention_target = self.store.conversation.primary_speaker
            inward.attention_strength = 0.7
        return inward

    async def handle(self, event: EventBase) -> list[EventBase]:
        before = len(self.emitted)
        if not self.bus.publish(event):
            return []
        await self._apply(event)
        await self.tick()
        return self.emitted[before:]

    async def tick(self) -> list[EventBase]:
        before = len(self.emitted)
        now = self.clock.monotonic()
        conv = self.store.conversation
        if not conv.human_speaking and not conv.agent_is_speaking:
            conv.silence_duration_ms = int((now - self._last_activity_mono) * 1000)
        elif conv.human_speaking or conv.agent_is_speaking:
            conv.silence_duration_ms = 0

        if self.chamber.decay(now):
            current = self.chamber.current
            if current is not None:
                self._emit(ThoughtCandidateUpdated(candidate_id=current.id))

        expired = self.chamber.expire(now)
        if expired is not None:
            self.metrics["candidates_expired_total"] += 1
            self._emit(
                ThoughtCandidateDiscarded(candidate_id=expired.id, reason="expired")
            )

        barge_events = await self.speech.evaluate_barge_in(
            now, human_speaking=conv.human_speaking
        )
        for item in barge_events:
            self._emit(item)
            if isinstance(item, SpeechInterrupted):
                await self._on_interrupted(item)

        await self._maybe_authorize()
        await self._sync_face()
        return self.emitted[before:]

    async def inject_candidate(self, candidate: ThoughtCandidate) -> list[EventBase]:
        before = len(self.emitted)
        self.metrics["candidates_generated_total"] += 1
        if candidate.kind == CandidateKind.DIRECT_RESPONSE:
            self.metrics["direct_responses_generated_total"] += 1
        candidate.conversation_generation = self.store.conversation.conversation_generation
        evicted, action = self.chamber.offer(candidate)
        if action == "rejected_weaker" or action == "rejected_busy":
            candidate.status = CandidateStatus.DISCARDED
            self._emit(
                ThoughtCandidateDiscarded(
                    candidate_id=candidate.id, reason=action
                )
            )
        else:
            placed = self.chamber.current
            assert placed is not None
            self._emit(ThoughtCandidateCreated(candidate_id=placed.id))
            if evicted is not None:
                self.metrics["candidates_replaced_total"] += 1
                evicted.status = CandidateStatus.DISCARDED
                self._emit(
                    ThoughtCandidateDiscarded(
                        candidate_id=evicted.id, reason=action
                    )
                )
        self.store.conversation.chamber = self.chamber.current
        await self._maybe_authorize()
        await self._sync_face()
        return self.emitted[before:]

    async def notify_speech_completed(self) -> None:
        speech_id = await self.speech.complete()
        if speech_id is None:
            return
        self._on_speech_finished(completed=True)
        self._emit(SpeechCompleted(speech_id=speech_id))
        await self._sync_face()

    def mute(self) -> None:
        self.store.conversation.muted = True

    def unmute(self) -> None:
        self.store.conversation.muted = False

    async def clear_chamber(self) -> None:
        dropped = self.chamber.clear()
        if dropped is not None:
            self._emit(
                ThoughtCandidateDiscarded(candidate_id=dropped.id, reason="cleared")
            )
        self.store.conversation.chamber = None

    def reset_session(self) -> None:
        self.store = ConversationStore(self.config.memory, self.clock)
        self.chamber = Chamber(self.config, self.clock)
        self._last_activity_mono = self.clock.monotonic()
        self._last_utterance_mono = None

    async def _apply(self, event: EventBase) -> None:
        if isinstance(event, TranscriptFinalized):
            await self._on_transcript(event)
        elif isinstance(event, TranscriptPartial):
            self._on_partial(event)
        elif isinstance(event, AudioActivityStarted):
            await self._on_vad_start(event)
        elif isinstance(event, AudioActivityEnded):
            self._on_vad_end(event)

    async def _on_transcript(self, event: TranscriptFinalized) -> None:
        now_wall = event.ended_at or self.clock.wall_time()
        started = event.started_at or now_wall
        conv = self.store.conversation
        name = self.config.agent_name.lower()
        text = event.text
        if event.addressed_agent_probability is not None:
            addressed = event.addressed_agent_probability
            address_method = "external"
        else:
            addressed = 1.0 if name in text.lower() else 0.0
            address_method = "wake_name"
        utterance = Utterance(
            id=event.utterance_id,
            speaker_id=event.speaker_id,
            text=text,
            asr_confidence=event.asr_confidence,
            started_at=started,
            ended_at=now_wall,
            addressed_agent_probability=addressed,
            topic_ids=list(event.topic_ids),
        )
        now_mono = self.clock.monotonic()
        if self._last_utterance_mono is not None:
            gap = now_mono - self._last_utterance_mono
            if gap < 1.0:
                conv.rapid_exchange_score = min(1.0, conv.rapid_exchange_score + 0.3)
            else:
                conv.rapid_exchange_score = max(0.0, conv.rapid_exchange_score - min(gap * 0.2, 0.5))
        self._last_utterance_mono = now_mono
        self._last_activity_mono = now_mono
        conv.human_speaking = False
        conv.overlapping_human_speech = False
        conv.silence_duration_ms = 0
        self.store.add_utterance(utterance)
        self.metrics["utterances_received_total"] += 1
        if addressed >= self.config.direct_address_probability:
            self._emit(
                AgentAddressed(
                    utterance_id=utterance.id,
                    probability=addressed,
                    detection_method=address_method,
                )
            )
        drifted = self.chamber.discard_if_topic_changed(conv.current_topics)
        if drifted is not None:
            self._emit(
                ThoughtCandidateDiscarded(
                    candidate_id=drifted.id, reason="topic_change"
                )
            )
        if self.auto_reflect:
            await self._reflect(utterance)

    async def reflect_chambered(self, *, timeout_seconds: float = 8.0) -> None:
        """Background reflection that may only produce a later callback."""
        if not self.store.conversation.recent_utterances:
            return
        await self._reflect(
            self.store.conversation.recent_utterances[-1],
            force_kind=CandidateKind.CHAMBERED_THOUGHT,
            timeout_seconds=timeout_seconds,
        )

    def _on_partial(self, event: TranscriptPartial) -> None:
        self._partial_stable_text = event.text
        if event.stability < 0.85:
            return
        name = self.config.agent_name.lower()
        if name in event.text.lower():
            self.store.internal.attention_target = event.speaker_id
            self.store.internal.attention_strength = max(
                self.store.internal.attention_strength, 0.4
            )

    async def _on_vad_start(self, event: AudioActivityStarted) -> None:
        conv = self.store.conversation
        conv.human_speaking = True
        conv.silence_duration_ms = 0
        self._last_activity_mono = self.clock.monotonic()
        if conv.agent_is_speaking:
            conv.overlapping_human_speech = True
            self.speech.note_human_audio(self.clock.monotonic())
        if event.speaker_hint:
            conv.primary_speaker = event.speaker_hint

    def _on_vad_end(self, event: AudioActivityEnded) -> None:  # noqa: ARG002
        conv = self.store.conversation
        conv.human_speaking = False
        conv.overlapping_human_speech = False
        self.speech.clear_human_audio()
        self._last_activity_mono = self.clock.monotonic()
        conv.silence_duration_ms = 0

    async def _reflect(
        self,
        utterance: Utterance,
        *,
        force_kind: CandidateKind | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        try:
            result = await self.provider.generate_structured(
                [Message(role="user", content=utterance.text)],
                ReflectionResult,
                temperature=0.2,
                timeout_seconds=timeout_seconds,
            )
        except StructuredOutputError:
            self.metrics["reflection_fail_closed_total"] += 1
            return
        except Exception:
            self.metrics["reflection_fail_closed_total"] += 1
            return
        if not result.candidate_worth_generating or not result.content:
            self.metrics["reflection_noop_total"] += 1
            return
        kind_raw = result.candidate_kind or "chambered_thought"
        try:
            kind = force_kind or CandidateKind(kind_raw)
        except ValueError:
            kind = force_kind or CandidateKind.CHAMBERED_THOUGHT
        if force_kind is not None:
            kind = force_kind
        candidate = ThoughtCandidate(
            kind=kind,
            content=result.content,
            source_utterance_ids=[utterance.id],
            topic_id=utterance.topic_ids[0] if utterance.topic_ids else None,
            confidence=0.7,
            relevance=result.relevance,
            importance=0.7 if kind == CandidateKind.CHAMBERED_THOUGHT else 0.8,
            created_at=self.clock.wall_time(),
            expires_at=self.clock.wall_time(),
        )
        await self.inject_candidate(candidate)

    async def _maybe_authorize(self) -> None:
        conv = self.store.conversation
        conv.chamber = self.chamber.current
        candidate = self.chamber.current
        if candidate is None:
            return
        windows = self.config.turn_taking.silence_windows_ms
        open_floor = floor_available(conv, candidate, windows)
        if (
            open_floor
            and conv.silence_duration_ms >= windows.minimal_gap
            and not any(
                isinstance(e, SpeechOpportunityDetected) and e.silence_ms == conv.silence_duration_ms
                for e in self.emitted[-8:]
            )
        ):
            self._emit(
                SpeechOpportunityDetected(
                    silence_ms=conv.silence_duration_ms, confidence=0.8
                )
            )
        trace = self.governor.evaluate(
            candidate,
            conv,
            floor_open=open_floor,
            now_mono=self.clock.monotonic(),
        )
        self.traces.append(trace)
        if self.on_decision is not None:
            self.on_decision(trace)
        self.store.internal.urge_to_speak = trace.score
        if trace.outcome == DecisionOutcome.NO_ACTION:
            return
        if trace.outcome == DecisionOutcome.DISCARD:
            dropped = self.chamber.clear()
            if dropped is not None:
                self._emit(
                    ThoughtCandidateDiscarded(
                        candidate_id=dropped.id,
                        reason=";".join(trace.reasons) or "discard",
                    )
                )
            return
        if trace.outcome == DecisionOutcome.SUPPRESS:
            self.metrics["speech_suppressed_total"] += 1
            self._emit(
                SpeechSuppressed(candidate_id=candidate.id, reasons=trace.reasons)
            )
            return
        if trace.outcome == DecisionOutcome.HOLD:
            return
        if trace.outcome in {DecisionOutcome.SPEAK, DecisionOutcome.INTERRUPT}:
            await self._start_speech(candidate, trace.score)

    async def _start_speech(self, candidate: ThoughtCandidate, score: float) -> None:
        if self.speech.is_active:
            return
        if candidate.status == CandidateStatus.DISCARDED:
            return
        if self.clock.monotonic() >= candidate.expires_mono:
            candidate.status = CandidateStatus.DISCARDED
            self.chamber.current = None
            self._emit(
                ThoughtCandidateDiscarded(candidate_id=candidate.id, reason="expired")
            )
            return
        candidate.status = CandidateStatus.AUTHORIZED
        self._emit(SpeechAuthorized(candidate_id=candidate.id, decision_score=score))
        started = await self.speech.start(candidate)
        if started is None:
            if candidate.status == CandidateStatus.AUTHORIZED:
                candidate.status = CandidateStatus.CHAMBERED
            return
        candidate.status = CandidateStatus.SPEAKING
        self.store.conversation.agent_is_speaking = True
        self.store.conversation.silence_duration_ms = 0
        self.metrics["candidates_spoken_total"] += 1
        self._emit(started)

    def _on_speech_finished(self, *, completed: bool) -> None:
        conv = self.store.conversation
        current = self.chamber.current
        if current is not None and current.status in {
            CandidateStatus.SPEAKING,
            CandidateStatus.AUTHORIZED,
        }:
            current.status = (
                CandidateStatus.COMPLETED if completed else CandidateStatus.INTERRUPTED
            )
            if completed:
                self.chamber.current = None
                conv.chamber = None
        conv.agent_is_speaking = False
        if completed or not conv.human_speaking:
            conv.overlapping_human_speech = False
        if completed:
            self.store.record_agent_turn()
        self._last_activity_mono = self.clock.monotonic()

    async def _on_interrupted(self, event: SpeechInterrupted) -> None:
        self.metrics["speech_interrupted_total"] += 1
        current = self.chamber.current
        self._on_speech_finished(completed=False)
        if current is None:
            return
        kept = self.chamber.re_chamber_interrupted(
            current, self.store.conversation.current_topics
        )
        if kept:
            self._emit(ThoughtCandidateUpdated(candidate_id=current.id))
        else:
            self._emit(
                ThoughtCandidateDiscarded(
                    candidate_id=current.id, reason="interrupt_no_rechamber"
                )
            )
        await self._safe_face("react", FaceEvent.INTERRUPTION)

    def _emit(self, event: EventBase) -> None:
        self.bus.wrap(event)
        self.emitted.append(event)

    async def _sync_face(self) -> None:
        conv = self.store.conversation
        if conv.agent_is_speaking:
            desired = FaceState.SPEAKING
        elif conv.human_speaking:
            desired = FaceState.LISTENING
        elif self.chamber.current is not None:
            desired = FaceState.CHAMBERED
        else:
            desired = FaceState.IDLE
        if desired == self._last_face:
            return
        self._last_face = desired
        ok = await self._safe_face("set_state", desired)
        if ok:
            self._emit(FaceStateChanged(state=desired.value))

    async def _safe_face(self, method: str, arg: Any) -> bool:
        try:
            await getattr(self.face, method)(arg)
            return True
        except Exception:
            return False

    def spoken_texts(self) -> list[str]:
        requests = getattr(self.speech_sink, "requests", None)
        if not requests:
            return []
        return [r.text for r in requests]
