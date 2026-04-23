"""Single-frame grab from the attached USB webcam (V4L2 via opencv).

We deliberately open the device on demand and release it right after —
Pi 3B can't easily share a V4L2 device between the voice daemon and the
browser preview, and holding the device open kills the kiosk's ability
to show a live feed.
"""

from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger("hosaka.voice.camera")

DEVICE = os.getenv("HOSAKA_VOICE_CAMERA", "/dev/video0")
WIDTH = int(os.getenv("HOSAKA_VOICE_CAMERA_WIDTH", "640"))
HEIGHT = int(os.getenv("HOSAKA_VOICE_CAMERA_HEIGHT", "480"))
JPEG_QUALITY = int(os.getenv("HOSAKA_VOICE_CAMERA_JPEG_QUALITY", "75"))
WARMUP_FRAMES = 3  # cheap cameras return a green frame on first read

_lock = threading.Lock()


class CameraError(RuntimeError):
    pass


def _open_capture():
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:
        raise CameraError(f"opencv not installed: {exc}") from exc

    target: object = DEVICE
    # cv2 also accepts an integer index; if DEVICE is "/dev/videoN" give
    # the numeric index a shot after the path fails, some V4L2 stacks
    # only like one or the other.
    cap = cv2.VideoCapture(DEVICE)
    if not cap.isOpened():
        cap.release()
        try:
            idx = int("".join(c for c in DEVICE if c.isdigit()) or "0")
        except ValueError:
            idx = 0
        cap = cv2.VideoCapture(idx)
        target = idx
    if not cap.isOpened():
        raise CameraError(f"could not open camera at {DEVICE!r}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    log.debug("camera opened at %r", target)
    return cap, cv2


def snapshot_jpeg() -> bytes:
    """Grab one JPEG from the webcam.

    Raises :class:`CameraError` if the device is unavailable.
    """
    with _lock:
        cap, cv2 = _open_capture()
        try:
            for _ in range(WARMUP_FRAMES):
                cap.read()
                time.sleep(0.02)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise CameraError("camera returned no frame")
            ok, buf = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
            )
            if not ok:
                raise CameraError("jpeg encode failed")
            return bytes(buf)
        finally:
            cap.release()


def is_available() -> bool:
    try:
        snapshot_jpeg()
        return True
    except Exception:  # noqa: BLE001
        return False
