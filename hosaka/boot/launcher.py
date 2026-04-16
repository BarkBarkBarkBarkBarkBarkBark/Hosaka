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
OPENCLAW_GATEWAY_PORT = int(
    os.getenv("OPENCLAW_GATEWAY_PORT")
    or os.getenv("PICOCLAW_GATEWAY_PORT")
    or "18790"
)


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_web_server() -> subprocess.Popen[str] | None:
    if is_port_in_use("127.0.0.1", WEB_PORT):
        print(f"Hosaka notice: port {WEB_PORT} already in use, reusing existing web setup server.")
        return None
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
        )
        return process
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka warning: failed to start web setup server: {exc}")
        return None


# ── OpenClaw gateway ──────────────────────────────────────────────────────────

def _openclaw_installed() -> bool:
    return bool(shutil.which("openclaw"))


def _patch_openclaw_model(model: str) -> None:
    """Patch ~/.openclaw/openclaw.json to use openai/<model> after onboard."""
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        return
    try:
        config = json.loads(config_path.read_text())
        agents = config.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        defaults.setdefault("model", {})["primary"] = f"openai/{model}"
        defaults.setdefault("tools", {})["profile"] = "coding"
        config_path.write_text(json.dumps(config, indent=2))
    except Exception:  # noqa: BLE001
        pass


def _onboard_openclaw() -> None:
    """Run openclaw onboard non-interactively on first boot."""
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        print("Hosaka: OPENAI_API_KEY not set — skipping OpenClaw onboard.")
        print("Hosaka: Set OPENAI_API_KEY and run /openclaw install to enable the agent.")
        return

    token = os.getenv("OPENCLAW_GATEWAY_TOKEN") or secrets.token_hex(16)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    print("Hosaka: first-boot — configuring OpenClaw gateway...")

    cmd = [
        "openclaw", "onboard", "--non-interactive",
        "--mode", "local",
        "--auth-choice", "openai-api-key",
        "--openai-api-key", openai_key,
        "--secret-input-mode", "plaintext",
        "--gateway-port", str(OPENCLAW_GATEWAY_PORT),
        "--gateway-auth", "token",
        "--gateway-token", token,
        "--skip-skills",
        "--skip-health",
        "--accept-risk",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)  # noqa: S603
        if result.returncode == 0:
            _patch_openclaw_model(model)
            print(f"Hosaka: OpenClaw configured — model: openai/{model}")
        else:
            err = (result.stderr or result.stdout or "").strip()[:300]
            print(f"Hosaka: OpenClaw onboard warning: {err}")
    except subprocess.TimeoutExpired:
        print("Hosaka: OpenClaw onboard timed out — gateway will start without config.")
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka: OpenClaw onboard error: {exc}")


def start_openclaw_gateway() -> subprocess.Popen | None:  # type: ignore[type-arg]
    """Start the OpenClaw gateway in the background if available."""
    if not _openclaw_installed():
        return None

    if is_port_in_use("127.0.0.1", OPENCLAW_GATEWAY_PORT):
        return None  # already running

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        _onboard_openclaw()
        # If onboard failed or no key, still try to start
        if not config_path.exists():
            return None

    try:
        proc = subprocess.Popen(  # noqa: S603
            ["openclaw", "gateway"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)  # brief pause for gateway to bind
        return proc
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka: could not start OpenClaw gateway: {exc}")
        return None


# ── main entry ────────────────────────────────────────────────────────────────

def launch() -> None:
    orchestrator = build_default_orchestrator()
    orchestrator.update_runtime_network()
    web_url = f"http://{orchestrator.state.local_ip}:{WEB_PORT}"
    web_process = start_web_server()

    # Start OpenClaw gateway as a background process (non-blocking)
    start_openclaw_gateway()

    if BOOT_MODE == "headless" or not sys.stdin.isatty():
        if BOOT_MODE != "headless":
            print("Hosaka warning: no TTY detected; falling back to headless web setup mode.")
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
