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
import json
import logging
import os
import signal
import sys
from typing import Any

from hosaka.llm.openai_adapter import resolve_api_key
from hosaka.voice import tools as voice_tools
from hosaka.voice.realtime_client import RealtimeSession, RealtimeError

log = logging.getLogger("hosaka.voice.daemon")

TURN_TIMEOUT_S = float(os.getenv("HOSAKA_VOICE_TURN_TIMEOUT", "180"))
RETRY_BASE_S = 2.0
RETRY_MAX_S = 30.0
_FRAME_MS = 80
_DUCK_MS = 120
_CANCEL_MS = 250
_game_holds_puck = False


async def _handle_tool(name: str, args: dict[str, Any]) -> str:
    from hosaka.voice.trace import TRACE

    TRACE.emit("tool", f"{name} {json.dumps(args, ensure_ascii=False, default=str)[:80]}")
    result = await asyncio.to_thread(voice_tools.dispatch, name, args)
    TRACE.emit("tool", f"{name} → {result[:80]}")
    return result


async def _run_turn(session: RealtimeSession, wake, speaker) -> None:
    """Stream a single wake-triggered turn end-to-end."""
    # The Realtime server does its own VAD and fires audio back as the
    # model speaks. The wake listener keeps pumping frames for up to
    # TURN_TIMEOUT_S; in practice speech_stopped + response.done fires
    # well before that.

    async def _on_audio(pcm: bytes) -> None:
        speaker.play(pcm)

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
            if speaker.recently_played():
                frame = b"\x00" * len(frame)
            await session.send_pcm16(frame)
    finally:
        reader.cancel()
        try:
            await reader
        except (asyncio.CancelledError, Exception):
            pass
    print()  # newline after the streamed assistant transcript


async def _spin_until(face: Any, stop: asyncio.Event) -> None:
    while not stop.is_set():
        face.pulse()
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.05)
        except asyncio.TimeoutError:
            continue


async def _run_social_turn(session: RealtimeSession, wake, speaker, *, face: Any | None = None) -> None:
    """Same mic/TTS path as ``_run_turn``, with SocialEngine on the floor."""
    from hosaka.voice.social_bridge import VoiceSocialBridge, chatty_enabled
    from hosaka.voice.trace import TRACE
    from hosaka.voice.wake import AdaptiveFloor, pcm_rms16

    bridge = VoiceSocialBridge(session, speaker, face=face)
    bridge.attach()
    session.on_tool = _handle_tool
    wakeword = "passthrough"
    if getattr(wake, "wake_enabled", False):
        wakeword = getattr(wake, "_wakeword", "passthrough")
    bridge.face.set_waiting(wakeword)
    await bridge.start_ticks()

    def _on_trace(etype: str, detail: str) -> None:
        TRACE.emit("rt", detail)
        bridge.face.note_rt(detail)
        if etype == "response.function_call_arguments.done":
            bridge.face.note_tool(detail)

    session.on_trace = _on_trace
    reader = asyncio.create_task(session.run_until_closed())
    heard = False
    quiet_ms = 0
    barge_ms = 0
    ducked = False
    floor = AdaptiveFloor()
    try:
        if chatty_enabled():
            await session.speak_verbatim(
                "Hey — I can hear you. Say something and I'll talk back."
            )
        async for frame in wake.stream_pcm24k(max_seconds=TURN_TIMEOUT_S):
            if reader.done():
                break
            raw = frame
            rms = pcm_rms16(raw)
            speaking = bridge.sink.is_speaking() or speaker.recently_played()
            if not speaking:
                floor.observe(rms)
            noise = floor.floor
            speech = floor.is_speech(rms)
            if _game_holds_puck:
                frame = b"\x00" * len(frame)
                barge_ms = 0
            elif speaking and floor.is_barge_in(rms):
                barge_ms += _FRAME_MS
                if barge_ms >= _CANCEL_MS:
                    speaker.abort()
                    ducked = False
                    barge_ms = 0
                    bridge.sink._speaking = False
                    bridge._response_pending = False
                    bridge.face.clear_busy()
                    try:
                        await session.cancel_response()
                    except Exception:  # noqa: BLE001
                        pass
                    TRACE.emit("interrupt", f"rms={rms:.0f}")
                elif barge_ms >= _DUCK_MS:
                    if not ducked:
                        speaker.duck(0.15)
                        ducked = True
                        TRACE.emit("duck", f"rms={rms:.0f}")
                else:
                    frame = b"\x00" * len(frame)
            elif speaking:
                barge_ms = 0
                if ducked:
                    speaker.unduck()
                    ducked = False
                frame = b"\x00" * len(frame)
            else:
                barge_ms = 0
                if ducked:
                    speaker.unduck()
                    ducked = False
            bridge.face.note_level(rms, floor=noise)
            TRACE.update(
                rms=rms,
                energy=bridge.face._energy,
                levels=list(bridge.face._levels),
                state=bridge.face._state,
                busy=bridge.face._busy,
                speaking=speaking,
                game=_game_holds_puck,
                hint=bridge.face._chamber,
                you=bridge.face._user,
            )
            if speech and not speaking and not _game_holds_puck:
                if not heard:
                    TRACE.emit("hear", f"rms={rms:.0f}")
                heard = True
                quiet_ms = 0
            elif heard:
                quiet_ms += _FRAME_MS
                if quiet_ms >= 400:
                    heard = False
                    quiet_ms = 0
                    TRACE.emit("end", "local silence")
            await session.send_pcm16(frame)
    finally:
        await bridge.stop_ticks()
        reader.cancel()
        try:
            await reader
        except (asyncio.CancelledError, Exception):
            pass
    print()


async def _main_loop(api_key: str) -> None:
    from hosaka.voice.wake import Speaker, WakeListener

    backoff = RETRY_BASE_S
    async with WakeListener() as wake:
        with Speaker() as speaker:
            try:
                speaker.play_tone(hz=660.0, seconds=0.16, amp=0.4)
            except Exception:  # noqa: BLE001
                log.debug("ready tone failed", exc_info=True)
            loop = asyncio.get_running_loop()

            def _puck(action: str) -> None:
                global _game_holds_puck
                if action == "pause":
                    _game_holds_puck = True
                    speaker.pause()
                else:
                    _game_holds_puck = False
                    speaker.resume()

            voice_tools.set_game_puck_hook(_puck)
            try:
                loop.add_signal_handler(signal.SIGUSR1, lambda: _puck("pause"))
                loop.add_signal_handler(signal.SIGUSR2, lambda: _puck("resume"))
            except NotImplementedError:
                pass
            log.info(
                "voice daemon ready — %s",
                (
                    f"say '{wake._wakeword}' to wake"
                    if wake.wake_enabled
                    else "listening (no wake-word model)"
                ),
            )
            from hosaka.voice.social_bridge import TuiOrbFace, chatty_enabled, social_enabled

            face = TuiOrbFace(stream=sys.__stdout__, live_log=True)
            chatty = chatty_enabled()
            while True:
                try:
                    await wake.wait_for_wake()
                    use_social = social_enabled()
                    auto = chatty or not use_social
                    instructions = voice_tools.SYSTEM_INSTRUCTIONS
                    if chatty:
                        instructions += (
                            "\n\nChatty mode is ON. Always reply out loud after the "
                            "operator speaks, in 1-3 sentences. Confirm what you heard. "
                            "Do not stay silent."
                        )
                    else:
                        instructions += (
                            "\n\nStay quiet unless the operator addresses you, asks a "
                            "question, or asks you to do something. Ignore ambient talk "
                            "and ignore your own voice on the speaker. "
                            "If they ask to play or launch a game (Tony Hawk, THPS, "
                            "Crash, Spyro, etc.), call play_game immediately with the "
                            "spoken name. Do not claim you cannot launch games."
                        )
                    face.note_working("connecting")
                    stop_spin = asyncio.Event()
                    spinner = asyncio.create_task(_spin_until(face, stop_spin))
                    try:
                        async with RealtimeSession(
                            api_key,
                            tools=voice_tools.TOOL_SCHEMAS,
                            instructions=instructions,
                            auto_create_response=auto,
                        ) as session:
                            stop_spin.set()
                            spinner.cancel()
                            if use_social:
                                await _run_social_turn(
                                    session, wake, speaker, face=face
                                )
                            else:
                                await _run_turn(session, wake, speaker)
                    finally:
                        stop_spin.set()
                        spinner.cancel()
                    backoff = RETRY_BASE_S  # success — reset backoff
                except ImportError:
                    raise
                except asyncio.CancelledError:
                    raise
                except RealtimeError as exc:
                    log.debug("realtime error: %s", exc)
                    await asyncio.sleep(backoff)
                    backoff = min(RETRY_MAX_S, backoff * 2)
                except Exception as exc:  # noqa: BLE001
                    log.debug("voice loop crashed: %s", exc, exc_info=True)
                    await asyncio.sleep(backoff)
                    backoff = min(RETRY_MAX_S, backoff * 2)


def _configure_voice_logging() -> None:
    """TUI already called basicConfig with timestamps — replace it."""
    tty = sys.stdout.isatty()
    level = os.getenv("HOSAKA_LOG_LEVEL", "ERROR" if tty else "INFO").upper()
    fmt = "%(message)s" if tty else "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        force=True,
        handlers=[logging.StreamHandler(sys.__stderr__)],
    )
    for name in ("httpx", "httpcore", "urllib3", "openai", "websockets"):
        logging.getLogger(name).setLevel(logging.ERROR)


async def _watch_quit(stop: asyncio.Event) -> None:
    """Escape / q / Ctrl-C / Ctrl-Z leave voice even when the HUD owns the TTY."""
    if not sys.__stdin__.isatty():
        return
    try:
        import select
        import termios
        import tty
    except ImportError:
        return
    fd = sys.__stdin__.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        return
    loop = asyncio.get_running_loop()

    def _poll() -> bytes:
        try:
            ready, _, _ = select.select([fd], [], [], 0.2)
        except (OSError, ValueError):
            return b""
        if not ready:
            return b""
        try:
            return os.read(fd, 8)
        except OSError:
            return b""

    try:
        tty.setcbreak(fd)
        while not stop.is_set():
            chunk = await loop.run_in_executor(None, _poll)
            if not chunk:
                continue
            if chunk[:1] in {b"\x1b", b"q", b"Q", b"\x03", b"\x04", b"\x1a"}:
                stop.set()
                return
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except termios.error:
            pass


def main() -> int:
    """Entry point for ``python -m hosaka voice``."""
    from hosaka.tui.style import install_terminal_guard, restore_terminal

    install_terminal_guard()
    _configure_voice_logging()
    api_key, _key_source = resolve_api_key()
    if not api_key:
        print(
            "hosaka voice: OPENAI_API_KEY is not set. Add it to "
            "/etc/hosaka/env, llm.json, or ~/.picoclaw/config.json first.",
            file=sys.stderr,
        )
        return 2

    from hosaka.voice.trace import TRACE, STATUS_PATH, lan_urls

    TRACE.serve()
    from hosaka.voice.social_bridge import voice_debug_enabled

    if voice_debug_enabled():
        print("voice debug panel:", file=sys.stderr)
        for url in lan_urls():
            print(f"  {url}", file=sys.stderr)
        print(f"  ssh:  watch -n 0.2 cat {STATUS_PATH}", file=sys.stderr)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, OSError, ValueError):
            try:
                signal.signal(sig, lambda *_: _stop())
            except (OSError, ValueError):
                pass

    async def _runner() -> None:
        task = asyncio.create_task(_main_loop(api_key))
        stopper = asyncio.create_task(stop.wait())
        keys = asyncio.create_task(_watch_quit(stop))
        done, pending = await asyncio.wait(
            {task, stopper}, return_when=asyncio.FIRST_COMPLETED
        )
        stop.set()
        keys.cancel()
        for p in pending:
            p.cancel()
        leftover = pending | {task, keys}
        if leftover:
            await asyncio.wait(leftover, timeout=2.5)
        for d in done:
            if d is task and d.exception():
                raise d.exception()  # type: ignore[misc]

    try:
        loop.run_until_complete(_runner())
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"hosaka voice: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    finally:
        restore_terminal()
        loop.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
