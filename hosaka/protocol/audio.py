"""Version-one Hosaka inference audio contract."""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
MEDIA_TYPE = "audio/wav"


class InvalidAudio(ValueError):
    pass


@dataclass(frozen=True)
class WavInfo:
    frames: int
    duration_seconds: float


def validate_wav(data: bytes, *, max_seconds: float = 30.0) -> WavInfo:
    if not data:
        raise InvalidAudio("audio body is empty")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            channels = source.getnchannels()
            rate = source.getframerate()
            width = source.getsampwidth()
            compression = source.getcomptype()
            frames = source.getnframes()
            pcm = source.readframes(frames)
    except (EOFError, wave.Error) as exc:
        raise InvalidAudio(f"malformed WAV: {exc}") from exc
    if channels != CHANNELS or rate != SAMPLE_RATE or width != SAMPLE_WIDTH or compression != "NONE":
        raise InvalidAudio(
            f"expected 16000 Hz mono PCM16 WAV; received {rate} Hz, {channels} channel(s), {width * 8}-bit {compression}"
        )
    if frames <= 0 or len(pcm) != frames * CHANNELS * SAMPLE_WIDTH:
        raise InvalidAudio("WAV contains empty or truncated PCM data")
    duration = frames / rate
    if duration > max_seconds:
        raise InvalidAudio(f"audio duration {duration:.2f}s exceeds {max_seconds:.2f}s limit")
    return WavInfo(frames=frames, duration_seconds=duration)