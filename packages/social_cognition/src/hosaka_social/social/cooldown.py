from __future__ import annotations


def recent_speech_factor(
    last_speech_mono: float | None,
    now_mono: float,
    cooldown_seconds: float,
) -> float:
    """1.0 immediately after speech, 0.0 after cooldown. Monotonic times only."""
    if last_speech_mono is None or cooldown_seconds <= 0:
        return 0.0
    elapsed = now_mono - last_speech_mono
    if elapsed <= 0:
        return 1.0
    if elapsed + 1e-9 >= cooldown_seconds:
        return 0.0
    return 1.0 - (elapsed / cooldown_seconds)
