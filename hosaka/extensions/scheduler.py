"""Opt-in bounded background actions; never imports extension code into core."""
from __future__ import annotations

import logging
import os
import threading
import time

from hosaka.extensions.manager import Manager
from hosaka.extensions.manifest import ExtensionError, validate_package
from hosaka.extensions.runner import run
from pathlib import Path

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self):
        self.stop = threading.Event()
        self.next_run: dict[str, float] = {}
        self.thread = threading.Thread(target=self._loop, name="extension-background", daemon=True)

    def tick(self, manager: Manager | None = None) -> None:
        if os.geteuid() == 0 or os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}:
            return
        manager = manager or Manager()
        for item in manager.discover()["extensions"]:
            identifier = item["id"]
            if not item["execution_available"] or "background:self" not in item["grants"]:
                continue
            background = validate_package(Path(item["path"])).manifest.background
            if background is None or time.monotonic() < self.next_run.get(identifier, 0):
                continue
            self.next_run[identifier] = time.monotonic() + background.interval_seconds
            result = run(manager, identifier, background.action, {}, background=True, cancellation=self.stop)
            if not result["ok"] and result["error"]["code"] != "busy":
                log.warning("Extension background action failed: %s (%s)", identifier, result["error"]["code"])

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.tick()
            except (OSError, ExtensionError, ValueError) as exc:
                log.error("Extension scheduler error (%s); run extensions doctor", type(exc).__name__)
            self.stop.wait(5)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=65)
        if self.thread.is_alive():
            raise RuntimeError("Extension background scheduler failed to stop.")
