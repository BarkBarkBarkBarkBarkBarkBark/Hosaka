from __future__ import annotations

import asyncio
import io
import wave
from contextlib import suppress

import httpx

from hosaka.main_role.inference_client import JetsonInferenceClient, play_wav
from hosaka.server_role.app import create_app


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * 1_600)
    return output.getvalue()


def test_pi_client_round_trips_wav_through_fake_jetson(monkeypatch) -> None:
    received: list[tuple[bytes, str]] = []

    async def fake_responder(audio: bytes, session_id: str) -> bytes:
        received.append((audio, session_id))
        return audio

    monkeypatch.setenv("HOSAKA_INFERENCE_TOKEN", "field-secret")
    transport = httpx.ASGITransport(app=create_app(fake_responder), client=("192.168.1.10", 1234))
    client = JetsonInferenceClient("http://fake-jetson:8421", token="field-secret", transport=transport)
    source = _wav()

    result = asyncio.run(client.respond(source, session_id="camp-1"))

    assert result == source
    assert received == [(source, "camp-1")]


def test_fake_jetson_rejects_wrong_wav_format(monkeypatch) -> None:
    monkeypatch.setenv("HOSAKA_INFERENCE_TOKEN", "field-secret")
    transport = httpx.ASGITransport(app=create_app(lambda audio, session: audio), client=("192.168.1.10", 1234))

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://fake-jetson") as client:
            return await client.post(
                "/respond",
                content=b"not a wav",
                headers={"Content-Type": "audio/wav", "Authorization": "Bearer field-secret"},
            )

    response = asyncio.run(request())
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_audio"
    assert response.headers["X-Hosaka-Request-ID"]


def test_pi_client_uses_configured_ip_fallback() -> None:
    source = _wav()
    requested_hosts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "hosaka-jetson.local":
            raise httpx.ConnectError("mDNS unavailable", request=request)
        return httpx.Response(200, content=source, headers={"Content-Type": "audio/wav"})

    client = JetsonInferenceClient(
        fallback_url="http://192.168.50.20:8421",
        transport=httpx.MockTransport(respond),
    )
    assert asyncio.run(client.respond(source)) == source
    assert requested_hosts == ["hosaka-jetson.local", "192.168.50.20"]


def test_cancelling_playback_terminates_local_player(monkeypatch) -> None:
    class FakePlayer:
        returncode: int | None = None

        def __init__(self) -> None:
            self.finished = asyncio.Event()
            self.terminated = False

        async def wait(self) -> int:
            await self.finished.wait()
            return self.returncode or 0

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15
            self.finished.set()

    player = FakePlayer()

    async def create_player(*args) -> FakePlayer:
        return player

    monkeypatch.setattr("hosaka.main_role.inference_client.shutil.which", lambda name: "/usr/bin/aplay")
    monkeypatch.setattr("hosaka.main_role.inference_client.asyncio.create_subprocess_exec", create_player)

    async def cancel_playback() -> None:
        task = asyncio.create_task(play_wav(_wav()))
        await asyncio.sleep(0)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(cancel_playback())
    assert player.terminated is True