"""Voice mode for Hosaka.

Everything under this package is optional — `import hosaka.voice` works
without sounddevice/opencv/openwakeword installed, but calling into the
daemon / camera / wake modules without those deps will raise a clear
``ImportError`` so the TUI and web paths can degrade gracefully.

Pieces:

* ``tools``           — shared tool schema + dispatcher used by both the
                        headless Python daemon and the browser client.
* ``realtime_client`` — tiny async OpenAI Realtime WS client.
* ``wake``            — openwakeword + VAD loop.
* ``camera``          — V4L2 frame grab via opencv.
* ``vision``          — one-shot vision call (gpt-4o-mini) on a JPEG.
* ``daemon``          — the full wake -> Realtime -> speakers loop.
"""

from __future__ import annotations

__all__ = [
    "tools",
    "realtime_client",
    "wake",
    "camera",
    "vision",
    "daemon",
]
