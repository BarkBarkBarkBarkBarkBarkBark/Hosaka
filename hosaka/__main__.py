from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Path inspection must work without loading secrets, logs, or the boot stack.
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in {"paths", "doctor", "migrate", "extensions"}:
    if sys.argv[1] == "paths":
        from hosaka.paths import main as diagnostic_main
    elif sys.argv[1] == "doctor":
        from hosaka.doctor import main as diagnostic_main
    elif sys.argv[1] == "migrate":
        from hosaka.migration import main as diagnostic_main
    else:
        from hosaka.extensions.__main__ import main as diagnostic_main
    raise SystemExit(diagnostic_main(sys.argv[2:]))

# The TUI is the product. Parent processes (Cursor, CI, a polluted desktop
# session) often export NO_COLOR=1 / TERM=dumb — strip that before style.py
# bakes its palette at import time.
if len(sys.argv) > 1 and sys.argv[1] in {"tui", "console"}:
    os.environ.pop("NO_COLOR", None)
    os.environ["FORCE_COLOR"] = "1"
    if os.environ.get("TERM", "dumb") in {"", "dumb", "unknown"}:
        os.environ["TERM"] = "xterm-256color"
    os.environ.setdefault("COLORTERM", "truecolor")

# Load .env (repo root or cwd) before anything reads os.environ.
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(_env_file, override=False)
except ImportError:
    pass

# Hydrate os.environ from the Hosaka-native JSON secrets store. Runs after
# dotenv so explicit shell exports + repo-local .env still win, but anything
# the operator stored via `hosaka secrets set` becomes visible to every
# entrypoint (TUI, voice daemon, webserver) without a systemd reload.
try:
    from hosaka.secrets import store as _secrets_store
    _secrets_store.apply_to_env()
except Exception:  # noqa: BLE001 - never let secrets loading kill boot
    pass

if len(sys.argv) > 1 and sys.argv[1] in {"tui", "console"}:
    os.environ.pop("NO_COLOR", None)
    os.environ["FORCE_COLOR"] = "1"

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


def _dispatch_argv() -> int | None:
    """Tiny subcommand router layered on top of the default launcher.

    Returns the desired exit code if a subcommand was handled, or None
    to fall through to the interactive launcher (the historical behaviour
    when running ``python -m hosaka`` with no args).
    """
    if len(sys.argv) < 2:
        return None
    cmd = sys.argv[1]
    if cmd in {"chat", "message"}:
        from hosaka.llm.chat import main as chat_main
        return chat_main(sys.argv[1:])
    if cmd == "play":
        from hosaka.play import main as play_main
        return play_main(sys.argv[2:])
    if cmd in {"tui", "console"}:
        from hosaka.boot.launcher import run_console_supervised
        run_console_supervised()
        return 0
    if cmd == "voice":
        from hosaka.voice.daemon import main as voice_main
        return voice_main()
    if cmd in {"launch", "apps"}:
        from hosaka.apps import main as apps_main
        return apps_main(sys.argv[2:])
    return None


if __name__ == "__main__":
    rc = _dispatch_argv()
    if rc is not None:
        sys.exit(rc)
    launch()
