from __future__ import annotations

import asyncio
from io import StringIO
from types import SimpleNamespace

import pytest

from hosaka.voice.social_bridge import (
    RealtimeTtsSink,
    TuiOrbFace,
    VoiceSocialBridge,
    chatty_enabled,
    render_social_status,
    social_enabled,
)
from hosaka_social import FakeClock, MockLLMProvider, make_candidate
from hosaka_social.events import TranscriptFinalized
from hosaka_social.models import CandidateKind


def test_render_social_status_is_one_line() -> None:
    line = render_social_status("chambered", "HOLD", "PlayStation 1994", score=0.8)
    assert "chambered" in line
    assert "HOLD" in line
    assert "PlayStation" in line
    assert "\n" not in line


def test_social_enabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOSAKA_SOCIAL_COGNITION", "0")
    assert social_enabled() is False
    monkeypatch.setenv("HOSAKA_SOCIAL_COGNITION", "1")
    assert social_enabled() is True


def test_chatty_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOSAKA_VOICE_CHATTY", raising=False)
    assert chatty_enabled() is False
    monkeypatch.setenv("HOSAKA_VOICE_CHATTY", "1")
    assert chatty_enabled() is True


def test_looks_directed_game_launch() -> None:
    from hosaka.voice.social_bridge import looks_directed

    assert looks_directed("launch tony hawk") is True
    assert looks_directed("can you play crash") is True
    assert looks_directed("lunch, fire") is True
    assert looks_directed("yeah") is False
    assert looks_directed("mm hmm") is False


def test_looks_directed_reading() -> None:
    from hosaka.voice.social_bridge import looks_directed

    assert looks_directed("what books do you have") is True
    assert looks_directed("open foliate") is True
    assert looks_directed("i want to read") is True
    assert looks_directed("read frankenstein") is True


def test_parse_read_command_list_and_open() -> None:
    from hosaka.voice.social_bridge import parse_play_command, parse_read_command

    assert parse_read_command("what books are available") == {"action": "list"}
    assert parse_read_command("list the books") == {"action": "list"}
    assert parse_read_command("launch foliate") == {"action": "open"}
    assert parse_read_command("lunch foliage") == {"action": "open"}
    assert parse_read_command("i want to read") == {"action": "open"}
    assert parse_read_command("read frankenstein") == {
        "action": "open",
        "name": "frankenstein",
    }
    assert parse_read_command("open walden") == {"action": "open", "name": "walden"}
    assert parse_play_command("launch foliate") is None
    assert parse_play_command("launch tony hawk") == "tony hawk"


def test_repair_lunch_fire_to_launch_spyro() -> None:
    from hosaka.voice.social_bridge import parse_play_command, repair_transcript

    assert repair_transcript("lunch, fire") == "launch spyro"
    assert parse_play_command("lunch, fire") == "spyro"


def test_live_log_streams_you_line() -> None:
    buf = StringIO()
    face = TuiOrbFace(stream=buf, live_log=True)
    face.note_user("hello there")
    out = buf.getvalue()
    assert "you" in out
    assert "hello there" in out


def test_tui_face_does_not_spam_hold() -> None:
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    face = TuiOrbFace(stream=buf)
    face.note_decision("hold", 0.8, "later")
    face.note_decision("hold", 0.8, "later")
    assert buf.getvalue() == ""
    face.note_decision("speak", 1.0, "1994")
    out = buf.getvalue()
    assert "SPEAK" in out
    assert "[hosaka]" in out


def test_waiting_passthrough_copy() -> None:
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    face = TuiOrbFace(stream=buf)
    face.set_waiting("passthrough")
    assert "listening" in buf.getvalue()


@pytest.mark.asyncio
async def test_wait_for_wake_passthrough_without_model() -> None:
    from hosaka.voice.wake import WakeListener

    wake = WakeListener()
    wake._oww = None
    wake._numpy = None
    assert await wake.wait_for_wake() == "passthrough"


def test_upsample_16k_to_24k_ratio() -> None:
    from hosaka.voice.wake import _upsample_16k_to_24k

    pcm = (1000).to_bytes(2, "little", signed=True) * 4
    out = _upsample_16k_to_24k(pcm)
    assert len(out) == 12


def test_resample_48k_to_24k_halves_length() -> None:
    from hosaka.voice.wake import _resample_pcm16

    pcm = (1000).to_bytes(2, "little", signed=True) * 8
    out = _resample_pcm16(pcm, 48_000, 24_000)
    assert len(out) == 8


def test_resample_24k_to_48k_doubles_length() -> None:
    from hosaka.voice.wake import _resample_pcm16

    pcm = (1000).to_bytes(2, "little", signed=True) * 4
    out = _resample_pcm16(pcm, 24_000, 48_000)
    assert len(out) == 16


def test_reclaim_stale_voice_does_not_kill_self() -> None:
    from hosaka.voice.wake import reclaim_stale_voice

    reclaim_stale_voice(timeout_s=0.2)


def test_pick_voice_devices_prefers_p10s_duplex() -> None:
    from hosaka.voice.wake import pick_voice_devices

    devices = [
        {"name": "bcm2835 Headphones", "max_input_channels": 0, "max_output_channels": 8},
        {"name": "USB PnP Sound Device", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "P10S: USB Audio (hw:3,0)", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "default", "max_input_channels": 0, "max_output_channels": 128},
    ]
    mic, spk = pick_voice_devices(devices)
    assert mic == 2
    assert spk == 2


def test_waiting_orb_uses_wakeword() -> None:
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    face = TuiOrbFace(stream=buf)
    face.set_waiting("hey_jarvis")
    out = buf.getvalue()
    assert "WAIT" in out
    assert "hey jarvis" in out
    assert "[you]" in out


def test_orb_spiral_has_eleven_lines() -> None:
    from hosaka.tui.style import render_orb_spiral

    a = render_orb_spiral(0.0)
    b = render_orb_spiral(1.7)
    assert len(a.splitlines()) == 11
    assert len(b.splitlines()) == 11
    assert a != b
    assert "◉" in a


@pytest.mark.asyncio
async def test_thinking_stays_busy_when_engine_sets_idle() -> None:
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    face = TuiOrbFace(stream=buf, live_log=True)
    face.note_working("launching crash")
    assert face._busy is True
    assert face._state == "thinking"
    await face.set_state("idle")
    assert face._state == "thinking"
    before = face._spin
    face.pulse()
    assert face._spin > before
    face.clear_busy()
    assert face._busy is False


def test_hud_falls_back_when_terminal_is_short(monkeypatch) -> None:
    monkeypatch.setattr(
        "hosaka.voice.social_bridge._term_size", lambda: (80, 10)
    )
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    face = TuiOrbFace(stream=buf, live_log=True)
    face.note_working("connecting")
    out = buf.getvalue()
    assert "connecting" in out


def test_waveform_travels_right() -> None:
    from hosaka.tui.style import render_waveform

    quiet = render_waveform([0.0] * 8, width=8)
    loud = render_waveform([0.0] * 7 + [1.0], width=8)
    assert "█" in loud or "▇" in loud
    assert loud != quiet


def test_voice_color_hall_has_tail() -> None:
    from hosaka.voice.wake import VoiceColor

    fx = VoiceColor(24_000, 1, "hall")
    impulse = (8000).to_bytes(2, "little", signed=True)
    fx.process(impulse)
    tail = fx.process(b"\x00\x00" * 800)
    peak = max(
        abs(int.from_bytes(tail[i : i + 2], "little", signed=True))
        for i in range(0, len(tail), 2)
    )
    assert peak > 0


def test_voice_color_robot_holds_samples() -> None:
    from hosaka.voice.wake import VoiceColor

    fx = VoiceColor(24_000, 1, "robot")
    pcm = b"".join((v).to_bytes(2, "little", signed=True) for v in (1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000))
    out = fx.process(pcm)
    samples = [int.from_bytes(out[i : i + 2], "little", signed=True) for i in range(0, len(out), 2)]
    assert len(samples) == 8
    assert samples[0] == samples[1] == samples[2] == samples[3]


def test_voice_fx_style_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from hosaka.voice.wake import _voice_fx_style

    monkeypatch.setenv("HOSAKA_VOICE_FX", "robot")
    assert _voice_fx_style() == "robot"
    monkeypatch.setenv("HOSAKA_VOICE_FX", "off")
    assert _voice_fx_style() == "off"
    monkeypatch.setenv("HOSAKA_VOICE_FX", "hall")
    assert _voice_fx_style() == "hall"
    monkeypatch.delenv("HOSAKA_VOICE_FX", raising=False)
    assert _voice_fx_style() == "off"


def test_pcm_rms16_silence_is_low() -> None:
    from hosaka.voice.wake import pcm_rms16

    assert pcm_rms16(b"\x00\x00" * 64) == 0.0
    loud = (8000).to_bytes(2, "little", signed=True) * 64
    assert pcm_rms16(loud) > 1000


@pytest.mark.asyncio
async def test_realtime_sink_cancel_uses_existing_session() -> None:
    session = SimpleNamespace(spoken=[], cancelled=0)

    async def speak_verbatim(text: str) -> None:
        session.spoken.append(text)

    async def cancel_response() -> None:
        session.cancelled += 1

    session.speak_verbatim = speak_verbatim
    session.cancel_response = cancel_response
    speaker = SimpleNamespace(aborted=0)

    def abort() -> None:
        speaker.aborted += 1

    speaker.abort = abort
    sink = RealtimeTtsSink(session, speaker)
    await sink.speak(SimpleNamespace(text="hello there"))
    await sink.cancel()
    await sink.cancel()
    assert session.spoken == ["hello there"]
    assert session.cancelled == 2
    assert speaker.aborted == 2


@pytest.mark.asyncio
async def test_bridge_maps_transcript_as_addressed() -> None:
    session = SimpleNamespace()
    speaker = SimpleNamespace(play=lambda pcm: None)
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    clock = FakeClock()
    bridge = VoiceSocialBridge(
        session,
        speaker,
        provider=MockLLMProvider(),
        clock=clock,
        face_stream=buf,
    )
    bridge.attach()
    await session.on_user_transcript("what game should we put on?")
    last = bridge.engine.state.recent_utterances[-1]
    assert last.speaker_id == "operator"
    assert last.addressed_agent_probability == 1.0
    await session.on_state("listening")
    assert bridge.engine.state.human_speaking is True


@pytest.mark.asyncio
async def test_bridge_authorized_speech_uses_realtime_tts() -> None:
    session = SimpleNamespace(spoken=[])

    async def speak_verbatim(text: str) -> None:
        session.spoken.append(text)

    session.speak_verbatim = speak_verbatim
    speaker = SimpleNamespace()
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    clock = FakeClock()
    bridge = VoiceSocialBridge(
        session,
        speaker,
        provider=MockLLMProvider(),
        clock=clock,
        face_stream=buf,
    )
    await bridge.engine.handle(
        TranscriptFinalized(
            speaker_id="operator",
            text="Hey Hosaka, launch Crash?",
            addressed_agent_probability=1.0,
        )
    )
    await bridge.engine.inject_candidate(
        make_candidate(
            "Crash Team Racing is a solid two-player pick.",
            clock=clock,
            kind=CandidateKind.DIRECT_RESPONSE,
            relevance=0.95,
            importance=0.9,
            confidence=0.9,
        )
    )
    clock.advance(0.7)
    await bridge.engine.tick()
    assert session.spoken
    assert "Crash" in session.spoken[0]


def test_ga_session_update_rejects_beta_shape() -> None:
    from hosaka.voice.realtime_client import ga_session_update

    evt = ga_session_update(
        model="gpt-realtime",
        voice="marin",
        instructions="be brief",
        tools=[{"type": "function", "name": "todo_add"}],
        auto_create_response=False,
    )
    session = evt["session"]
    assert evt["type"] == "session.update"
    assert session["type"] == "realtime"
    assert session["output_modalities"] == ["audio"]
    assert session["audio"]["input"]["format"]["type"] == "audio/pcm"
    assert session["audio"]["input"]["turn_detection"]["create_response"] is False
    assert session["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert session["audio"]["input"]["turn_detection"]["eagerness"] == "medium"
    assert session["audio"]["output"]["voice"] == "marin"
    assert "modalities" not in session
    assert "input_audio_format" not in session
    assert "voice" not in session


@pytest.mark.asyncio
async def test_handle_ga_output_audio_delta() -> None:
    import base64

    from hosaka.voice.realtime_client import RealtimeSession

    got: list[bytes] = []

    async def _on_audio(pcm: bytes) -> None:
        got.append(pcm)

    rt = RealtimeSession("sk-test")
    rt.on_audio = _on_audio
    pcm = b"\x01\x00"
    await rt._handle_event(
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(pcm).decode("ascii"),
        }
    )
    assert got == [pcm]


def test_play_argv_is_path_command_not_python(monkeypatch) -> None:
    from hosaka.voice import tools as voice_tools

    monkeypatch.delenv("HOSAKA_PLAY", raising=False)
    monkeypatch.setattr(
        voice_tools.shutil, "which", lambda name: "/home/operator/bin/play" if name == "play" else None
    )
    argv = voice_tools._play_argv("Crash Bandicoot")
    assert argv == ["/home/operator/bin/play", "--json", "Crash Bandicoot"]
    assert argv[0] != "python"


def test_tool_hint_is_human() -> None:
    from hosaka.voice.social_bridge import tool_hint, voice_debug_enabled

    assert "looking around" in tool_hint("see")
    assert "spyro" in tool_hint("play_game", "spyro")
    assert "frankenstein" in tool_hint("open_reader", "frankenstein")
    assert "shelf" in tool_hint("list_books")
    assert "working on it" in tool_hint("mystery_tool")
    assert voice_debug_enabled() is False


def test_adaptive_floor_ignores_quiet_noise() -> None:
    from hosaka.voice.wake import AdaptiveFloor

    floor = AdaptiveFloor(window=20, min_samples=8)
    for _ in range(12):
        floor.observe(100.0)
    assert floor.floor <= 120
    assert floor.is_speech(100.0) is False
    assert floor.is_speech(2000.0) is True
    assert floor.is_barge_in(400.0) is False
    assert floor.is_barge_in(2000.0) is True


def test_ensure_playback_volume_lifts_silence(monkeypatch) -> None:
    from types import SimpleNamespace

    from hosaka.voice import wake as wake_mod

    calls: list[list[str]] = []
    sget = {
        "PCM": "Mono: Playback 0 [0%] [0.00dB] [on]\n",
        "Speaker": "",
        "Headphone": "",
        "Master": "",
    }

    def fake_run(argv, **_kwargs):
        from types import SimpleNamespace

        calls.append(list(argv))
        if "sget" in argv:
            ctrl = argv[-1]
            return SimpleNamespace(returncode=0, stdout=sget.get(ctrl, ""), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(wake_mod.subprocess, "run", fake_run)
    sd = SimpleNamespace(query_devices=lambda _d: {"name": "P10S: USB Audio (hw:2,0)"})
    wake_mod.ensure_playback_volume(sd, 0)
    joined = [" ".join(c) for c in calls]
    assert any("sset PCM 70%" in line for line in joined)


def test_speaker_duck_scales_gain() -> None:
    from hosaka.voice.wake import Speaker

    spk = Speaker()
    assert spk._duck == 1.0
    spk.duck(0.15)
    assert spk._duck == 0.15
    spk.unduck()
    assert spk._duck == 1.0
    spk.duck(0.2)
    spk.abort()
    assert spk._duck == 1.0
    assert spk.recently_played() is False


def test_picoclaw_chat_sync_honors_timeout(monkeypatch) -> None:
    from types import SimpleNamespace

    from hosaka.llm import picoclaw_adapter

    captured: dict = {}

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stdout="🦞 hi", stderr="")

    monkeypatch.setattr(picoclaw_adapter.subprocess, "run", fake_run)
    assert picoclaw_adapter.chat_sync("hello", timeout=6) == "hi"
    assert captured["timeout"] == 6


def test_restore_terminal_writes_reset(monkeypatch) -> None:
    from io import StringIO

    from hosaka.tui.style import restore_terminal

    buf = StringIO()
    monkeypatch.setattr("hosaka.tui.style.sys", SimpleNamespace(__stdout__=buf, stdout=buf))
    restore_terminal()
    assert "\033[r" in buf.getvalue()
    assert "\033[?25h" in buf.getvalue()


def test_waveform_dims_floor() -> None:
    from hosaka.tui.style import render_waveform

    out = render_waveform([0.0] * 7 + [1.0], width=8, floor=0.2)
    assert "█" in out or "▇" in out


@pytest.mark.asyncio
async def test_directed_asks_before_engine_speech() -> None:
    order: list[str] = []
    session = SimpleNamespace(spoken=[])

    async def request_response() -> None:
        order.append("ask")

    async def speak_verbatim(text: str) -> None:
        order.append("verbatim")
        session.spoken.append(text)

    session.request_response = request_response
    session.speak_verbatim = speak_verbatim
    speaker = SimpleNamespace(play=lambda pcm: None)
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    clock = FakeClock()
    bridge = VoiceSocialBridge(
        session,
        speaker,
        provider=MockLLMProvider(),
        clock=clock,
        face_stream=buf,
    )
    bridge.attach()
    await session.on_user_transcript("what game should we put on?")
    assert order[0] == "ask"
    assert bridge._response_pending is True
    await bridge.engine.inject_candidate(
        make_candidate(
            "Crash Team Racing is a solid two-player pick.",
            clock=clock,
            kind=CandidateKind.DIRECT_RESPONSE,
            relevance=0.95,
            importance=0.9,
            confidence=0.9,
        )
    )
    clock.advance(0.7)
    await bridge.engine.tick()
    assert "verbatim" not in order


@pytest.mark.asyncio
async def test_partial_words_update_hud_and_can_ask() -> None:
    session = SimpleNamespace(asked=0)

    async def request_response() -> None:
        session.asked += 1

    session.request_response = request_response
    speaker = SimpleNamespace(play=lambda pcm: None)
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    bridge = VoiceSocialBridge(
        session,
        speaker,
        provider=MockLLMProvider(),
        clock=FakeClock(),
        face_stream=buf,
    )
    bridge.attach()
    await session.on_user_partial("yeah ")
    assert session.asked == 0
    await session.on_user_partial("hosaka what game")
    assert session.asked == 1
    assert "hosaka" in bridge.face._user.lower()


@pytest.mark.asyncio
async def test_handle_event_does_not_wait_for_user_hook() -> None:
    import time

    from hosaka.voice.realtime_client import RealtimeSession

    started = asyncio.Event()
    release = asyncio.Event()
    rt = RealtimeSession("sk-test")

    async def slow(_text: str) -> None:
        started.set()
        await release.wait()

    rt.on_user_transcript = slow
    t0 = time.monotonic()
    await rt._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "hi",
        }
    )
    assert time.monotonic() - t0 < 0.2
    await asyncio.sleep(0)
    assert started.is_set()
    release.set()
    if rt._bg:
        await asyncio.gather(*rt._bg)


@pytest.mark.asyncio
async def test_handle_transcription_delta() -> None:
    from hosaka.voice.realtime_client import RealtimeSession

    partials: list[str] = []
    finals: list[str] = []
    rt = RealtimeSession("sk-test")

    async def on_p(text: str) -> None:
        partials.append(text)

    async def on_u(text: str) -> None:
        finals.append(text)

    rt.on_user_partial = on_p
    rt.on_user_transcript = on_u
    await rt._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "delta": "hey",
        }
    )
    await rt._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "hey there",
        }
    )
    await asyncio.sleep(0)
    if rt._bg:
        await asyncio.gather(*rt._bg)
    assert partials == ["hey"]
    assert finals == ["hey there"]


@pytest.mark.asyncio
async def test_note_hearing_sets_listening_copy() -> None:
    buf = StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    face = TuiOrbFace(stream=buf, live_log=False)
    face.note_hearing()
    assert face._state == "listening"
    assert "hearing you" in face._chamber
