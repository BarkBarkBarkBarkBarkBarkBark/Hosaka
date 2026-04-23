"""Headless voice daemon: wake word -> OpenAI Realtime -> speakers.

Boots the mic + wake-word listener, and on every detected wake event
opens a short Realtime session that streams the subsequent speech to
OpenAI and plays the response back through the configured speaker.

Run with::

    python -m hosaka voice

The daemon is a long-lived loop; ctrl-c (or SIGTERM from systemd) shuts
it down cleanly. Failures to open the mic / camera / API are logged but
retried with exponential backoff so a USB unplug doesn't kill the unit.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Any

from hosaka.voice import tools as voice_tools
from hosaka.voice.realtime_client import RealtimeSession, RealtimeError

log = logging.getLogger("hosaka.voice.daemon")

TURN_TIMEOUT_S = float(os.getenv("HOSAKA_VOICE_TURN_TIMEOUT", "45"))
RETRY_BASE_S = 2.0
RETRY_MAX_S = 30.0


async def _handle_tool(name: str, args: dict[str, Any]) -> str:
    # Dispatch happens in a thread so camera capture / picoclaw
    # subprocess calls don't block the event loop that's also pushing
    # audio frames to the speaker.
    return await asyncio.to_thread(voice_tools.dispatch, name, args)


async def _run_turn(session: RealtimeSession, wake, speaker) -> None:
    """Stream a single wake-triggered turn end-to-end."""
    # The Realtime server does its own VAD and fires audio back as the
    # model speaks. The wake listener keeps pumping frames for up to
    # TURN_TIMEOUT_S; in practice speech_stopped + response.done fires
    # well before that.

    async def _on_audio(pcm: bytes) -> None:
        await asyncio.to_thread(speaker.play, pcm)

    async def _on_user(text: str) -> None:
        print(f"\n[you] {text}")

    async def _on_assistant(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    async def _on_state(state: str) -> None:
        log.debug("state: %s", state)

    session.on_audio = _on_audio
    session.on_user_transcript = _on_user
    session.on_assistant_transcript = _on_assistant
    session.on_state = _on_state
    session.on_tool = _handle_tool

    reader = asyncio.create_task(session.run_until_closed())
    try:
        async for frame in wake.stream_pcm24k(max_seconds=TURN_TIMEOUT_S):
            if reader.done():
                break
            await session.send_pcm16(frame)
    finally:
        reader.cancel()
        try:
            await reader
        except (asyncio.CancelledError, Exception):
            pass
    print()  # newline after the streamed assistant transcript


async def _main_loop(api_key: str) -> None:
    from hosaka.voice.wake import Speaker, WakeListener

    backoff = RETRY_BASE_S
    async with WakeListener() as wake:
        with Speaker() as speaker:
            log.info(
                "voice daemon ready — say '%s' to wake",
                os.getenv("HOSAKA_VOICE_WAKEWORD", "hey_jarvis"),
            )
            while True:
                try:
                    fired = await wake.wait_for_wake()
                    log.info("waking on %r", fired)
                    async with RealtimeSession(
                        api_key,
                        tools=voice_tools.TOOL_SCHEMAS,
                        instructions=voice_tools.SYSTEM_INSTRUCTIONS,
                    ) as session:
                        await _run_turn(session, wake, speaker)
                    backoff = RETRY_BASE_S  # success — reset backoff
                except asyncio.CancelledError:
                    raise
                except RealtimeError as exc:
                    log.warning("realtime error: %s (retry in %.0fs)", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(RETRY_MAX_S, backoff * 2)
                except Exception as exc:  # noqa: BLE001
                    log.exception("voice loop crashed: %s", exc)
                    await asyncio.sleep(backoff)
                    backoff = min(RETRY_MAX_S, backoff * 2)


def main() -> int:
    """Entry point for ``python -m hosaka voice``."""
    logging.basicConfig(
        level=os.getenv("HOSAKA_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(
            "hosaka voice: OPENAI_API_KEY is not set. Add it to "
            "/etc/hosaka/env or ~/.picoclaw/config.json first.",
            file=sys.stderr,
        )
        return 2

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _stop())

    async def _runner() -> None:
        task = asyncio.create_task(_main_loop(api_key))
        stopper = asyncio.create_task(stop.wait())
        done, pending = await asyncio.wait(
            {task, stopper}, return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()
        for d in done:
            if d is task and d.exception():
                raise d.exception()  # type: ignore[misc]

    try:
        loop.run_until_complete(_runner())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
