from __future__ import annotations

import asyncio
import io
import wave
from pathlib import Path

import httpx
import pytest

from hosaka.server_role.app import create_app
from hosaka.server_role.responder import OfflineResponder, ProviderError, normalize_wav, spoken_text


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * 1_600)
    return output.getvalue()


def _piper_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(22_050)
        target.writeframes(b"\x00\x00" * 2_205)
    return output.getvalue()


def _responder(tmp_path: Path) -> OfflineResponder:
    paths = [tmp_path / name for name in ("whisper", "whisper.bin", "vad.bin", "piper", "voice.onnx", "voice.json")]
    for path in paths:
        path.write_bytes(b"artifact")
    return OfflineResponder(*paths)


def test_offline_responder_runs_whisper_ollama_and_piper(tmp_path, monkeypatch) -> None:
    responder = _responder(tmp_path)
    output_wav = _piper_wav()
    commands: list[tuple[str, ...]] = []
    async_client = httpx.AsyncClient

    async def fake_run(*argv: str, stdin: bytes | None = None) -> None:
        commands.append(argv)
        if "-otxt" in argv:
            base = Path(argv[argv.index("-of") + 1])
            base.with_suffix(".txt").write_text("Hosaka, are you awake?", encoding="utf-8")
        else:
            assert stdin == b"Signal steady."
            Path(argv[argv.index("--output_file") + 1]).write_bytes(output_wav)

    def fake_ollama(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:11434/api/chat"
        return httpx.Response(200, json={"message": {"content": "Signal steady."}})

    monkeypatch.setattr(OfflineResponder, "_run", fake_run)
    monkeypatch.setattr(
        "hosaka.server_role.responder.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(fake_ollama)),
    )

    result = asyncio.run(responder(_wav(), "camp-1"))
    assert result is not None
    assert normalize_wav(output_wav) == result
    assert len(commands) == 2
    assert "--no-gpu" in commands[0]
    assert "--vad" in commands[0]


def test_offline_responder_reports_missing_artifacts(tmp_path) -> None:
    responder = OfflineResponder(
        tmp_path / "whisper",
        tmp_path / "model",
        tmp_path / "vad",
        tmp_path / "piper",
        tmp_path / "voice",
        tmp_path / "config",
    )
    with pytest.raises(ProviderError, match="missing offline artifact"):
        asyncio.run(responder(_wav(), "camp-1"))


def test_offline_responder_rejects_nonlocal_ollama(tmp_path) -> None:
    responder = _responder(tmp_path)
    responder.ollama_url = "https://api.openai.com"
    with pytest.raises(ProviderError, match="must use loopback"):
        asyncio.run(responder(_wav(), "camp-1"))


def test_spoken_text_removes_reasoning_and_limits_response() -> None:
    raw = "<think>Long private reasoning.</think> Signal steady. This must not be spoken."
    assert spoken_text(raw) == "Signal steady."


def test_provider_failure_returns_service_unavailable(monkeypatch) -> None:
    async def failed_responder(audio: bytes, session_id: str) -> bytes:
        raise ProviderError("Whisper unavailable")

    monkeypatch.setenv("HOSAKA_INFERENCE_TOKEN", "field-secret")
    transport = httpx.ASGITransport(app=create_app(failed_responder), client=("192.168.1.10", 1234))

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://jetson") as client:
            return await client.post(
                "/respond",
                content=_wav(),
                headers={"Content-Type": "audio/wav", "Authorization": "Bearer field-secret"},
            )

    response = asyncio.run(request())
    assert response.status_code == 503
    assert "Whisper unavailable" in response.text