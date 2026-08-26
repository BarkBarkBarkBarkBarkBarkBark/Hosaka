"""Wake-word + microphone plumbing for the headless voice daemon.

Responsibilities:

* Open the USB mic at a rate the hardware actually supports (many
  CM108-style sticks are 44.1/48 kHz only), then resample to 16 kHz
  for openwakeword and 24 kHz for Realtime.
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
import math
import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import AsyncIterator

log = logging.getLogger("hosaka.voice.wake")

SAMPLE_RATE_IN = 16_000      # openwakeword native rate
SAMPLE_RATE_OUT = 24_000     # OpenAI Realtime native rate
FRAME_MS = 80


class AdaptiveFloor:
    """Rolling 20th-percentile noise floor from mic RMS frames."""

    def __init__(self, *, window: int = 62, min_samples: int = 8) -> None:
        self._samples: deque[float] = deque(maxlen=window)
        self.floor = 200.0
        self._min_samples = min_samples

    def observe(self, rms: float) -> float:
        self._samples.append(float(rms))
        if len(self._samples) >= self._min_samples:
            ordered = sorted(self._samples)
            self.floor = ordered[max(0, (len(ordered) * 20) // 100)]
        return self.floor

    def is_speech(self, rms: float) -> bool:
        return float(rms) > max(self.floor * 3.5, self.floor + 300.0)

    def is_barge_in(self, rms: float) -> bool:
        """Stricter than is_speech so speaker echo does not cancel TTS."""
        return float(rms) > max(self.floor * 8.0, self.floor + 1200.0, 900.0)


_INSTALL_HINT = (
    "voice daemon deps missing — from the Hosaka venv run:\n"
    "  pip install -r requirements-voice-daemon.txt\n"
    "  pip install --no-deps openwakeword   # skip on Python 3.13 if tflite fails\n"
    "Also: sudo apt-get install -y libportaudio2"
)


def _double_pcm16(pcm: bytes) -> bytes:
    n = len(pcm) // 2
    if n == 0:
        return b""
    src = memoryview(pcm).cast("h")
    out = bytearray(n * 4)
    dst = memoryview(out).cast("h")
    j = 0
    for i in range(n):
        v = src[i]
        dst[j] = v
        dst[j + 1] = v
        j += 2
    return bytes(out)


def _half_pcm16(pcm: bytes) -> bytes:
    n = len(pcm) // 4
    if n == 0:
        return b""
    src = memoryview(pcm).cast("h")
    out = bytearray(n * 2)
    dst = memoryview(out).cast("h")
    for i in range(n):
        a = int(src[i * 2])
        b = int(src[i * 2 + 1])
        dst[i] = (a + b) >> 1
    return bytes(out)


def _gain_pcm16(pcm: bytes, gain: float) -> bytes:
    if gain >= 0.99 or not pcm:
        return pcm
    g = max(0, min(256, int(gain * 256)))
    src = memoryview(pcm).cast("h")
    out = bytearray(len(pcm))
    dst = memoryview(out).cast("h")
    for i in range(len(src)):
        dst[i] = (int(src[i]) * g) >> 8
    return bytes(out)


def _clip16(v: int) -> int:
    if v > 32767:
        return 32767
    if v < -32768:
        return -32768
    return v


class VoiceColor:
    """Cheap playback color. Hall hides leftover edges; robot leans into them."""

    def __init__(self, rate: int, channels: int, style: str) -> None:
        self.style = (style or "off").strip().lower()
        self.channels = max(1, channels)
        self._hold: list[int] = [0] * self.channels
        self._hold_left = 0
        self._factor = 4
        combs: list[list[int]] = []
        if self.style == "hall":
            for delay_s, _fb in (
                (0.0297, 0.52),
                (0.0371, 0.48),
                (0.0411, 0.45),
                (0.0437, 0.43),
                (0.18, 0.28),
            ):
                combs.append([0] * max(8, int(rate * delay_s)))
            self._idx = [0] * len(combs)
            self._fb = [0.52, 0.48, 0.45, 0.43, 0.28]
            self._combs = combs
        else:
            self._idx = []
            self._fb: list[float] = []
            self._combs = combs

    def reset(self) -> None:
        for line in self._combs:
            for i in range(len(line)):
                line[i] = 0
        self._idx = [0] * len(self._combs)
        self._hold = [0] * self.channels
        self._hold_left = 0

    def process(self, pcm: bytes) -> bytes:
        if self.style in {"", "off", "none"} or not pcm:
            return pcm
        if self.style == "robot":
            return self._robot(pcm)
        if self.style == "hall":
            return self._hall(pcm)
        return pcm

    def _robot(self, pcm: bytes) -> bytes:
        src = memoryview(pcm).cast("h")
        out = bytearray(len(pcm))
        dst = memoryview(out).cast("h")
        ch = self.channels
        nframes = len(src) // ch
        left = self._hold_left
        hold = self._hold
        factor = self._factor
        j = 0
        for _ in range(nframes):
            if left <= 0:
                for c in range(ch):
                    hold[c] = (int(src[j + c]) >> 3) << 3
                left = factor
            for c in range(ch):
                dst[j + c] = hold[c]
            j += ch
            left -= 1
        self._hold_left = left
        self._hold = hold
        return bytes(out)

    def _hall(self, pcm: bytes) -> bytes:
        src = memoryview(pcm).cast("h")
        out = bytearray(len(pcm))
        dst = memoryview(out).cast("h")
        combs = self._combs
        idx = self._idx
        fb = self._fb
        n_combs = len(combs)
        wet_n, dry_n = 7, 9
        for i in range(len(src)):
            x = int(src[i])
            acc = 0
            for k in range(n_combs):
                line = combs[k]
                p = idx[k]
                y = line[p]
                line[p] = _clip16(x + int(y * fb[k]))
                idx[k] = p + 1 if p + 1 < len(line) else 0
                acc += y
            mixed = (x * dry_n + (acc // max(1, n_combs)) * wet_n) // (dry_n + wet_n)
            dst[i] = _clip16(mixed)
        self._idx = idx
        return bytes(out)


def _voice_fx_style() -> str:
    raw = os.getenv("HOSAKA_VOICE_FX", "off").strip().lower()
    if raw in {"robot", "decimate", "crush"}:
        return "robot"
    if raw in {"hall", "reverb", "echo", "god"}:
        return "hall"
    return "off"


def pcm_rms16(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    src = memoryview(pcm).cast("h")
    acc = 0
    step = max(1, n // 64)
    count = 0
    for i in range(0, n, step):
        v = int(src[i])
        acc += v * v
        count += 1
    return (acc / count) ** 0.5


def _resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Packed int16 mono PCM. Fast 2×/½ paths; linear otherwise. No numpy."""
    if src_rate <= 0 or dst_rate <= 0:
        return b""
    if src_rate == dst_rate:
        return pcm
    if dst_rate == src_rate * 2:
        return _double_pcm16(pcm)
    if src_rate == dst_rate * 2:
        return _half_pcm16(pcm)
    n = len(pcm) // 2
    if n == 0:
        return b""
    src = memoryview(pcm).cast("h")
    out_n = n * dst_rate // src_rate
    if out_n == 0:
        return b""
    out = bytearray(out_n * 2)
    dst = memoryview(out).cast("h")
    for j in range(out_n):
        num = j * src_rate
        i = num // dst_rate
        frac = num % dst_rate
        if i + 1 < n:
            a = int(src[i])
            b = int(src[i + 1])
            dst[j] = a + (b - a) * frac // dst_rate
        else:
            dst[j] = int(src[min(i, n - 1)])
    return bytes(out)


def _downmix_to_mono(pcm: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm
    nframes = len(pcm) // (2 * channels)
    src = memoryview(pcm).cast("h")
    out = bytearray(nframes * 2)
    dst = memoryview(out).cast("h")
    for i in range(nframes):
        acc = 0
        base = i * channels
        for c in range(channels):
            acc += int(src[base + c])
        dst[i] = acc // channels
    return bytes(out)


def _upmix_mono(pcm: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm
    n = len(pcm) // 2
    src = memoryview(pcm).cast("h")
    out = bytearray(n * channels * 2)
    dst = memoryview(out).cast("h")
    j = 0
    for i in range(n):
        v = int(src[i])
        for _ in range(channels):
            dst[j] = v
            j += 1
    return bytes(out)


def _upsample_16k_to_24k(pcm: bytes) -> bytes:
    """2:3 upsample without numpy (16 kHz → 24 kHz)."""
    return _resample_pcm16(pcm, SAMPLE_RATE_IN, SAMPLE_RATE_OUT)


DEFAULT_WAKEWORD = os.getenv("HOSAKA_VOICE_WAKEWORD", "hey_jarvis")
DEFAULT_THRESHOLD = float(os.getenv("HOSAKA_VOICE_WAKE_THRESHOLD", "0.5"))
INPUT_DEVICE_ENV = "HOSAKA_VOICE_INPUT_DEVICE"
OUTPUT_DEVICE_ENV = "HOSAKA_VOICE_OUTPUT_DEVICE"
INPUT_RATE_ENV = "HOSAKA_VOICE_INPUT_RATE"
_DUPLEX_HINTS = ("p10s", "speakerphone", "jabra", "conference", "polycom", "yeti")


def _parse_device_env(raw: str) -> int | str | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def pick_voice_devices(
    devices: list[dict],
    *,
    env_in: int | str | None = None,
    env_out: int | str | None = None,
) -> tuple[int | str | None, int | str | None]:
    """Prefer a duplex USB conference puck for both mic and speaker."""
    duplex: list[int] = []
    inputs: list[int] = []
    for i, d in enumerate(devices):
        inn = int(d.get("max_input_channels") or 0)
        out = int(d.get("max_output_channels") or 0)
        if inn >= 1:
            inputs.append(i)
        if inn >= 1 and out >= 1:
            duplex.append(i)
    if not inputs:
        for i, d in enumerate(devices):
            name = str(d.get("name") or "").lower()
            if any(h in name for h in _DUPLEX_HINTS):
                inputs.append(i)

    def _hint_score(i: int) -> tuple[int, int]:
        name = str(devices[i].get("name") or "").lower()
        return (1 if any(h in name for h in _DUPLEX_HINTS) else 0, i)

    in_dev: int | str | None = env_in
    out_dev: int | str | None = env_out
    if in_dev is None:
        pool = duplex or inputs
        in_dev = max(pool, key=_hint_score) if pool else None
    if out_dev is None and isinstance(in_dev, int):
        if int(devices[in_dev].get("max_output_channels") or 0) >= 1:
            out_dev = in_dev
    return in_dev, out_dev


def _rate_candidates(sd, device: int | str | None, *, forced_env: str) -> list[int]:
    forced = os.getenv(forced_env, "").strip()
    if forced:
        return [int(forced)]
    rates: list[int] = []
    try:
        native = int(sd.query_devices(device)["default_samplerate"])
    except Exception:  # noqa: BLE001
        native = 0
    for rate in (48_000, native, 44_100, 24_000, 16_000):
        if rate > 0 and rate not in rates:
            rates.append(rate)
    return rates


def _alsa_card(sd, device: int | str | None) -> str | None:
    try:
        name = str(sd.query_devices(device)["name"] if device is not None else "")
    except Exception:  # noqa: BLE001
        name = str(device or "")
    match = re.search(r"hw:(\d+)", name)
    return match.group(1) if match else None


def _proc_cmd(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace")


def _alsa_holder_pids() -> set[int]:
    pids: set[int] = set()
    snd = Path("/dev/snd")
    if not snd.is_dir():
        return pids
    for path in snd.glob("pcmC*"):
        try:
            proc = subprocess.run(
                ["fuser", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        blob = f"{proc.stdout} {proc.stderr}"
        for tok in blob.replace(":", " ").split():
            if tok.isdigit():
                pids.add(int(tok))
    return pids


def reclaim_stale_voice(*, timeout_s: float = 1.2) -> None:
    """SIGTERM/KILL other Hosaka processes still holding the mic/speaker."""
    me = os.getpid()
    holders = _alsa_holder_pids() - {me}
    stale = [pid for pid in holders if "hosaka" in _proc_cmd(pid).lower()]
    if not stale:
        return
    for pid in stale:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        left = (_alsa_holder_pids() - {me}) & set(stale)
        if not left:
            time.sleep(0.15)
            return
        time.sleep(0.08)
    for pid in (_alsa_holder_pids() - {me}) & set(stale):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(0.2)


def ensure_playback_volume(sd, device: int | str | None, *, percent: int = 70) -> None:
    """Unmute, and lift a silent (0%) playback control so the puck can be heard.

    Leaves a non-zero mixer setting alone so a real volume dial still wins.
    """
    card = _alsa_card(sd, device)
    if card is None:
        return
    for control in ("PCM", "Speaker", "Headphone", "Master"):
        subprocess.run(
            ["amixer", "-q", "-c", card, "sset", control, "unmute"],
            check=False,
            capture_output=True,
        )
        got = subprocess.run(
            ["amixer", "-c", card, "sget", control],
            check=False,
            capture_output=True,
            text=True,
        )
        if got.returncode != 0 or "[off]" in (got.stdout or ""):
            continue
        percents = [int(x) for x in re.findall(r"\[(\d+)%\]", got.stdout or "")]
        if percents and max(percents) <= 5:
            subprocess.run(
                ["amixer", "-q", "-c", card, "sset", control, f"{percent}%", "unmute"],
                check=False,
                capture_output=True,
            )


def _channel_candidates(sd, device: int | str | None, *, output: bool) -> list[int]:
    key = "max_output_channels" if output else "max_input_channels"
    try:
        cap = int(sd.query_devices(device)[key] or 1)
    except Exception:  # noqa: BLE001
        cap = 2
    ordered = [c for c in (min(2, max(cap, 1)), 1) if c >= 1]
    out: list[int] = []
    for c in ordered:
        if c not in out:
            out.append(c)
    return out


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
        self._capture_rate = SAMPLE_RATE_IN
        self._capture_channels = 1

    @property
    def wake_enabled(self) -> bool:
        return self._oww is not None

    async def __aenter__(self) -> "WakeListener":
        self._loop = asyncio.get_running_loop()
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise ImportError(f"{_INSTALL_HINT}\n({exc})") from exc

        try:
            import numpy as np
        except ImportError:
            np = None

        self._numpy = np
        self._oww = None
        skip_wake = self._wakeword.strip().lower() in {"", "off", "none", "passthrough"}
        if not skip_wake:
            try:
                from openwakeword.model import Model as OwwModel
            except ImportError:
                log.debug("openwakeword not installed — listening immediately")
            else:
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
                    try:
                        self._oww = OwwModel(inference_framework="onnx")
                    except Exception:  # noqa: BLE001
                        self._oww = None

        def _cb(indata, _frames, _time, status):  # noqa: ANN001
            if status:
                log.debug("sounddevice status: %s", status)
            pcm = bytes(indata)
            if self._capture_channels > 1:
                pcm = _downmix_to_mono(pcm, self._capture_channels)
            if self._loop is None:
                return
            self._loop.call_soon_threadsafe(self._enqueue, pcm)

        reclaim_stale_voice()
        in_dev, _ = pick_voice_devices(
            list(sd.query_devices()),
            env_in=_parse_device_env(os.getenv(INPUT_DEVICE_ENV, "")),
            env_out=_parse_device_env(os.getenv(OUTPUT_DEVICE_ENV, "")),
        )
        if in_dev is None:
            reclaim_stale_voice()
            in_dev, _ = pick_voice_devices(
                list(sd.query_devices()),
                env_in=_parse_device_env(os.getenv(INPUT_DEVICE_ENV, "")),
                env_out=_parse_device_env(os.getenv(OUTPUT_DEVICE_ENV, "")),
            )
        if in_dev is None:
            raise RuntimeError("couldn't open the microphone")
        candidates = _rate_candidates(sd, in_dev, forced_env=INPUT_RATE_ENV)
        last_exc: Exception | None = None
        for rate in candidates:
            for channels in (1, 2):
                blocksize = max(64, rate * FRAME_MS // 1000)
                try:
                    stream = sd.RawInputStream(
                        samplerate=rate,
                        channels=channels,
                        dtype="int16",
                        blocksize=blocksize,
                        device=in_dev,
                        callback=_cb,
                    )
                    stream.start()
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    continue
                self._stream = stream
                self._capture_rate = rate
                self._capture_channels = channels
                log.debug("mic %s %d Hz ch=%d", in_dev, rate, channels)
                return self
        raise RuntimeError(
            "could not open microphone. "
            f"Tried {candidates} Hz on device {in_dev}. "
            f"Set {INPUT_DEVICE_ENV} / {INPUT_RATE_ENV}. Last error: {last_exc}"
        ) from last_exc

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
        if self._oww is None or np is None:
            log.info("listening immediately (no wake-word model)")
            return "passthrough"
        while True:
            pcm = await self._queue.get()
            pcm16 = _resample_pcm16(pcm, self._capture_rate, SAMPLE_RATE_IN)
            samples = np.frombuffer(pcm16, dtype=np.int16)
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
        deadline = asyncio.get_running_loop().time() + max_seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                pcm = await asyncio.wait_for(
                    self._queue.get(), timeout=max(0.05, deadline - asyncio.get_running_loop().time()),
                )
            except asyncio.TimeoutError:
                return
            up = _resample_pcm16(pcm, self._capture_rate, SAMPLE_RATE_OUT)
            if up:
                yield up


# ── speaker-side helpers ─────────────────────────────────────────────────


class Speaker:
    """Play back 24 kHz PCM16 frames from the Realtime session."""

    def __init__(self) -> None:
        self._stream = None
        self._sd = None
        self._out_dev: int | str | None = None
        self._play_rate = SAMPLE_RATE_OUT
        self._play_channels = 1
        self._last_play = 0.0
        self._q: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._pump: threading.Thread | None = None
        self._running = False
        self._gain = float(os.getenv("HOSAKA_VOICE_GAIN", "0.5"))
        self._duck = 1.0
        self._period_bytes = 0
        self._preroll_ms = int(os.getenv("HOSAKA_VOICE_PREROLL_MS", "120"))

    def __enter__(self) -> "Speaker":
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise ImportError(f"{_INSTALL_HINT}\n({exc})") from exc
        self._sd = sd
        reclaim_stale_voice()
        _, out_dev = pick_voice_devices(
            list(sd.query_devices()),
            env_in=_parse_device_env(os.getenv(INPUT_DEVICE_ENV, "")),
            env_out=_parse_device_env(os.getenv(OUTPUT_DEVICE_ENV, "")),
        )
        self._out_dev = out_dev
        ensure_playback_volume(sd, out_dev)
        self._start_output()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop_output()
        self._sd = None

    def pause(self) -> None:
        """Drop the puck playback handle so RetroArch can open it."""
        self._stop_output()

    def resume(self) -> None:
        if self._stream is not None or self._sd is None:
            return
        try:
            self._start_output()
        except Exception:  # noqa: BLE001
            log.debug("speaker resume failed", exc_info=True)

    def _start_output(self) -> None:
        sd = self._sd
        out_dev = self._out_dev
        if sd is None:
            raise RuntimeError("speaker not entered")
        candidates = _rate_candidates(sd, out_dev, forced_env="HOSAKA_VOICE_OUTPUT_RATE")
        last_exc: Exception | None = None
        for rate in candidates:
            for channels in _channel_candidates(sd, out_dev, output=True):
                period = max(256, rate * 40 // 1000)
                opened = False
                for blocksize in (period, 0):
                    try:
                        kwargs = dict(
                            samplerate=rate,
                            channels=channels,
                            dtype="int16",
                            blocksize=blocksize,
                            device=out_dev,
                        )
                        try:
                            stream = sd.RawOutputStream(**kwargs, latency="high")
                        except TypeError:
                            stream = sd.RawOutputStream(**kwargs)
                        stream.start()
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        continue
                    self._stream = stream
                    self._play_rate = rate
                    self._play_channels = channels
                    self._period_bytes = period * channels * 2
                    opened = True
                    break
                if not opened:
                    continue
                self._running = True
                self._pump = threading.Thread(target=self._pump_loop, daemon=True)
                self._pump.start()
                log.debug("spk %s %d Hz ch=%d", out_dev, rate, channels)
                return
        raise RuntimeError(
            f"could not open speaker on device {out_dev}: {last_exc}"
        ) from last_exc

    def _stop_output(self) -> None:
        self._running = False
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        pump = self._pump
        if pump is not None:
            pump.join(timeout=1.0)
        self._pump = None
        self._drain()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
        self._stream = None

    def play(self, pcm: bytes) -> None:
        if not self._running or not pcm:
            return
        self._last_play = time.monotonic()
        try:
            self._q.put_nowait(pcm)
            return
        except queue.Full:
            pass
        # Prefer dropping the oldest queued chunk over blocking the WS loop.
        try:
            self._q.get_nowait()
        except queue.Empty:
            pass
        try:
            self._q.put_nowait(pcm)
        except queue.Full:
            pass

    def _prepare(self, pcm: bytes) -> bytes:
        pcm = _resample_pcm16(pcm, SAMPLE_RATE_OUT, self._play_rate)
        pcm = _upmix_mono(pcm, self._play_channels)
        return _gain_pcm16(pcm, self._gain * self._duck)

    def _pump_loop(self) -> None:
        period = max(self._period_bytes, 1)
        preroll = max(
            period * 2,
            self._play_rate * self._play_channels * 2 * max(60, self._preroll_ms) // 1000,
        )
        buf = bytearray()
        primed = False
        while self._running:
            try:
                chunk = self._q.get(timeout=0.2 if primed else 0.05)
            except queue.Empty:
                continue
            if chunk is None:
                break
            buf.extend(self._prepare(chunk))
            if not primed:
                if len(buf) < preroll:
                    continue
                primed = True
            while len(buf) >= period:
                self._write_out(bytes(buf[:period]))
                del buf[:period]

    def _write_out(self, pcm: bytes) -> None:
        stream = self._stream
        if stream is None or not pcm:
            return
        try:
            stream.write(pcm)
        except Exception:  # noqa: BLE001
            log.debug("speaker write failed", exc_info=True)

    def recently_played(self, window_s: float = 0.6) -> bool:
        return self._last_play > 0 and (time.monotonic() - self._last_play) < window_s

    def play_tone(self, *, hz: float = 880.0, seconds: float = 0.7, amp: float = 0.45) -> None:
        n = max(1, int(SAMPLE_RATE_OUT * seconds))
        pcm = bytearray(n * 2)
        for i in range(n):
            s16 = int(amp * 32767 * math.sin(2 * math.pi * hz * i / SAMPLE_RATE_OUT))
            fade = min(i, n - 1 - i, int(SAMPLE_RATE_OUT * 0.02)) / max(1, int(SAMPLE_RATE_OUT * 0.02))
            s16 = int(s16 * fade)
            pcm[i * 2 : i * 2 + 2] = s16.to_bytes(2, "little", signed=True)
        self.play(bytes(pcm))

    def _drain(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def duck(self, factor: float = 0.2) -> None:
        self._duck = max(0.0, min(1.0, float(factor)))

    def unduck(self) -> None:
        self._duck = 1.0

    def abort(self) -> None:
        """Drop queued playback immediately (barge-in)."""
        self.unduck()
        self._last_play = 0.0
        self._drain()
        stream = self._stream
        if stream is None:
            return
        try:
            abort = getattr(stream, "abort", None)
            if abort is not None:
                abort()
            else:
                stream.stop()
            if not getattr(stream, "active", True):
                stream.start()
        except Exception:  # noqa: BLE001
            log.debug("speaker abort failed", exc_info=True)
