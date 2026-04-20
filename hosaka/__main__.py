from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Load .env (repo root or cwd) before anything reads os.environ.
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(_env_file, override=False)
except ImportError:
    pass

# ── logging ───────────────────────────────────────────────────────────────────
_LOG_FILE = os.getenv("HOSAKA_LOG_FILE", "/var/log/hosaka/boot.log")
_LOG_LEVEL = os.getenv("HOSAKA_LOG_LEVEL", "INFO").upper()

_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
try:
    _log_path = Path(_LOG_FILE)
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(_log_path, encoding="utf-8")
    _handlers.append(_file_handler)

    # Tee all print() output to the log file as well as tty
    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, data):
            for s in self._streams:
                try:
                    s.write(data)
                    s.flush()
                except Exception:
                    pass
        def flush(self):
            for s in self._streams:
                try:
                    s.flush()
                except Exception:
                    pass
        def fileno(self):
            return self._streams[0].fileno()

    _logfile_stream = open(_log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = _Tee(sys.__stdout__, _logfile_stream)
    sys.stderr = _Tee(sys.__stderr__, _logfile_stream)

except OSError:
    pass  # log dir not writable — stdout only

logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=_handlers,
)

# Quiet noisy third-party loggers that would otherwise crash into the TUI
# prompt every time the agent makes an HTTP call. Override with HOSAKA_LOG_LEVEL=DEBUG.
_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "openai", "openai._base_client")
for _name in _NOISY_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)
# ─────────────────────────────────────────────────────────────────────────────

from hosaka.boot.launcher import launch


if __name__ == "__main__":
    launch()
