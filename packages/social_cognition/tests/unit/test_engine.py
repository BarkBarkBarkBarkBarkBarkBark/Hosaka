from __future__ import annotations

import pytest

from hosaka_social.clock import FakeClock
from hosaka_social.config import SocialConfig
from hosaka_social.engine import SocialEngine
from hosaka_social.events import AudioActivityStarted, TranscriptFinalized
from hosaka_social.face import BrokenFaceController
from hosaka_social.models import CandidateKind, CandidateStatus, ReflectionResult
from hosaka_social.providers import MockLLMProvider, StructuredOutputError
from hosaka_social.simulation import make_candidate
from hosaka_social.speech import MockSpeechSink, SpeechCoordinator, SpeechState


@pytest.mark.asyncio
async def test_malformed_structured_output_fails_closed() -> None:
    provider = MockLLMProvider()
    provider.enqueue_malformed()
    engine = SocialEngine(clock=FakeClock(), provider=provider, auto_reflect=True)
    await engine.handle(
        TranscriptFinalized(speaker_id="SPK_1", text="hello there")
    )
    assert engine.chamber.current is None
    assert engine.metrics["reflection_fail_closed_total"] == 1
    with pytest.raises(StructuredOutputError):
        provider.enqueue_malformed()
        await provider.generate_structured(
            [], ReflectionResult, temperature=0, timeout_seconds=1
        )


@pytest.mark.asyncio
async def test_barge_in_cancel_is_idempotent() -> None:
    clock = FakeClock()
    sink = MockSpeechSink()
    coord = SpeechCoordinator(sink, clock, SocialConfig().barge_in)
    cand = make_candidate("hello", clock=clock)
    started = await coord.start(cand)
    assert started is not None
    first = await coord.cancel(interrupted_by="human")
    second = await coord.cancel(interrupted_by="human")
    third = await coord.cancel(interrupted_by="human")
    assert first is not None
    assert second is None
    assert third is None
    assert sink.cancel_count == 1
    assert coord.state is SpeechState.IDLE
    assert not coord.is_active


@pytest.mark.asyncio
async def test_never_two_active_speech_ids() -> None:
    clock = FakeClock()
    sink = MockSpeechSink()
    coord = SpeechCoordinator(sink, clock, SocialConfig().barge_in)
    a = make_candidate("one", clock=clock)
    b = make_candidate("two", clock=clock)
    first = await coord.start(a)
    second = await coord.start(b)
    assert first is not None
    assert second is None
    assert coord.speech_id == first.speech_id


@pytest.mark.asyncio
async def test_expired_candidate_cannot_become_authorized() -> None:
    clock = FakeClock()
    engine = SocialEngine(clock=clock, auto_reflect=False)
    cand = make_candidate("stale", clock=clock, importance=0.1)
    await engine.inject_candidate(cand)
    clock.advance(engine.config.chamber.expiration.default_seconds + 1)
    await engine.tick()
    assert engine.chamber.current is None
    assert engine.metrics["candidates_expired_total"] == 1
    assert not engine.spoken_texts()


@pytest.mark.asyncio
async def test_discarded_candidate_cannot_become_speaking() -> None:
    clock = FakeClock()
    engine = SocialEngine(clock=clock, auto_reflect=False)
    cand = make_candidate("nope", clock=clock, relevance=0.05, importance=0.05, confidence=0.05)
    await engine.inject_candidate(cand)
    clock.advance(1.5)
    await engine.tick()
    if engine.chamber.current is not None:
        engine.chamber.current.status = CandidateStatus.DISCARDED
        await engine.tick()
    assert not engine.spoken_texts()
    assert all(t.candidate_id != str(cand.id) or t.outcome.value != "speak" for t in engine.traces[-3:])


@pytest.mark.asyncio
async def test_interrupted_thought_re_chambers_once() -> None:
    clock = FakeClock()
    engine = SocialEngine(clock=clock, auto_reflect=False)
    await engine.handle(
        TranscriptFinalized(speaker_id="A", text="retro consoles", topic_ids=["retro"])
    )
    await engine.inject_candidate(
        make_candidate(
            "PlayStation launched in Japan in 1994.",
            clock=clock,
            topic_id="retro",
            relevance=0.95,
            importance=0.85,
        )
    )
    clock.advance(1.0)
    await engine.tick()
    assert engine.state.agent_is_speaking
    clock.advance(0.4)
    await engine.handle(AudioActivityStarted(speaker_hint="A", confidence=1.0))
    clock.advance(0.3)
    await engine.tick()
    assert engine.metrics["speech_interrupted_total"] == 1
    assert not engine.state.agent_is_speaking
    current = engine.chamber.current
    assert current is not None
    assert current.kind is CandidateKind.INTERRUPTED_THOUGHT
    assert current.attempts == 1


@pytest.mark.asyncio
async def test_face_failure_does_not_crash() -> None:
    engine = SocialEngine(
        clock=FakeClock(),
        face=BrokenFaceController(),
        auto_reflect=False,
    )
    await engine.handle(TranscriptFinalized(speaker_id="A", text="hello"))
    await engine.inject_candidate(make_candidate("thought", clock=engine.clock))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_monotonic_timing_drives_cooldown() -> None:
    clock = FakeClock()
    engine = SocialEngine(clock=clock, auto_reflect=False)
    await engine.handle(TranscriptFinalized(speaker_id="A", text="topic", topic_ids=["x"]))
    await engine.inject_candidate(
        make_candidate("callback", clock=clock, topic_id="x", relevance=0.95, importance=0.8)
    )
    clock.advance(1.2)
    await engine.tick()
    assert engine.spoken_texts()
    await engine.notify_speech_completed()
    factor_now = engine.state.last_agent_speech_mono
    assert factor_now is not None
    await engine.inject_candidate(
        make_candidate("again", clock=clock, topic_id="x", relevance=0.95, importance=0.8)
    )
    await engine.tick()
    assert engine.traces[-1].negative["recent_agent_speech"] > 0.5
    clock.advance(engine.config.cooldown.recent_speech_seconds)
    await engine.tick()
    assert engine.traces[-1].negative["recent_agent_speech"] == 0.0


@pytest.mark.asyncio
async def test_conversation_state_has_no_raw_audio() -> None:
    engine = SocialEngine(clock=FakeClock(), auto_reflect=False)
    dumped = engine.state.model_dump()
    blob = str(dumped).lower()
    assert "audio" not in blob
    assert "pcm" not in blob
    assert "wav" not in blob


@pytest.mark.asyncio
async def test_reflect_chambered_forces_kind() -> None:
    provider = MockLLMProvider()
    provider.enqueue_structured(
        ReflectionResult(
            candidate_worth_generating=True,
            candidate_kind="direct_response",
            relevance=0.9,
            content="later thought",
        )
    )
    clock = FakeClock()
    engine = SocialEngine(clock=clock, provider=provider, auto_reflect=False)
    await engine.handle(TranscriptFinalized(speaker_id="s", text="hello there"))
    await engine.reflect_chambered()
    assert engine.chamber.current is not None
    assert engine.chamber.current.kind is CandidateKind.CHAMBERED_THOUGHT
    assert engine.chamber.current.content == "later thought"
