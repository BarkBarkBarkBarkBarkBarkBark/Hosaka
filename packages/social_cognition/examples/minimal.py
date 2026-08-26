"""Minimal in-process usage."""

from __future__ import annotations

import asyncio

from hosaka_social import FakeClock, SocialEngine, TranscriptFinalized


async def main() -> None:
    clock = FakeClock()
    engine = SocialEngine(clock=clock, auto_reflect=False)
    await engine.handle(
        TranscriptFinalized(speaker_id="SPK_1", text="anyway the snacks are in the kitchen")
    )
    clock.advance(1.5)
    await engine.tick()
    print("spoke:", engine.spoken_texts() or "(silence)")
    print("chamber:", engine.chamber.current)


if __name__ == "__main__":
    asyncio.run(main())
