"""Deterministic party simulation from cognition_play.yaml §39."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hosaka_social import (  # noqa: E402
    ConversationSimulator,
    FakeClock,
    ScriptTurn,
    SocialEngine,
    make_candidate,
)


async def main() -> None:
    clock = FakeClock()
    engine = SocialEngine(clock=clock, auto_reflect=False)
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
    state = engine.state
    chamber = engine.chamber.current
    last = engine.traces[-1] if engine.traces else None
    print("HOSAKA SOCIAL")
    print()
    print(f"speaker      {state.primary_speaker}")
    print(f"topic        {', '.join(state.current_topics) or '-'}")
    print()
    inward = engine.internal
    print(f"attention    {inward.attention_strength:.2f}")
    print(f"urge         {inward.urge_to_speak:.2f}")
    print(f"suppression  {inward.suppression:.2f}")
    print()
    print("decisions:")
    for trace in engine.traces:
        print(f"  {trace.outcome.value.upper():<10} score={trace.score:.2f}")
    print()
    print(f"decision     {last.outcome.value.upper() if last else 'NO_ACTION'}")
    print()
    print("chamber:")
    print(chamber.content if chamber else "(empty)")
    print()
    print("spoken:")
    for text in report.spoken_texts or ["(silence)"]:
        print(f"  {text}")
    print()
    print(f"turn share   {report.agent_turn_share:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
