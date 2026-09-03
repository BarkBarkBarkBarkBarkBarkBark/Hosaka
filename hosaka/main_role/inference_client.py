"""Raspberry Pi client for the Jetson WAV inference endpoint."""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from hosaka.protocol.audio import MEDIA_TYPE, validate_wav

DEFAULT_JETSON_URL = "http://hosaka-jetson.local:8421"


class JetsonInferenceClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        fallback_url: str | None = None,
        token: str | None = None,
        timeout: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("HOSAKA_JETSON_URL") or DEFAULT_JETSON_URL).rstrip("/")
        self.fallback_url = (fallback_url or os.getenv("HOSAKA_JETSON_FALLBACK_URL") or "").rstrip("/")
        self.token = token or os.getenv("HOSAKA_INFERENCE_TOKEN", "")
        self.timeout = timeout
        self.transport = transport

    async def respond(self, wav_data: bytes, *, session_id: str = "hosaka-pi") -> bytes | None:
        validate_wav(wav_data)
        headers = {"Content-Type": MEDIA_TYPE, "X-Session-ID": session_id}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        urls = [self.base_url]
        if self.fallback_url and self.fallback_url not in urls:
            urls.append(self.fallback_url)
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for url in urls:
                try:
                    response = await client.post(f"{url}/respond", content=wav_data, headers=headers)
                    if response.status_code == 204:
                        return None
                    response.raise_for_status()
                    validate_wav(response.content)
                    return response.content
                except httpx.TransportError as exc:
                    last_error = exc
        raise RuntimeError(f"could not reach Jetson inference server: {last_error}")


def record_wav(seconds: int) -> bytes:
    if not shutil.which("arecord"):
        raise RuntimeError("arecord is required; install the alsa-utils package")
    command = ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(seconds), "-t", "wav"]
    result = subprocess.run(command, check=True, capture_output=True)
    validate_wav(result.stdout)
    return result.stdout


async def play_wav(wav_data: bytes) -> None:
    if not shutil.which("aplay"):
        raise RuntimeError("aplay is required; install the alsa-utils package")
    with tempfile.NamedTemporaryFile(suffix=".wav") as output:
        output.write(wav_data)
        output.flush()
        player = await asyncio.create_subprocess_exec("aplay", "-q", output.name)
        try:
            await player.wait()
        finally:
            if player.returncode is None:
                player.terminate()
                await player.wait()


async def _run(args: argparse.Namespace) -> int:
    wav_data = record_wav(args.record) if args.record else Path(args.wav).read_bytes()
    client = JetsonInferenceClient(args.url, fallback_url=args.fallback_url, token=args.token)
    response = await client.respond(wav_data, session_id=args.session_id)
    if response is None:
        print("Jetson chose to remain silent.")
        return 0
    if args.output:
        Path(args.output).write_bytes(response)
        print(f"Saved response to {args.output}")
    if not args.no_play:
        await play_wav(response)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hosaka inference", description="Send 16 kHz mono WAV audio to the Jetson")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("wav", nargs="?", help="prerecorded 16 kHz mono PCM WAV")
    source.add_argument("--record", type=int, metavar="SECONDS", help="record from the Pi microphone")
    parser.add_argument("--url", help=f"Jetson URL (default: {DEFAULT_JETSON_URL})")
    parser.add_argument("--fallback-url", help="IP URL used if mDNS is unavailable")
    parser.add_argument("--token", help="bearer token (prefer HOSAKA_INFERENCE_TOKEN)")
    parser.add_argument("--session-id", default="hosaka-pi")
    parser.add_argument("--output", help="also save the returned WAV")
    parser.add_argument("--no-play", action="store_true", help="do not play the returned WAV")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Cancelled; local playback stopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())