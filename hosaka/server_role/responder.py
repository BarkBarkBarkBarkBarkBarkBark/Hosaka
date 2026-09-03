"""Offline Whisper, Ollama, and Piper responder for the Jetson role."""
from __future__ import annotations

import asyncio
import audioop
import io
import json
import logging
import os
import re
import tempfile
import time
import wave
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from hosaka.protocol.audio import validate_wav
from hosaka.voice.social_bridge import looks_directed

log = logging.getLogger("uvicorn.error")
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_SENTENCE_RE = re.compile(r"^(.{1,280}?[.!?])(?:\s|$)", re.DOTALL)


class ProviderError(RuntimeError):
    """An offline inference provider is unavailable or failed."""


def normalize_wav(wav_data: bytes) -> bytes:
    """Convert mono PCM16 Piper output to the shared 16 kHz WAV contract."""
    try:
        with wave.open(io.BytesIO(wav_data), "rb") as source:
            channels = source.getnchannels()
            width = source.getsampwidth()
            rate = source.getframerate()
            compression = source.getcomptype()
            pcm = source.readframes(source.getnframes())
    except (EOFError, wave.Error) as exc:
        raise ProviderError(f"Piper returned malformed WAV: {exc}") from exc
    if channels != 1 or width != 2 or compression != "NONE":
        raise ProviderError("Piper must return mono PCM16 WAV")
    if rate != 16_000:
        pcm, _ = audioop.ratecv(pcm, width, channels, rate, 16_000, None)
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(pcm)
    return output.getvalue()


def spoken_text(text: str) -> str:
    """Remove reasoning markup and cap synthesis at one short sentence."""
    cleaned = " ".join(_THINK_RE.sub("", text).split())
    match = _SENTENCE_RE.match(cleaned)
    if match:
        return match.group(1).strip()
    return cleaned[:280].strip()


@dataclass
class OfflineResponder:
    whisper_bin: Path
    whisper_model: Path
    vad_model: Path
    piper_bin: Path
    piper_model: Path
    piper_config: Path
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    timeout_seconds: float = 180.0
    whisper_gpu: bool = False
    _history: dict[str, deque[dict[str, str]]] = field(default_factory=dict, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @classmethod
    def from_env(cls) -> "OfflineResponder":
        return cls(
            whisper_bin=Path(os.getenv("HOSAKA_WHISPER_BIN", "/opt/hosaka/bin/whisper-cli")),
            whisper_model=Path(os.getenv("HOSAKA_WHISPER_MODEL", "/opt/hosaka/models/whisper/ggml-tiny.en.bin")),
            vad_model=Path(os.getenv("HOSAKA_WHISPER_VAD_MODEL", "/opt/hosaka/models/whisper/ggml-silero-v6.2.0.bin")),
            piper_bin=Path(os.getenv("HOSAKA_PIPER_BIN", "/opt/hosaka/bin/piper")),
            piper_model=Path(os.getenv("HOSAKA_PIPER_MODEL", "/opt/hosaka/models/piper/en_US-lessac-medium.onnx")),
            piper_config=Path(os.getenv("HOSAKA_PIPER_CONFIG", "/opt/hosaka/models/piper/en_US-lessac-medium.onnx.json")),
            ollama_url=os.getenv("HOSAKA_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("HOSAKA_OLLAMA_MODEL", "qwen3:4b"),
            timeout_seconds=float(os.getenv("HOSAKA_INFERENCE_TIMEOUT", "180")),
            whisper_gpu=os.getenv("HOSAKA_WHISPER_GPU", "0").strip().lower() in {"1", "true", "yes", "on"},
        )

    def missing_artifacts(self) -> list[str]:
        required = (
            self.whisper_bin,
            self.whisper_model,
            self.vad_model,
            self.piper_bin,
            self.piper_model,
            self.piper_config,
        )
        return [str(path) for path in required if not path.is_file()]

    async def __call__(self, wav: bytes, session_id: str) -> bytes | None:
        validate_wav(wav)
        missing = self.missing_artifacts()
        if missing:
            raise ProviderError(f"missing offline artifact(s): {', '.join(missing)}")
        host = (urlparse(self.ollama_url).hostname or "").lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ProviderError("HOSAKA_OLLAMA_BASE_URL must use loopback in server role")

        async with self._lock:
            return await self._respond(wav, session_id)

    async def _respond(self, wav: bytes, session_id: str) -> bytes | None:
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="hosaka-inference-") as raw_dir:
            work = Path(raw_dir)
            input_path = work / "input.wav"
            transcript_base = work / "transcript"
            output_path = work / "response.wav"
            input_path.write_bytes(wav)

            whisper_args = [
                str(self.whisper_bin),
                "-m", str(self.whisper_model),
                "-f", str(input_path),
                "-otxt",
                "-of", str(transcript_base),
                "--no-timestamps",
                "--prompt", "Hosaka is the name of the assistant.",
                "--vad",
                "--vad-model", str(self.vad_model),
            ]
            if not self.whisper_gpu:
                whisper_args.insert(1, "--no-gpu")
            await self._run(*whisper_args)
            stt_finished = time.monotonic()
            transcript_path = transcript_base.with_suffix(".txt")
            try:
                transcript = transcript_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ProviderError(f"Whisper did not produce a transcript: {exc}") from exc
            if not transcript:
                log.info("session=%s decision=remain_silent stt_ms=%.1f reason=no_speech", session_id, (stt_finished - started) * 1000)
                return None

            if not looks_directed(transcript):
                log.info("session=%s decision=remain_silent stt_ms=%.1f reason=not_directed", session_id, (stt_finished - started) * 1000)
                return None

            text = await self._generate(transcript, session_id)
            llm_finished = time.monotonic()
            text = spoken_text(text)
            if not text:
                raise ProviderError("Ollama returned an empty response")
            await self._run(
                str(self.piper_bin),
                "--model", str(self.piper_model),
                "--config", str(self.piper_config),
                "--output_file", str(output_path),
                stdin=text.encode("utf-8"),
            )
            try:
                result = output_path.read_bytes()
            except OSError as exc:
                raise ProviderError(f"Piper did not produce audio: {exc}") from exc
            result = normalize_wav(result)
            validate_wav(result)
            finished = time.monotonic()
            log.info(
                "session=%s decision=speak stt_ms=%.1f llm_ms=%.1f tts_ms=%.1f total_ms=%.1f",
                session_id,
                (stt_finished - started) * 1000,
                (llm_finished - stt_finished) * 1000,
                (finished - llm_finished) * 1000,
                (finished - started) * 1000,
            )
            return result

    async def _generate(self, transcript: str, session_id: str) -> str:
        history = self._history.setdefault(session_id, deque(maxlen=20))
        history.append({"role": "user", "content": transcript})
        payload = {
            "model": self.ollama_model,
            "messages": [
                {
                    "role": "system",
                    "content": "/no_think You are Hosaka. Output only one concise spoken sentence with no reasoning or markup.",
                },
                *history,
            ],
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {"num_ctx": 1024, "num_predict": 96},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                response.raise_for_status()
            body = response.json()
            text = str(body.get("message", {}).get("content", "")).strip()
            if text:
                history.append({"role": "assistant", "content": text})
            return text
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

    async def _run(self, *argv: str, stdin: bytes | None = None) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin), timeout=self.timeout_seconds
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise ProviderError(f"provider process failed to start or timed out: {exc}") from exc
        if process.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", "replace").strip()[-500:]
            raise ProviderError(f"provider process exited {process.returncode}: {detail}")