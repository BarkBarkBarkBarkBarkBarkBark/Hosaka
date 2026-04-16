"""OpenClaw adapter — real OpenClaw gateway (port 18789) + diagnostics.

The real OpenClaw product (https://openclaw.ai) runs as a local Node.js gateway
that gives the agent exec, fs, web_search, browser, and image tools on top of
whichever model provider is configured (OpenAI, Anthropic, etc.).

This module:
  - Probes whether the OpenClaw gateway is up on port 18789
  - Provides doctor() diagnostics
  - Wraps run_install_script() for /openclaw install

Chat routing via the gateway WebSocket protocol is handled by
openclaw_gateway.py (sessions.send / chat.send).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

OPENCLAW_GATEWAY_PORT = int(
    os.getenv("OPENCLAW_GATEWAY_PORT")
    or os.getenv("PICOCLAW_GATEWAY_PORT")
    or "18790"
)
OPENCLAW_GATEWAY_HOST = os.getenv("OPENCLAW_GATEWAY_HOST", "127.0.0.1")

APP_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = APP_ROOT / "scripts" / "install_openclaw.sh"


# ── availability ──────────────────────────────────────────────────────────────

def is_cli_installed() -> bool:
    """Return True if the openclaw CLI binary is on PATH."""
    return bool(shutil.which("openclaw"))


def is_gateway_up() -> bool:
    """Return True if the OpenClaw gateway is accepting connections."""
    try:
        with socket.create_connection(
            (OPENCLAW_GATEWAY_HOST, OPENCLAW_GATEWAY_PORT), timeout=1
        ):
            return True
    except OSError:
        return False


def is_available() -> bool:
    """Return True if the OpenClaw gateway is reachable (used by router)."""
    return is_gateway_up()


# ── runtime info ──────────────────────────────────────────────────────────────

def cli_version() -> str | None:
    """Return the openclaw CLI version string, or None."""
    if not is_cli_installed():
        return None
    try:
        result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (result.stdout or result.stderr).strip() or None
    except Exception:  # noqa: BLE001
        return None


def gateway_status_text() -> str | None:
    """Return the output of `openclaw gateway status`, or None on failure."""
    if not is_cli_installed():
        return None
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (result.stdout or result.stderr).strip() or None
    except Exception:  # noqa: BLE001
        return None


def configured_model() -> str:
    """Return the model configured in openclaw.json, or env fallback."""
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            import json
            config = json.loads(config_path.read_text())
            primary = (
                config
                .get("agents", {})
                .get("defaults", {})
                .get("model", {})
                .get("primary", "")
            )
            if primary:
                return primary
        except Exception:  # noqa: BLE001
            pass
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return f"openai/{model}"


# ── doctor / diagnostics ──────────────────────────────────────────────────────

def doctor() -> dict[str, object]:
    """Run a full diagnostic and return a status dict."""
    cli = is_cli_installed()
    version = cli_version() if cli else None
    gateway = is_gateway_up()
    config_path = Path.home() / ".openclaw" / "openclaw.json"

    return {
        "cli_installed": cli,
        "cli_version": version,
        "gateway_up": gateway,
        "gateway_port": OPENCLAW_GATEWAY_PORT,
        "configured_model": configured_model(),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "config_exists": config_path.exists(),
    }


# ── install ───────────────────────────────────────────────────────────────────

def run_install_script() -> tuple[bool, str]:
    """Run scripts/install_openclaw.sh and return (success, output)."""
    if not INSTALL_SCRIPT.is_file():
        return False, f"Install script not found: {INSTALL_SCRIPT}"
    try:
        result = subprocess.run(
            ["bash", str(INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Install timed out after 5 minutes."
    except Exception as exc:  # noqa: BLE001
        return False, f"Install failed: {exc}"
