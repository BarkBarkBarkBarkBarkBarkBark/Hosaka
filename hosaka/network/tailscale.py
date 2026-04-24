"""Tailscale CLI wrapper — used by the Nodes panel to onboard users onto
their own tailnet and to discover other Hosaka devices.

All functions degrade gracefully when the `tailscale` binary is not on
PATH (returns `{"installed": False, ...}` instead of raising), so the
Nodes panel can render the "install tailscale" onboarding card.

We intentionally shell out to the CLI instead of using the official Go
client lib — Hosaka runs on Raspberry Pi OS, Debian, macOS (via Docker),
and the CLI is the one interface that's stable across all of them.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import socket
import subprocess
from typing import Any, AsyncIterator

# Regex for the login URL `tailscale up` prints to stderr when a browser
# flow is required. Matches both the legacy `login.tailscale.com/a/<code>`
# and the newer `controlplane.tailscale.com/a/<code>` hosts.
_LOGIN_URL_RE = re.compile(r"https://(?:login|controlplane)\.tailscale\.com/\S+")


def is_installed() -> bool:
    """True if the `tailscale` binary is on PATH."""
    return shutil.which("tailscale") is not None


def status_json() -> dict[str, Any]:
    """Return `tailscale status --json` as a dict, or an empty shape if the
    CLI is missing or not logged in.

    The returned dict always has the keys `installed`, `connected`, and
    (when connected) `Self` + `Peer`. The frontend relies on this shape.
    """
    if not is_installed():
        return {"installed": False, "connected": False}

    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"installed": True, "connected": False}

    if result.returncode != 0 or not result.stdout.strip():
        return {"installed": True, "connected": False}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"installed": True, "connected": False}

    data["installed"] = True
    # `BackendState` is `Running` when tailscaled is connected to the
    # control plane with a logged-in user. Everything else means we need
    # onboarding.
    data["connected"] = data.get("BackendState") == "Running"
    return data


def self_info() -> dict[str, Any]:
    """Short summary of the local node (hostname, ip, magic DNS name)."""
    s = status_json()
    if not s.get("connected"):
        return {"installed": s.get("installed", False), "connected": False}

    me = s.get("Self") or {}
    ips = me.get("TailscaleIPs") or []
    return {
        "installed": True,
        "connected": True,
        "hostname": me.get("HostName") or socket.gethostname(),
        "dns_name": me.get("DNSName", "").rstrip("."),
        "ip": ips[0] if ips else None,
        "os": me.get("OS"),
    }


def peers() -> list[dict[str, Any]]:
    """Return the list of tailnet peers as light dicts suitable for the
    Nodes panel — NOT the raw tailscale JSON (which is enormous)."""
    s = status_json()
    if not s.get("connected"):
        return []

    out: list[dict[str, Any]] = []
    for peer in (s.get("Peer") or {}).values():
        ips = peer.get("TailscaleIPs") or []
        if not ips:
            continue
        out.append({
            "hostname": peer.get("HostName", ""),
            "dns_name": peer.get("DNSName", "").rstrip("."),
            "ip": ips[0],
            "online": bool(peer.get("Online")),
            "os": peer.get("OS"),
            "last_seen": peer.get("LastSeen"),
        })
    # Stable ordering: online first, then hostname alphabetically.
    out.sort(key=lambda p: (not p["online"], p["hostname"].lower()))
    return out


async def up_interactive(hostname: str | None = None) -> AsyncIterator[dict[str, str]]:
    """Run `tailscale up` in the background, yielding status events for SSE.

    Emits:
      {"event": "line", "data": "<raw output line>"}
      {"event": "login_url", "data": "<https://...>"}   # when we see it
      {"event": "done", "data": "ok" | "error:<msg>"}

    Callers are responsible for formatting these as SSE frames.
    """
    if not is_installed():
        yield {"event": "done", "data": "error:tailscale-not-installed"}
        return

    args = ["tailscale", "up", "--ssh"]
    if hostname:
        args += [f"--hostname={hostname}"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        yield {"event": "done", "data": f"error:{exc}"}
        return

    assert proc.stdout is not None
    url_seen = False
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if not text:
                continue
            yield {"event": "line", "data": text}
            if not url_seen:
                match = _LOGIN_URL_RE.search(text)
                if match:
                    url_seen = True
                    yield {"event": "login_url", "data": match.group(0)}
    finally:
        rc = await proc.wait()
        if rc == 0:
            yield {"event": "done", "data": "ok"}
        else:
            yield {"event": "done", "data": f"error:exit-{rc}"}


def logout() -> tuple[bool, str]:
    """Run `tailscale logout`. Returns (ok, message)."""
    if not is_installed():
        return False, "tailscale-not-installed"
    try:
        result = subprocess.run(
            ["tailscale", "logout"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "unknown").strip()
    return True, "ok"
