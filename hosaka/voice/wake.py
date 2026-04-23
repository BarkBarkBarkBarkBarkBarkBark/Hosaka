"""Wake-word + microphone plumbing for the headless voice daemon.

Responsibilities:

* Open the USB mic at 16 kHz / mono / 16-bit (what openwakeword wants
  and what Realtime tolerates — we upsample to 24 kHz before sending).
* Run openwakeword on every 80 ms frame.
* Expose an async ``listen_for_wake()`` that resolves once the wake
  score crosses ``threshold``, then an ``audio_chunks()`` generator that
  yields raw PCM16 frames for as long as the daemon wants them.

This module lazily imports sounddevice / openwakeword / numpy so the
rest of Hosaka keeps working on a host without PortAudio.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

log = logging.getLogger("hosaka.voice.wake")

SAMPLE_RATE_IN = 16_000      # openwakeword native rate
SAMPLE_RATE_OUT = 24_000     # OpenAI Realtime native rate
FRAME_MS = 80
FRAME_SAMPLES = SAMPLE_RATE_IN * FRAME_MS // 1000  # 1280 @ 16 kHz

DEFAULT_WAKEWORD = os.getenv("HOSAKA_VOICE_WAKEWORD", "hey_jarvis")
DEFAULT_THRESHOLD = float(os.getenv("HOSAKA_VOICE_WAKE_THRESHOLD", "0.5"))
INPUT_DEVICE_ENV = "HOSAKA_VOICE_INPUT_DEVICE"


def _input_device() -> int | str | None:
    raw = os.getenv(INPUT_DEVICE_ENV, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


class WakeListener:
    """Async wrapper around sounddevice + openwakeword.

    Usage::

        async with WakeListener() as wake:
            await wake.wait_for_wake()     # blocks until 'hey jarvis'
            async for pcm_24k in wake.stream_until_silent(max_seconds=30):
                await rt.send_pcm16(pcm_24k)
    """

    def __init__(
        self,
        *,
        wakeword: str = DEFAULT_WAKEWORD,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._wakeword = wakeword
        self._threshold = threshold
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stream = None  # sounddevice.InputStream
        self._oww = None     # openwakeword.Model
        self._numpy = None

    async def __aenter__(self) -> "WakeListener":
        self._loop = asyncio.get_running_loop()
        try:
            import numpy as np
            import sounddevice as sd
            from openwakeword.model import Model as OwwModel
        except ImportError as exc:
            raise ImportError(
                "voice deps missing — pip install -r requirements-voice.txt "
                f"({exc})"
            ) from exc

        self._numpy = np
        try:
            self._oww = OwwModel(
                wakeword_models=[self._wakeword],
                inference_framework="onnx",
            )
        except Exception:  # noqa: BLE001
            log.warning(
                "openwakeword: %r not bundled, falling back to default preset",
                self._wakeword,
            )
            self._oww = OwwModel(inference_framework="onnx")

        def _cb(indata, _frames, _time, status):  # noqa: ANN001
            if status:
                log.debug("sounddevice status: %s", status)
            pcm = bytes(indata)
            if self._loop is None:
                return
            self._loop.call_soon_threadsafe(self._enqueue, pcm)

        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE_IN,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
            device=_input_device(),
            callback=_cb,
        )
        self._stream.start()
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        self._oww = None

    def _enqueue(self, pcm: bytes) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(pcm)
        except asyncio.QueueFull:
            pass

    # ── wake detection ────────────────────────────────────────────────

    async def wait_for_wake(self) -> str:
        """Block until any wakeword score exceeds the threshold.

        Returns the name of the model that fired (useful if you loaded
        multiple).
        """
        np = self._numpy
        assert np is not None and self._oww is not None
        while True:
            pcm = await self._queue.get()
            samples = np.frombuffer(pcm, dtype=np.int16)
            scores = self._oww.predict(samples)
            for name, score in scores.items():
                if score >= self._threshold:
                    log.info("wake word %r (%.2f)", name, score)
                    self._oww.reset()
                    return name

    # ── post-wake audio stream ────────────────────────────────────────

    async def stream_pcm24k(
        self,
        *,
        max_seconds: float = 30.0,
    ) -> AsyncIterator[bytes]:
        """Yield 24 kHz mono PCM16 frames from the mic.

        We feed this straight into OpenAI Realtime. VAD lives on the
        server side, so this generator simply keeps pumping until the
        caller stops iterating (or ``max_seconds`` elapses as a
        belt-and-braces safety cap).
        """
        np = self._numpy
        assert np is not None
        deadline = asyncio.get_running_loop().time() + max_seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                pcm = await asyncio.wait_for(
                    self._queue.get(), timeout=max(0.05, deadline - asyncio.get_running_loop().time()),
                )
            except asyncio.TimeoutError:
                return
            # upsample 16 kHz -> 24 kHz by simple 2x / 3x resampling
            # (good enough for speech; sox-quality isn't worth the CPU).
            src = np.frombuffer(pcm, dtype=np.int16)
            if src.size == 0:
                continue
            # 16k -> 24k: 2 out samples for every 3 in, linear interp.
            out_len = src.size * SAMPLE_RATE_OUT // SAMPLE_RATE_IN
            idx = np.linspace(0, src.size - 1, out_len, dtype=np.float32)
            lo = np.floor(idx).astype(np.int32)
            hi = np.clip(lo + 1, 0, src.size - 1)
            frac = (idx - lo).astype(np.float32)
            up = (src[lo].astype(np.float32) * (1 - frac)
                  + src[hi].astype(np.float32) * frac)
            yield np.clip(up, -32768, 32767).astype(np.int16).tobytes()


# ── speaker-side helpers ─────────────────────────────────────────────────


class Speaker:
    """Play back 24 kHz PCM16 frames from the Realtime session."""

    def __init__(self) -> None:
        self._stream = None
        self._sd = None

    def __enter__(self) -> "Speaker":
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise ImportError(
                "voice deps missing — pip install -r requirements-voice.txt "
                f"({exc})"
            ) from exc
        self._sd = sd
        dev_raw = os.getenv("HOSAKA_VOICE_OUTPUT_DEVICE", "").strip()
        device: int | str | None = None
        if dev_raw:
            try:
                device = int(dev_raw)
            except ValueError:
                device = dev_raw
        self._stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE_OUT,
            channels=1,
            dtype="int16",
            blocksize=0,
            device=device,
        )
        self._stream.start()
        return self

    def __exit__(self, *_exc) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
        self._stream = None

    def play(self, pcm: bytes) -> None:
        if self._stream is None or not pcm:
            return
        try:
            self._stream.write(pcm)
        except Exception:  # noqa: BLE001
            log.exception("speaker write failed")
