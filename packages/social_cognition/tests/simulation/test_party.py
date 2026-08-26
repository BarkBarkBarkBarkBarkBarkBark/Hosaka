from __future__ import annotations

import pytest

from hosaka_social import (
    CandidateKind,
    ConversationSimulator,
    FakeClock,
    MockLLMProvider,
    ScriptTurn,
    SocialEngine,
    make_candidate,
)


def _engine(clock: FakeClock) -> SocialEngine:
    return SocialEngine(
        clock=clock,
        provider=MockLLMProvider(),
        auto_reflect=False,
    )


@pytest.mark.asyncio
async def test_normal_party_mostly_silent() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    sim = ConversationSimulator(engine, clock)
    speakers = ["SPK_1", "SPK_2", "SPK_3", "SPK_4"]
    lines = [
        "anyway I brought chips",
        "nice those are good",
        "did you see the new season",
        "yeah last night",
        "wait who died",
        "no spoilers",
        "fine fine",
        "pass me a beer",
        "the soundtrack slaps",
        "put it on later",
        "my controller drifted",
        "use the other one",
        "this couch is a trap",
        "move over",
        "ok ok",
        "what time is it",
    ]
    script: list[ScriptTurn] = []
    t = 0
    thought = make_candidate(
        "One thing from earlier — Sheep supports multiplayer.",
        clock=clock,
        topic_id="party",
        relevance=0.7,
        importance=0.5,
    )
    for i, line in enumerate(lines):
        script.append(
            ScriptTurn(
                at_ms=t,
                speaker_id=speakers[i % 4],
                text=line,
                topic_ids=["party"],
                candidate=thought if i == 3 else None,
            )
        )
        t += 280
    report = await sim.run(script)
    assert report.agent_turn_share <= 0.20
    assert not report.spoke


@pytest.mark.asyncio
async def test_direct_question_gets_response() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    sim = ConversationSimulator(engine, clock)
    chambered = make_candidate(
        "Sheep supports multiplayer.",
        clock=clock,
        topic_id="games",
        relevance=0.99,
        importance=0.9,
    )
    direct = make_candidate(
        "Crash Team Racing is a solid two-player pick.",
        clock=clock,
        kind=CandidateKind.DIRECT_RESPONSE,
        topic_id="games",
        relevance=0.95,
        importance=0.9,
        confidence=0.9,
    )
    report = await sim.run(
        [
            ScriptTurn(at_ms=0, speaker_id="A", text="retro games tonight", topic_ids=["games"], candidate=chambered),
            ScriptTurn(
                at_ms=400,
                speaker_id="A",
                text="Hey Hosaka, what's the best two-player game here?",
                topic_ids=["games"],
                candidate=direct,
            ),
            ScriptTurn(at_ms=1100, complete_speech=True),
        ]
    )
    assert report.spoke
    assert "Crash Team Racing" in report.spoken_texts[0]
    assert all("Sheep" not in t for t in report.spoken_texts)


@pytest.mark.asyncio
async def test_good_thought_waits_then_releases() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    sim = ConversationSimulator(engine, clock)
    thought = make_candidate(
        "One thing from earlier — the PlayStation launched in Japan in 1994.",
        clock=clock,
        topic_id="retro",
        relevance=0.95,
        importance=0.85,
    )
    report = await sim.run(
        [
            ScriptTurn(
                at_ms=0,
                speaker_id="SPK_1",
                text="I think the PlayStation came out in 1992.",
                topic_ids=["retro"],
                candidate=thought,
            ),
            ScriptTurn(at_ms=200, speaker_id="SPK_2", text="You want another beer?", topic_ids=["retro"]),
            ScriptTurn(at_ms=450, speaker_id="SPK_1", text="Yeah.", topic_ids=["retro"]),
            ScriptTurn(at_ms=700, speaker_id="SPK_3", text="What game should we put on?", topic_ids=["retro"]),
            ScriptTurn(at_ms=1900, complete_speech=True),
        ]
    )
    assert any(o.value == "suppress" or o.value == "hold" for o in report.outcomes)
    assert report.spoke
    assert "1994" in report.spoken_texts[0]
    speak_while_human = [
        t
        for t in engine.traces
        if t.outcome.value == "speak" and "human_speaking" in t.hard_inhibitors
    ]
    assert speak_while_human == []


@pytest.mark.asyncio
async def test_thought_becomes_stale_on_topic_change() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    sim = ConversationSimulator(engine, clock)
    thought = make_candidate(
        "The Japanese launch was 1994.",
        clock=clock,
        topic_id="playstation",
        relevance=0.95,
        importance=0.9,
    )
    report = await sim.run(
        [
            ScriptTurn(
                at_ms=0,
                speaker_id="A",
                text="PlayStation games tonight",
                topic_ids=["playstation"],
                candidate=thought,
            ),
            ScriptTurn(
                at_ms=300,
                speaker_id="B",
                text="We need generator fuel before the storm.",
                topic_ids=["fuel"],
            ),
            ScriptTurn(at_ms=2000),
        ]
    )
    assert not report.spoke
    assert report.discarded("topic_change")
    assert engine.chamber.current is None


@pytest.mark.asyncio
async def test_talk_over_hosaka_cancels_tts() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    sim = ConversationSimulator(engine, clock)
    thought = make_candidate(
        "One thing from earlier — the Japanese launch was actually 1994.",
        clock=clock,
        topic_id="retro",
        relevance=0.95,
        importance=0.85,
    )
    report = await sim.run(
        [
            ScriptTurn(
                at_ms=0,
                speaker_id="SPK_1",
                text="I think the PlayStation came out in 1992.",
                topic_ids=["retro"],
                candidate=thought,
            ),
            ScriptTurn(at_ms=1000, vad="start", speaker_id="SPK_2"),
            ScriptTurn(at_ms=1400),
        ]
    )
    assert report.interrupt_count >= 1
    assert engine.speech_sink.cancel_count >= 1  # type: ignore[attr-defined]
    assert not engine.state.agent_is_speaking
    assert engine.chamber.current is not None
    assert engine.chamber.current.kind is CandidateKind.INTERRUPTED_THOUGHT
