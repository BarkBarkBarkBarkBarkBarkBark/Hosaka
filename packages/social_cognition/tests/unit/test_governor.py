from __future__ import annotations

from datetime import datetime, timezone

from hosaka_social.config import SocialConfig
from hosaka_social.models import CandidateKind, CandidateStatus, ConversationState, ThoughtCandidate
from hosaka_social.social.cooldown import recent_speech_factor
from hosaka_social.social.governor import DecisionOutcome, SocialGovernor
from hosaka_social.social.turn_taking import floor_available


def _candidate(**kwargs: object) -> ThoughtCandidate:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base = dict(
        content="hi",
        created_at=now,
        expires_at=now,
        created_mono=0.0,
        expires_mono=45.0,
        relevance=0.9,
        importance=0.8,
        confidence=0.8,
        kind=CandidateKind.CHAMBERED_THOUGHT,
        status=CandidateStatus.CHAMBERED,
    )
    base.update(kwargs)
    return ThoughtCandidate(**base)  # type: ignore[arg-type]


def test_human_speech_hard_suppresses_unsolicited() -> None:
    gov = SocialGovernor(SocialConfig())
    state = ConversationState(human_speaking=True, silence_duration_ms=2000)
    trace = gov.evaluate(_candidate(), state, floor_open=False, now_mono=1.0)
    assert trace.outcome is DecisionOutcome.SUPPRESS
    assert "human_speaking" in trace.hard_inhibitors


def test_discarded_candidate_cannot_speak() -> None:
    gov = SocialGovernor(SocialConfig())
    state = ConversationState(silence_duration_ms=2000)
    cand = _candidate(status=CandidateStatus.DISCARDED)
    trace = gov.evaluate(cand, state, floor_open=True, now_mono=1.0)
    assert trace.outcome is DecisionOutcome.DISCARD
    assert "candidate_discarded" in trace.hard_inhibitors


def test_monotonic_recent_speech_factor() -> None:
    assert recent_speech_factor(None, 10.0, 8.0) == 0.0
    assert recent_speech_factor(10.0, 10.0, 8.0) == 1.0
    assert recent_speech_factor(10.0, 14.0, 8.0) == 0.5
    assert recent_speech_factor(10.0, 18.0, 8.0) == 0.0


def test_floor_closed_while_human_speaking() -> None:
    from hosaka_social.config import SilenceWindows

    state = ConversationState(human_speaking=True, silence_duration_ms=5000)
    assert not floor_available(state, _candidate(), SilenceWindows())


def test_floor_available_signature() -> None:
    from hosaka_social.config import SilenceWindows

    state = ConversationState(silence_duration_ms=1000)
    assert floor_available(state, _candidate(), SilenceWindows())
