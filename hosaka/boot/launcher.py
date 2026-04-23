from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from hosaka.main_console import run_main_console
from hosaka.setup.orchestrator import build_default_orchestrator
from hosaka.tui.terminal import run_setup_flow


WEB_HOST = os.getenv("HOSAKA_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))
BOOT_MODE = os.getenv("HOSAKA_BOOT_MODE", "console")
PICOCLAW_GATEWAY_PORT = int(os.getenv("PICOCLAW_GATEWAY_PORT", "18790"))
# Desktop mode is set by the cross-platform `hosaka` launcher when the
# container is running on a laptop (not a Pi). In that case we avoid the
# Pi-only assumptions: don't try to auto-start the picoclaw gateway
# (the desktop user hasn't onboarded a key yet), and don't crash on
# missing /proc/net shapes during network introspection.
DESKTOP_MODE = os.getenv("HOSAKA_DESKTOP_MODE") == "1"
# `client` is a special desktop-mode boot: this container is just a
# front-end; the real Hosaka lives somewhere else on the tailnet, pointed
# at by $HOSAKA_REMOTE. We don't spin up the local web server or picoclaw.
REMOTE_URL = os.getenv("HOSAKA_REMOTE", "").strip()
# Skip the Python ANSI shell; keep the FastAPI/JS UI as the only interactive surface.
_WEB_PRIMARY_MODES = frozenset({"headless", "kiosk", "web"})


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_web_server() -> subprocess.Popen[str] | None:
    if is_port_in_use("127.0.0.1", WEB_PORT):
        print(f"Hosaka notice: port {WEB_PORT} already in use, reusing existing web setup server.")
        return None

    # In console mode the TUI owns the terminal; the uvicorn subprocess inherits
    # FDs 1/2 and would otherwise crash log lines into the operator's prompt.
    # Route web logs to a file in console mode; keep them on stdout otherwise.
    web_primary = BOOT_MODE in _WEB_PRIMARY_MODES
    stdout: int | object = sys.stdout
    stderr: int | object = sys.stderr
    if not web_primary:
        log_path = Path(os.getenv("HOSAKA_WEB_LOG", "/var/log/hosaka/web.log"))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_fp = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            stdout = log_fp
            stderr = log_fp
        except OSError:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

    try:
        process = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "uvicorn",
                "hosaka.web.server:app",
                "--host",
                WEB_HOST,
                "--port",
                str(WEB_PORT),
                "--log-level",
                "warning",
            ],
            stdout=stdout,
            stderr=stderr,
        )
        return process
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka warning: failed to start web setup server: {exc}")
        return None


# ── Picoclaw gateway ─────────────────────────────────────────────────────────

_PICOCLAW_MIN_BYTES = 1_000_000  # real binary is ~26 MB; 9-byte "Not Found" must fail.


def _picoclaw_installed() -> bool:
    """Truthy only if picoclaw is on PATH AND looks like a real binary.

    Guards against a clobbered `/usr/local/bin/picoclaw` (e.g. someone curled
    a 404 page over it). We don't trust `shutil.which` alone.
    """
    path = shutil.which("picoclaw")
    if not path:
        return False
    try:
        size = Path(path).stat().st_size
    except OSError:
        return False
    if size < _PICOCLAW_MIN_BYTES:
        print(
            f"Hosaka: picoclaw at {path} is only {size} bytes — looks corrupted "
            "(likely a failed download wrote over the binary). Restart the "
            "container to restore the image's copy, or reinstall from "
            "https://github.com/sipeed/picoclaw/releases",
        )
        return False
    return True


def start_picoclaw_gateway() -> subprocess.Popen | None:  # type: ignore[type-arg]
    """Start the Picoclaw gateway in the background if available."""
    # On a desktop install the user hasn't onboarded picoclaw yet — the
    # first-run web UI collects their model provider key and writes the
    # config, after which they can start the gateway manually. Starting
    # it here just spams the log with "config not found" every boot.
    if DESKTOP_MODE:
        return None
    if not _picoclaw_installed():
        return None

    if is_port_in_use("127.0.0.1", PICOCLAW_GATEWAY_PORT):
        return None  # already running

    config_path = Path.home() / ".picoclaw" / "config.json"
    if not config_path.exists():
        print("Hosaka: picoclaw config not found — run 'picoclaw onboard' first.")
        print("Hosaka: continuing without gateway — the console will prompt for API key.")
        return None

    log_path = Path(os.getenv("HOSAKA_PICOCLAW_LOG", "/var/log/hosaka/picoclaw.log"))
    stdout: int | object = subprocess.DEVNULL
    stderr: int | object = subprocess.DEVNULL
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        stdout = log_fp
        stderr = log_fp
    except OSError:
        pass

    try:
        proc = subprocess.Popen(  # noqa: S603
            ["picoclaw", "gateway"],
            stdout=stdout,
            stderr=stderr,
        )
        time.sleep(2)  # brief pause for gateway to bind
        if proc.poll() is not None:
            print(
                f"Hosaka: picoclaw gateway exited immediately (code {proc.returncode}) — "
                f"check {log_path}",
            )
            return None
        return proc
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka: could not start picoclaw gateway: {exc}")
        return None


# ── main entry ────────────────────────────────────────────────────────────────

def _run_client_mode() -> None:
    """Desktop 'client' boot: no local web server, just point the operator
    at the remote Hosaka they linked to via `hosaka link`."""
    if not REMOTE_URL:
        print(
            "Hosaka client mode: HOSAKA_REMOTE is not set. "
            "Did you mean to run `hosaka up` (local) or `hosaka link <host>` first?",
        )
        sys.exit(2)
    print(f"Hosaka client: linked to {REMOTE_URL}")
    print("Open the web UI in your browser, or use `hosaka open`.")
    # Hand off to the TUI which honours HOSAKA_REMOTE for API calls.
    # (If main_console doesn't yet speak remote, the user still gets a
    # working browser path via `hosaka open`.)
    try:
        run_main_console()
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka client: main console exited ({exc})")
        sys.exit(1)


def launch() -> None:
    if BOOT_MODE == "client":
        _run_client_mode()
        return

    orchestrator = build_default_orchestrator()
    try:
        orchestrator.update_runtime_network()
    except Exception as exc:  # noqa: BLE001
        # /proc/net shapes differ on macOS/WSL containers — don't let
        # network introspection kill the desktop boot.
        if DESKTOP_MODE:
            print(f"Hosaka desktop: skipping network introspection ({exc})")
        else:
            raise
    web_url = f"http://{orchestrator.state.local_ip}:{WEB_PORT}"
    web_process = start_web_server()

    start_picoclaw_gateway()

    web_primary = BOOT_MODE in _WEB_PRIMARY_MODES
    if web_primary or not sys.stdin.isatty():
        if not web_primary and not sys.stdin.isatty():
            print("Hosaka warning: no TTY detected; falling back to headless web setup mode.")
        if BOOT_MODE == "kiosk":
            print(
                "Hosaka kiosk/web-primary mode: use the browser UI (systemd hosaka-kiosk.service), "
                f"not this TTY — {web_url}",
            )
        print(f"Hosaka web setup available at: {web_url}")
        while True:
            if web_process and web_process.poll() is not None:
                print("Hosaka warning: web setup process exited; retrying in 5s")
                time.sleep(5)
                web_process = start_web_server()
            time.sleep(60)

    if not orchestrator.state.setup_completed:
        try:
            run_setup_flow(orchestrator=orchestrator, web_url=web_url)
        except Exception as exc:  # noqa: BLE001
            orchestrator.state.last_error = f"Setup flow crashed: {exc}"
            orchestrator.persist()
            raise

    run_main_console()


if __name__ == "__main__":
    launch()
