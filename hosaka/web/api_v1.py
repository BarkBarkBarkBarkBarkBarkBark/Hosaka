"""Hosaka v1 API — single source of truth for remote clients.

This is the public, versioned surface that `hosakactl` (the Mac client),
the `/device` page in the kiosk, and any third-party tool talk to.

Design rules (kept deliberately small for a Pi 3B + maintainability):

* Stdlib + `nmcli` + `systemctl` only — no extra Python deps.
* Every endpoint returns a typed Pydantic model so OpenAPI is rich enough
  to drive auto-generated docs (mkdocs-material plugin reads /openapi.json).
* Auth: `Authorization: Bearer <token>` where the token lives at
  `/etc/hosaka/api-token` (or `$HOSAKA_API_TOKEN`). Loopback (127.0.0.1) is
  always allowed without a token so the local kiosk SPA / TTY dashboard work.
* Side-effects are funneled through the `hosaka` CLI on the box, not
  reimplemented here. That keeps one source of truth for "what does
  switching modes mean".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

import httpx
from hosaka.ops.updater import APP_ROOT, UPDATE_SCRIPT
from hosaka.web import channel_store as channel_store
from hosaka.web import inbox_store as inbox_store
from hosaka.web.beacon_registry import get_registry
from hosaka.web.sync_ws import relay_inbox_event
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# ── config ────────────────────────────────────────────────────────────────────

TOKEN_FILE = Path(os.getenv("HOSAKA_API_TOKEN_FILE", "/etc/hosaka/api-token"))
RUNTIME_MODE_FILE = Path(os.getenv("HOSAKA_MODE_FILE", "/var/lib/hosaka/mode"))
BOOT_MARKER = Path("/boot/firmware/hosaka-build-mode")
HOSAKA_CLI = os.getenv("HOSAKA_CLI", "/usr/local/bin/hosaka")

KEY_SERVICES = (
    "hosaka-webserver.service",
    "picoclaw-gateway.service",
    "hosaka-mode.service",
    "hosaka-device-dashboard.service",
    "ssh.service",
)

# ── auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def _load_token() -> Optional[str]:
    env = os.getenv("HOSAKA_API_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_FILE.exists():
        try:
            tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
            return tok or None
        except OSError:
            return None
    return None


def _is_loopback(req: Request) -> bool:
    client = req.client
    if not client:
        return False
    host = client.host or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def require_auth(
    req: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """Allow if loopback, OR bearer matches stored token, OR no token configured."""
    if _is_loopback(req):
        return
    expected = _load_token()
    if not expected:
        # No token configured → API is read-only-from-LAN by default. We still
        # block writes via per-endpoint dependency `require_write` below.
        return
    if creds and creds.scheme.lower() == "bearer" and creds.credentials == expected:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid bearer token")


def require_write(
    req: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """Stricter: writes require either loopback or a real bearer match."""
    if _is_loopback(req):
        return
    expected = _load_token()
    if not expected:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "no API token configured on this Pi — generate one at /etc/hosaka/api-token",
        )
    if creds and creds.scheme.lower() == "bearer" and creds.credentials == expected:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid bearer token")


# ── shell helpers ─────────────────────────────────────────────────────────────


def _run(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout: {' '.join(cmd)}"


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ── models ────────────────────────────────────────────────────────────────────

ModeName = Literal["console", "device"]


class HealthOut(BaseModel):
    web: str = "ok"
    mode: ModeName
    hostname: str
    uptime_seconds: int
    timestamp: int


class MemInfo(BaseModel):
    total_mb: int
    used_mb: int
    available_mb: int
    swap_used_mb: int


class NetInfo(BaseModel):
    ip: Optional[str] = None
    iface: Optional[str] = None
    ssid: Optional[str] = None
    mac: Optional[str] = None
    tailscale_ip: Optional[str] = None


class ServiceInfo(BaseModel):
    name: str
    active: bool
    sub: str
    enabled: bool


class SystemInfoOut(BaseModel):
    mode: ModeName
    boot_marker: bool
    hostname: str
    uptime_seconds: int
    cpu_temp_c: Optional[float] = None
    mem: MemInfo
    net: NetInfo
    services: list[ServiceInfo]
    urls: dict[str, str]
    listening_ports: list[int]


class ModeOut(BaseModel):
    mode: ModeName
    boot_marker: bool


class ModeIn(BaseModel):
    mode: ModeName
    persist: bool = False


class WifiNetwork(BaseModel):
    ssid: str
    saved: bool = False
    in_range: bool = False
    signal: Optional[int] = Field(None, description="0–100 from nmcli")
    security: Optional[str] = None
    active: bool = False


class WifiList(BaseModel):
    networks: list[WifiNetwork]


class WifiAdd(BaseModel):
    ssid: str = Field(..., min_length=1, max_length=64)
    psk: Optional[str] = Field(None, min_length=8, max_length=128, description="omit for open networks")
    hidden: bool = False


class ActionResult(BaseModel):
    ok: bool
    message: str = ""


class AudioVolume(BaseModel):
    level: int = Field(..., ge=0, le=100, description="0-100 system output volume")
    muted: bool = False
    backend: str = Field(..., description="pactl | osascript | unsupported")


class AudioVolumeSet(BaseModel):
    level: Optional[int] = Field(None, ge=0, le=100)
    muted: Optional[bool] = None


class ChannelMessageOut(BaseModel):
    id: str
    at: int
    author: str
    text: str
    tags: list[str]
    parent_id: Optional[str] = None
    prev_hash: str
    hash: str


class ChannelFeedOut(BaseModel):
    chain_head: str
    chain_ok: bool
    messages: list[ChannelMessageOut]


class ChannelPostIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    author: str = Field("operator", max_length=64)
    parent_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


InboxSeverity = Literal["info", "success", "warn", "error"]


class InboxEventOut(BaseModel):
    id: str
    at: int
    kind: Literal["notify", "ack"]
    author: str
    node_id: str
    topic: str
    severity: InboxSeverity
    title: str
    body: str
    target: str
    tags: list[str]
    event_ref: Optional[str] = None
    prev_hash: str
    hash: str
    acked: bool = False
    ack_at: Optional[int] = None
    ack_author: Optional[str] = None


class InboxFeedOut(BaseModel):
    chain_head: str
    chain_ok: bool
    node_id: str
    notifications: list[InboxEventOut]


class InboxPostIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    body: str = Field("", max_length=4000)
    author: str = Field("operator", max_length=64)
    topic: str = Field("general", max_length=64)
    severity: InboxSeverity = "info"
    target: str = Field("broadcast", max_length=128)
    tags: list[str] = Field(default_factory=list)


class InboxAckIn(BaseModel):
    author: str = Field("operator", max_length=64)


class HttpHeaderIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., max_length=2000)


class HttpGetIn(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    headers: list[HttpHeaderIn] = Field(default_factory=list)


class HttpPostIn(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    headers: list[HttpHeaderIn] = Field(default_factory=list)
    body: Optional[str] = Field(None, max_length=200000)
    json_body: Optional[dict[str, Any]] = None


class HttpResponseOut(BaseModel):
    url: str
    status: int
    content_type: str
    headers: dict[str, str]
    body: str
    truncated: bool = False


# ── system info collectors ────────────────────────────────────────────────────


def _read_mode() -> ModeName:
    raw = _read_file(str(RUNTIME_MODE_FILE))
    if raw == "device" or raw == "build":
        return "device"
    if raw == "console" or raw == "kiosk":
        return "console"
    return "device" if BOOT_MARKER.exists() else "console"


def _local_node_id() -> str:
    beacon = get_registry().local_beacon()
    return str(beacon.get("node_id") or "unknown")


HTTP_ALLOWED_HOSTS = [h.strip().lower() for h in os.getenv("HOSAKA_HTTP_ALLOWED_HOSTS", "").split(",") if h.strip()]
HTTP_TIMEOUT = float(os.getenv("HOSAKA_HTTP_TIMEOUT", "15"))
HTTP_MAX_BODY = int(os.getenv("HOSAKA_HTTP_MAX_BODY", "65536"))
HTTP_ALLOW_PRIVATE = os.getenv("HOSAKA_HTTP_ALLOW_PRIVATE", "").strip().lower() in {"1", "true", "yes", "on"}


def _host_allowed(host: str) -> bool:
    if not HTTP_ALLOWED_HOSTS:
        return False
    host = host.lower().rstrip(".")
    for allowed in HTTP_ALLOWED_HOSTS:
        if allowed.startswith("."):
            if host.endswith(allowed):
                return True
        elif host == allowed:
            return True
    return False


def _assert_http_url_allowed(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "url must be http or https")
    if not parsed.hostname:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "url missing hostname")

    host = parsed.hostname.lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None and not HTTP_ALLOW_PRIVATE:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "private or loopback addresses are blocked")

    if not _host_allowed(host):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "host not allowed; set HOSAKA_HTTP_ALLOWED_HOSTS to allow it",
        )

    return parsed.geturl()


def _headers_to_dict(headers: list[HttpHeaderIn]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in headers:
        name = item.name.strip()
        if not name:
            continue
        out[name] = item.value
    return out


def _truncate_body(text: str) -> tuple[str, bool]:
    if len(text) <= HTTP_MAX_BODY:
        return text, False
    return text[:HTTP_MAX_BODY], True


async def _perform_http_request(method: str, url: str, *, headers: dict[str, str], body: str | None = None, json_body: dict[str, Any] | None = None) -> HttpResponseOut:
    allowed_url = _assert_http_url_allowed(url)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.request(method, allowed_url, headers=headers, content=body, json=json_body)
    raw_body = response.text
    body_text, truncated = _truncate_body(raw_body)
    safe_headers = {k: v for k, v in response.headers.items() if k.lower() in {
        "content-type", "content-length", "cache-control", "etag", "last-modified", "location"
    }}
    return HttpResponseOut(
        url=str(response.request.url),
        status=response.status_code,
        content_type=response.headers.get("content-type", ""),
        headers=safe_headers,
        body=body_text,
        truncated=truncated,
    )


def _uptime_seconds() -> int:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except OSError:
        return 0


def _cpu_temp() -> Optional[float]:
    raw = _read_file("/sys/class/thermal/thermal_zone0/temp")
    if not raw:
        return None
    try:
        return round(int(raw) / 1000.0, 1)
    except ValueError:
        return None


def _mem() -> MemInfo:
    info: dict[str, int] = {}
    for line in _read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        v = v.strip().split()[0]
        try:
            info[k] = int(v)  # KiB
        except ValueError:
            pass
    total = info.get("MemTotal", 0) // 1024
    avail = info.get("MemAvailable", 0) // 1024
    swap_total = info.get("SwapTotal", 0) // 1024
    swap_free = info.get("SwapFree", 0) // 1024
    return MemInfo(
        total_mb=total,
        used_mb=max(total - avail, 0),
        available_mb=avail,
        swap_used_mb=max(swap_total - swap_free, 0),
    )


def _net() -> NetInfo:
    iface = ip = mac = ssid = ts = None
    rc, out, _ = _run(["ip", "-4", "route", "show", "default"])
    if rc == 0 and out.strip():
        parts = out.split()
        if "dev" in parts:
            iface = parts[parts.index("dev") + 1]
    if iface:
        rc, out, _ = _run(["ip", "-4", "-o", "addr", "show", "dev", iface])
        if rc == 0:
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
            if m:
                ip = m.group(1)
        mac_path = f"/sys/class/net/{iface}/address"
        if Path(mac_path).exists():
            mac = _read_file(mac_path) or None
    if shutil.which("iwgetid"):
        rc, out, _ = _run(["iwgetid", "-r"])
        if rc == 0 and out.strip():
            ssid = out.strip()
    if shutil.which("tailscale"):
        rc, out, _ = _run(["tailscale", "ip", "-4"], timeout=3)
        if rc == 0 and out.strip():
            ts = out.strip().splitlines()[0]
    return NetInfo(ip=ip, iface=iface, ssid=ssid, mac=mac, tailscale_ip=ts)


def _services() -> list[ServiceInfo]:
    out: list[ServiceInfo] = []
    for name in KEY_SERVICES:
        rc1, a, _ = _run(["systemctl", "is-active", name], timeout=4)
        rc2, e, _ = _run(["systemctl", "is-enabled", name], timeout=4)
        rc3, s, _ = _run(["systemctl", "show", name, "-p", "SubState", "--value"], timeout=4)
        out.append(
            ServiceInfo(
                name=name,
                active=a.strip() == "active",
                sub=(s.strip() or "unknown"),
                enabled=e.strip() in {"enabled", "static", "alias"},
            )
        )
    return out


def _listening_ports() -> list[int]:
    rc, out, _ = _run(["ss", "-tlnH"], timeout=4)
    ports: set[int] = set()
    if rc == 0:
        for line in out.splitlines():
            cols = line.split()
            if len(cols) < 4:
                continue
            addr = cols[3]
            m = re.search(r":(\d+)$", addr)
            if m:
                p = int(m.group(1))
                if 0 < p < 65535:
                    ports.add(p)
    return sorted(ports)


def _urls(net: NetInfo) -> dict[str, str]:
    host = net.ip or net.tailscale_ip or "127.0.0.1"
    base = f"http://{host}:8421"
    return {
        "ui": base,
        "device": f"{base}/device",
        "setup": f"{base}/setup/",
        "api": f"{base}/api/v1",
        "openapi": f"{base}/openapi.json",
    }


# ── router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Liveness ping",
    dependencies=[Depends(require_auth)],
)
def v1_health() -> HealthOut:
    return HealthOut(
        mode=_read_mode(),
        hostname=socket.gethostname(),
        uptime_seconds=_uptime_seconds(),
        timestamp=int(time.time()),
    )


@router.get(
    "/system/info",
    response_model=SystemInfoOut,
    summary="One-shot snapshot of everything device-mode shows",
    dependencies=[Depends(require_auth)],
)
def v1_system_info() -> SystemInfoOut:
    net = _net()
    return SystemInfoOut(
        mode=_read_mode(),
        boot_marker=BOOT_MARKER.exists(),
        hostname=socket.gethostname(),
        uptime_seconds=_uptime_seconds(),
        cpu_temp_c=_cpu_temp(),
        mem=_mem(),
        net=net,
        services=_services(),
        urls=_urls(net),
        listening_ports=_listening_ports(),
    )


@router.get(
    "/mode",
    response_model=ModeOut,
    summary="Get current operating mode",
    dependencies=[Depends(require_auth)],
)
def v1_mode_get() -> ModeOut:
    return ModeOut(mode=_read_mode(), boot_marker=BOOT_MARKER.exists())


@router.post(
    "/mode",
    response_model=ModeOut,
    summary="Switch operating mode (console|device)",
    dependencies=[Depends(require_write)],
)
def v1_mode_set(body: ModeIn) -> ModeOut:
    if not Path(HOSAKA_CLI).exists():
        raise HTTPException(500, f"{HOSAKA_CLI} not installed")
    args = [HOSAKA_CLI, "mode", body.mode]
    if body.persist:
        args.append("--persist")
    # Run detached so we don't kill ourselves if the mode switch restarts the
    # webserver; the caller polls /mode to confirm. 4 s should be enough for
    # the CLI to write the runtime mode file before we read it back.
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    return ModeOut(mode=_read_mode(), boot_marker=BOOT_MARKER.exists())


# ── wifi (NetworkManager) ─────────────────────────────────────────────────────


def _nmcli(*args: str, timeout: int = 12) -> tuple[int, str, str]:
    return _run(["nmcli", "-t", "-e", "no", *args], timeout=timeout)


@router.get(
    "/wifi/networks",
    response_model=WifiList,
    summary="Saved + visible wifi networks (nmcli)",
    dependencies=[Depends(require_auth)],
)
def v1_wifi_list() -> WifiList:
    if not shutil.which("nmcli"):
        raise HTTPException(501, "nmcli not installed")
    saved: dict[str, dict[str, Any]] = {}
    rc, out, _ = _nmcli("-f", "NAME,TYPE", "connection", "show")
    if rc == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "802-11-wireless":
                saved[parts[0]] = {"saved": True}
    visible: dict[str, dict[str, Any]] = {}
    rc, out, _ = _nmcli(
        "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no"
    )
    if rc == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            in_use, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
            if not ssid:
                continue
            try:
                sig = int(signal)
            except ValueError:
                sig = None
            visible[ssid] = {
                "in_range": True,
                "signal": sig,
                "security": security or None,
                "active": in_use.strip() == "*",
            }
    keys = set(saved) | set(visible)
    nets = [
        WifiNetwork(
            ssid=k,
            saved=k in saved,
            in_range=visible.get(k, {}).get("in_range", False),
            signal=visible.get(k, {}).get("signal"),
            security=visible.get(k, {}).get("security"),
            active=visible.get(k, {}).get("active", False),
        )
        for k in sorted(keys, key=lambda s: (-(visible.get(s, {}).get("signal") or 0), s))
    ]
    return WifiList(networks=nets)


@router.post(
    "/wifi/networks",
    response_model=ActionResult,
    summary="Add or join a wifi network",
    dependencies=[Depends(require_write)],
)
def v1_wifi_add(body: WifiAdd) -> ActionResult:
    if not shutil.which("nmcli"):
        raise HTTPException(501, "nmcli not installed")
    args = ["device", "wifi", "connect", body.ssid]
    if body.psk:
        args += ["password", body.psk]
    if body.hidden:
        args += ["hidden", "yes"]
    rc, out, err = _run(["nmcli", *args], timeout=45)
    if rc != 0:
        return ActionResult(ok=False, message=(err or out).strip()[:400])
    return ActionResult(ok=True, message=out.strip()[:400] or f"connected to {body.ssid}")


@router.delete(
    "/wifi/networks/{ssid}",
    response_model=ActionResult,
    summary="Forget a saved wifi network",
    dependencies=[Depends(require_write)],
)
def v1_wifi_forget(ssid: str) -> ActionResult:
    if not shutil.which("nmcli"):
        raise HTTPException(501, "nmcli not installed")
    rc, out, err = _run(["nmcli", "connection", "delete", ssid], timeout=10)
    if rc != 0:
        return ActionResult(ok=False, message=(err or out).strip()[:400])
    return ActionResult(ok=True, message=f"forgot {ssid}")


# ── audio (system output volume) ──────────────────────────────────────────────
#
# Two backends, picked in order:
#   pactl     — Linux/PulseAudio/PipeWire (kiosk, Pi, most desktop linuxes)
#   osascript — macOS (`output volume of (get volume settings)`)
# When neither is available we return 501 so the UI can degrade gracefully.


def _audio_backend() -> str:
    if shutil.which("pactl"):
        return "pactl"
    if shutil.which("osascript"):
        return "osascript"
    return "unsupported"


def _audio_get() -> AudioVolume:
    be = _audio_backend()
    if be == "pactl":
        rc, out, _ = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], timeout=4)
        level = 0
        if rc == 0:
            m = re.search(r"(\d+)%", out)
            if m:
                level = max(0, min(100, int(m.group(1))))
        rc, out, _ = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"], timeout=4)
        muted = "yes" in (out or "").lower()
        return AudioVolume(level=level, muted=muted, backend=be)
    if be == "osascript":
        rc, out, _ = _run(
            ["osascript", "-e", "output volume of (get volume settings)"], timeout=4
        )
        try:
            level = int((out or "0").strip())
        except ValueError:
            level = 0
        rc, out, _ = _run(
            ["osascript", "-e", "output muted of (get volume settings)"], timeout=4
        )
        muted = (out or "").strip().lower() == "true"
        return AudioVolume(level=max(0, min(100, level)), muted=muted, backend=be)
    raise HTTPException(501, "no audio backend (need pactl or osascript)")


@router.get(
    "/audio/volume",
    response_model=AudioVolume,
    summary="Current system output volume + mute state",
    dependencies=[Depends(require_auth)],
)
def v1_audio_get() -> AudioVolume:
    return _audio_get()


@router.put(
    "/audio/volume",
    response_model=AudioVolume,
    summary="Set system output volume and/or mute",
    dependencies=[Depends(require_write)],
)
def v1_audio_set(body: AudioVolumeSet) -> AudioVolume:
    be = _audio_backend()
    if be == "unsupported":
        raise HTTPException(501, "no audio backend (need pactl or osascript)")
    if body.level is None and body.muted is None:
        raise HTTPException(400, "provide level and/or muted")
    if be == "pactl":
        if body.level is not None:
            _run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{body.level}%"],
                timeout=4,
            )
        if body.muted is not None:
            _run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if body.muted else "0"],
                timeout=4,
            )
    elif be == "osascript":
        if body.level is not None:
            _run(["osascript", "-e", f"set volume output volume {body.level}"], timeout=4)
        if body.muted is not None:
            flag = "true" if body.muted else "false"
            _run(["osascript", "-e", f"set volume output muted {flag}"], timeout=4)
    return _audio_get()


# ── services ──────────────────────────────────────────────────────────────────


@router.get(
    "/services",
    response_model=list[ServiceInfo],
    summary="Status of the Hosaka systemd units",
    dependencies=[Depends(require_auth)],
)
def v1_services() -> list[ServiceInfo]:
    return _services()


@router.post(
    "/services/{name}/restart",
    response_model=ActionResult,
    summary="Restart one of the known Hosaka units",
    dependencies=[Depends(require_write)],
)
def v1_service_restart(name: str) -> ActionResult:
    if name not in KEY_SERVICES:
        raise HTTPException(404, f"unknown service: {name}")
    rc, _, err = _run(["sudo", "-n", "systemctl", "restart", name], timeout=15)
    if rc != 0:
        return ActionResult(ok=False, message=err.strip()[:400] or f"rc={rc}")
    return ActionResult(ok=True, message=f"restarted {name}")


@router.post(
    "/system/update",
    response_model=ActionResult,
    summary="Run the Hosaka git pull / reinstall script in the background",
    dependencies=[Depends(require_write)],
)
def v1_system_update() -> ActionResult:
    """Same flow as the Python TUI `/update` — fires `scripts/update_hosaka.sh`.

    Runs detached so the HTTP handler returns before services restart.
    """
    if not UPDATE_SCRIPT.exists():
        return ActionResult(
            ok=False,
            message=f"update script not found: {UPDATE_SCRIPT}",
        )
    try:
        subprocess.Popen(
            [str(UPDATE_SCRIPT)],
            cwd=str(APP_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return ActionResult(ok=False, message=str(exc)[:400])
    return ActionResult(
        ok=True,
        message="update started — services may restart; check ssh or journalctl",
    )


# ── public channel (hash-chained log, on-disk JSON) ───────────────────────────


@router.get(
    "/channel/messages",
    response_model=ChannelFeedOut,
    summary="Public channel messages (SHA-256 chain, persisted on the appliance SD card)",
    dependencies=[Depends(require_auth)],
)
def v1_channel_messages(tag: Optional[str] = None) -> ChannelFeedOut:
    raw, head = channel_store.list_messages()
    msgs = [m for m in raw if isinstance(m, dict)]
    if tag:
        t = tag.strip().lstrip("#").lower()
        msgs = [m for m in msgs if t in (m.get("tags") or [])]
    ok = channel_store.verify_chain()
    out: list[ChannelMessageOut] = []
    for m in msgs:
        try:
            out.append(
                ChannelMessageOut(
                    id=str(m["id"]),
                    at=int(m["at"]),
                    author=str(m.get("author", "operator")),
                    text=str(m.get("text", "")),
                    tags=list(m.get("tags") or []),
                    parent_id=str(m["parent_id"]) if m.get("parent_id") else None,
                    prev_hash=str(m.get("prev_hash", "")),
                    hash=str(m.get("hash", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return ChannelFeedOut(chain_head=head, chain_ok=ok, messages=out)


@router.post(
    "/channel/messages",
    response_model=ChannelMessageOut,
    summary="Append a message (extends the hash chain)",
    dependencies=[Depends(require_write)],
)
def v1_channel_post(body: ChannelPostIn) -> ChannelMessageOut:
    try:
        row = channel_store.append_message(
            body.text,
            author=body.author,
            parent_id=body.parent_id,
            extra_tags=body.tags,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ChannelMessageOut(
        id=str(row["id"]),
        at=int(row["at"]),
        author=str(row.get("author", "operator")),
        text=str(row.get("text", "")),
        tags=list(row.get("tags") or []),
        parent_id=str(row["parent_id"]) if row.get("parent_id") else None,
        prev_hash=str(row.get("prev_hash", "")),
        hash=str(row["hash"]),
    )


# ── inbox / notifications (append-only gossipable event log) ─────────────────


@router.get(
    "/inbox/events",
    response_model=InboxFeedOut,
    summary="Append-only inbox / notification feed",
    dependencies=[Depends(require_auth)],
)
def v1_inbox_events(limit: int = 200, topic: Optional[str] = None) -> InboxFeedOut:
    rows, head, ok = inbox_store.list_notifications(limit=max(1, min(limit, 500)))
    if topic:
        wanted = topic.strip().lower()
        rows = [row for row in rows if str(row.get("topic") or "").lower() == wanted]
    out: list[InboxEventOut] = []
    for row in rows:
        try:
            out.append(InboxEventOut(
                id=str(row["id"]),
                at=int(row["at"]),
                kind=str(row.get("kind") or "notify"),
                author=str(row.get("author") or "operator"),
                node_id=str(row.get("node_id") or "unknown"),
                topic=str(row.get("topic") or "general"),
                severity=str(row.get("severity") or "info"),
                title=str(row.get("title") or ""),
                body=str(row.get("body") or ""),
                target=str(row.get("target") or "broadcast"),
                tags=list(row.get("tags") or []),
                event_ref=str(row["event_ref"]) if row.get("event_ref") else None,
                prev_hash=str(row.get("prev_hash") or ""),
                hash=str(row.get("hash") or ""),
                acked=bool(row.get("acked", False)),
                ack_at=int(row["ack_at"]) if row.get("ack_at") else None,
                ack_author=str(row["ack_author"]) if row.get("ack_author") else None,
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return InboxFeedOut(chain_head=head, chain_ok=ok, node_id=_local_node_id(), notifications=out)


@router.post(
    "/inbox/events",
    response_model=InboxEventOut,
    summary="Append a notification event",
    dependencies=[Depends(require_write)],
)
def v1_inbox_post(body: InboxPostIn) -> InboxEventOut:
    try:
        row = inbox_store.append_notification(
            body.title,
            body.body,
            author=body.author,
            node_id=_local_node_id(),
            topic=body.topic,
            severity=body.severity,
            target=body.target,
            tags=body.tags,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    relay_inbox_event(row)
    return InboxEventOut(
        id=str(row["id"]),
        at=int(row["at"]),
        kind=str(row["kind"]),
        author=str(row.get("author") or "operator"),
        node_id=str(row.get("node_id") or "unknown"),
        topic=str(row.get("topic") or "general"),
        severity=str(row.get("severity") or "info"),
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        target=str(row.get("target") or "broadcast"),
        tags=list(row.get("tags") or []),
        event_ref=str(row["event_ref"]) if row.get("event_ref") else None,
        prev_hash=str(row.get("prev_hash") or ""),
        hash=str(row.get("hash") or ""),
    )


@router.post(
    "/inbox/events/{event_id}/ack",
    response_model=InboxEventOut,
    summary="Append an acknowledgement event for a notification",
    dependencies=[Depends(require_write)],
)
def v1_inbox_ack(event_id: str, body: Optional[InboxAckIn] = None) -> InboxEventOut:
    try:
        row = inbox_store.append_ack(
            event_id,
            author=(body.author if body else "operator"),
            node_id=_local_node_id(),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    relay_inbox_event(row)
    return InboxEventOut(
        id=str(row["id"]),
        at=int(row["at"]),
        kind=str(row["kind"]),
        author=str(row.get("author") or "operator"),
        node_id=str(row.get("node_id") or "unknown"),
        topic=str(row.get("topic") or "general"),
        severity=str(row.get("severity") or "success"),
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        target=str(row.get("target") or "broadcast"),
        tags=list(row.get("tags") or []),
        event_ref=str(row["event_ref"]) if row.get("event_ref") else None,
        prev_hash=str(row.get("prev_hash") or ""),
        hash=str(row.get("hash") or ""),
    )


@router.post(
    "/http/get",
    response_model=HttpResponseOut,
    summary="Perform an allowlisted outbound HTTP GET",
    dependencies=[Depends(require_write)],
)
async def v1_http_get(body: HttpGetIn) -> HttpResponseOut:
    return await _perform_http_request(
        "GET",
        body.url,
        headers=_headers_to_dict(body.headers),
    )


@router.post(
    "/http/post",
    response_model=HttpResponseOut,
    summary="Perform an allowlisted outbound HTTP POST",
    dependencies=[Depends(require_write)],
)
async def v1_http_post(body: HttpPostIn) -> HttpResponseOut:
    return await _perform_http_request(
        "POST",
        body.url,
        headers=_headers_to_dict(body.headers),
        body=body.body,
        json_body=body.json_body,
    )


# ── apps (HTTP fallback) ─────────────────────────────────────────────────────
#
# The Electron kiosk talks to flatpak directly via IPC. This HTTP surface is
# the browser-only fallback so the app store / shell commands can demo
# without Electron. It is mock-only by default — actually shelling out to
# `flatpak install` from a web request is too footgunny to ship turned on.
# Set HOSAKA_APPS_HTTP=real on a Linux box if you really want it.

# pyyaml is optional at import time so the rest of api_v1 still loads on
# slim envs. The apps endpoints raise 503 if it is genuinely missing.
try:  # noqa: SIM105
    import yaml as _yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]

_APPS_ROOT = Path(os.getenv("HOSAKA_APPS_ROOT", str(APP_ROOT / "hosaka-apps")))
_APPS_DIR = _APPS_ROOT / "apps"
_APPS_HTTP_MODE = os.getenv("HOSAKA_APPS_HTTP", "mock").strip().lower()


# ── flatpak shellout cache ───────────────────────────────────────────────────
# `flatpak info <id>` and `flatpak remotes` cost 150–500 ms each on a Pi 3B+;
# the status endpoints get hit on every panel mount. We keep a tiny in-process
# TTL cache (no external deps) keyed by call signature. Invalidated by
# install/launch handlers when state actually changes.
_FLATPAK_CACHE: dict[str, tuple[float, Any]] = {}
_FLATPAK_INSTALLED_TTL = 30.0
_FLATPAK_REMOTE_TTL = 300.0


def _flatpak_cache_get(key: str) -> Optional[Any]:
    hit = _FLATPAK_CACHE.get(key)
    if hit is None:
        return None
    expires_at, value = hit
    if expires_at < time.time():
        _FLATPAK_CACHE.pop(key, None)
        return None
    return value


def _flatpak_cache_set(key: str, value: Any, ttl: float) -> None:
    _FLATPAK_CACHE[key] = (time.time() + ttl, value)


def _flatpak_cache_bust(prefix: str) -> None:
    for k in list(_FLATPAK_CACHE.keys()):
        if k.startswith(prefix):
            _FLATPAK_CACHE.pop(k, None)


def _flatpak_which() -> Optional[str]:
    """Cached shutil.which('flatpak'). Process-lifetime — flatpak does not
    grow legs and walk to a different directory."""
    cached = _flatpak_cache_get("which:flatpak")
    if cached is not None:
        return cached or None
    found = shutil.which("flatpak")
    _flatpak_cache_set("which:flatpak", found or "", 24 * 3600.0)
    return found


def _flathub_remote_ready() -> bool:
    cached = _flatpak_cache_get("remote:flathub")
    if cached is not None:
        return bool(cached)
    code, out, _err = _run(["flatpak", "remotes", "--columns=name"], timeout=5)
    ready = code == 0 and any(line.strip() == "flathub" for line in out.splitlines())
    _flatpak_cache_set("remote:flathub", ready, _FLATPAK_REMOTE_TTL)
    return ready


def _flatpak_app_installed(flatpak_id: str) -> bool:
    cached = _flatpak_cache_get(f"installed:{flatpak_id}")
    if cached is not None:
        return bool(cached)
    code, _out, _err = _run(["flatpak", "info", flatpak_id], timeout=8)
    installed = code == 0
    _flatpak_cache_set(f"installed:{flatpak_id}", installed, _FLATPAK_INSTALLED_TTL)
    return installed


def _require_yaml() -> Any:
    if _yaml is None:
        raise HTTPException(503, "pyyaml is not installed in this environment")
    return _yaml


def _normalize_app_token(raw: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", raw.strip().lower())


def _read_app_manifests() -> list[dict[str, Any]]:
    if _yaml is None or not _APPS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(_APPS_DIR.iterdir()):
        if entry.suffix.lower() not in {".yaml", ".yml"}:
            continue
        # Skip macOS AppleDouble sidecars and other dotfiles that occasionally
        # leak through tar/scp transfers; their binary header is not UTF-8 and
        # would otherwise crash the whole endpoint.
        if entry.name.startswith("."):
            continue
        try:
            data = _yaml.safe_load(entry.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError, _yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        app_id = _normalize_app_token(str(data.get("id", "")))
        flatpak_id = str(data.get("flatpak_id", "")).strip()
        if not app_id or not flatpak_id:
            continue
        install = data.get("install") or {}
        launch = data.get("launch") or {}
        out.append({
            "id": app_id,
            "name": str(data.get("name", app_id)),
            "category": str(data.get("category", "other")),
            "backend": str(data.get("backend", "flatpak")),
            "flatpak_id": flatpak_id,
            "install": {"command": list(install.get("command") or [])},
            "launch": {"command": list(launch.get("command") or [])},
            "aliases": [_normalize_app_token(str(a)) for a in (data.get("aliases") or []) if str(a).strip()],
            "arches": [str(a).strip().lower() for a in (data.get("arches") or []) if str(a).strip()],
        })
    return out


def _host_flatpak_arch() -> str:
    """Host CPU arch in flatpak's vocabulary (x86_64 / aarch64 / arm / i386)."""
    raw = ""
    if hasattr(os, "uname"):
        try:
            raw = os.uname().machine.lower()  # type: ignore[attr-defined]
        except Exception:
            raw = ""
    return {
        "x86_64": "x86_64", "amd64": "x86_64",
        "aarch64": "aarch64", "arm64": "aarch64",
        "armv7l": "arm", "armv6l": "arm",
        "i386": "i386", "i686": "i386",
    }.get(raw, raw or "unknown")


def _resolve_app(raw: str) -> Optional[dict[str, Any]]:
    token = _normalize_app_token(raw)
    for m in _read_app_manifests():
        if m["id"] == token or token in m["aliases"]:
            return m
    return None


def _mock_app_response(app: dict[str, Any], verb: str) -> dict[str, Any]:
    return {
        "ok": True,
        "appId": app["id"],
        "manifestFound": True,
        "installed": verb in {"install", "status"},
        "flatpakAvailable": True,
        "flathubConfigured": True,
        "host": "mock",
        "message": f"[mock] {verb} {app['name']}.",
        "details": [f"{verb} command: " + " ".join(app[verb if verb != 'status' else 'install']['command'])],
    }


class AppStageIn(BaseModel):
    flatpak_id: str = Field(..., min_length=1, max_length=255)
    name: Optional[str] = None
    id: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None
    overwrite: bool = False


@router.get("/apps/", summary="List staged Hosaka app manifests")
def v1_apps_list() -> dict[str, Any]:
    return {"apps": _read_app_manifests()}


@router.get("/apps/capabilities", summary="Apps subsystem capability probe")
def v1_apps_capabilities() -> dict[str, Any]:
    real_mode = _APPS_HTTP_MODE == "real"
    flatpak_bin = _flatpak_which() if real_mode else None
    flathub_ready = False
    note: Optional[str] = None
    if real_mode and flatpak_bin:
        flathub_ready = _flathub_remote_ready()
        if not flathub_ready:
            note = "flatpak is installed but the `flathub` remote is not configured. run: flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
    elif real_mode:
        note = "HOSAKA_APPS_HTTP=real but the `flatpak` binary is not on PATH for the webserver process."
    else:
        note = (
            "browser fallback — install/launch are mocked. "
            "set HOSAKA_APPS_HTTP=real on a Linux host to actually shell out."
        )
    manifests = _read_app_manifests()
    # Map machine() to flatpak's arch vocabulary so the frontend can compare
    # apples to apples against AppDefinition.flatpakArches without a translation
    # layer in the UI. Anything we don't recognize is passed through as-is.
    _arch_raw = ""
    if hasattr(os, "uname"):
        try:
            _arch_raw = os.uname().machine.lower()  # type: ignore[attr-defined]
        except Exception:
            _arch_raw = ""
    _arch_map = {
        "x86_64": "x86_64", "amd64": "x86_64",
        "aarch64": "aarch64", "arm64": "aarch64",
        "armv7l": "arm", "armv6l": "arm",
        "i386": "i386", "i686": "i386",
    }
    arch = _arch_map.get(_arch_raw, _arch_raw) or "unknown"
    return {
        "host": "web",
        "platform": os.uname().sysname.lower() if hasattr(os, "uname") else "unknown",
        "arch": arch,
        "flatpakAvailable": bool(flatpak_bin),
        "flathubConfigured": flathub_ready,
        "manifestsRoot": str(_APPS_DIR),
        "manifestsFound": len(manifests),
        "mocked": not real_mode,
        "note": note,
    }


@router.get("/apps/{app_id}/status", summary="Get a Hosaka app's install status (mock or real)")
def v1_apps_status(app_id: str) -> dict[str, Any]:
    app = _resolve_app(app_id)
    if not app:
        return {"ok": False, "manifestFound": False, "message": f"app not found: {app_id}"}
    if _APPS_HTTP_MODE != "real":
        return _mock_app_response(app, "status")
    if not _flatpak_which():
        return {
            "ok": False, "appId": app["id"], "manifestFound": True,
            "installed": False, "flatpakAvailable": False, "host": "web",
            "message": "flatpak is not installed on this host.",
            "actionableCommand": "sudo apt-get install -y flatpak",
        }
    installed = _flatpak_app_installed(app["flatpak_id"])
    return {
        "ok": True, "appId": app["id"], "manifestFound": True,
        "installed": installed, "flatpakAvailable": True, "host": "web",
        "message": f"{app['name']} is {'installed' if installed else 'not installed'}.",
    }


@router.post("/apps/{app_id}/install", summary="Install a Hosaka app (mock by default)", dependencies=[Depends(require_write)])
def v1_apps_install(app_id: str) -> dict[str, Any]:
    app = _resolve_app(app_id)
    if not app:
        return {"ok": False, "manifestFound": False, "message": f"app not found: {app_id}"}
    if _APPS_HTTP_MODE != "real":
        return _mock_app_response(app, "install")
    if not _flatpak_which():
        return {
            "ok": False, "appId": app["id"], "manifestFound": True,
            "installed": False, "flatpakAvailable": False, "host": "web",
            "message": "flatpak is not installed on this host.",
            "actionableCommand": "sudo apt-get install -y flatpak && flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
        }
    # Arch gate. Spotify/Steam/Discord/Slack are x86_64-only on Flathub today
    # and will fail with a confusing "No remote refs found" deep inside an
    # apt-style install spinner. Catch it before we shell out.
    arches = app.get("arches") or []
    host_arch = _host_flatpak_arch()
    if arches and host_arch not in arches:
        supported = ", ".join(arches)
        return {
            "ok": False, "appId": app["id"], "manifestFound": True,
            "installed": False, "flatpakAvailable": True, "host": "web",
            "archIncompatible": True, "hostArch": host_arch, "supportedArches": arches,
            "message": (
                f"{app['name']} is not available for this CPU architecture. "
                f"Flathub publishes {app['flatpak_id']} for {supported} only; this host is {host_arch}."
            ),
        }
    cmd = list(app["install"]["command"])
    code, _out, err = _run(cmd, timeout=600)
    # Whatever the outcome, the cached `installed?` answer is now stale.
    _flatpak_cache_bust(f"installed:{app['flatpak_id']}")
    if code == 0:
        return {
            "ok": True, "appId": app["id"], "manifestFound": True,
            "installed": True, "flatpakAvailable": True, "host": "web",
            "message": f"installed {app['name']}.",
        }
    short = err.strip().splitlines()[-1] if err.strip() else "unknown error"
    return {
        "ok": False, "appId": app["id"], "manifestFound": True,
        "installed": False, "flatpakAvailable": True, "host": "web",
        "message": f"install failed: {short[:240]}",
        "details": err.strip().splitlines()[-5:],
        "actionableCommand": " ".join(cmd),
    }


@router.post("/apps/{app_id}/launch", summary="Launch a Hosaka app (mock by default)", dependencies=[Depends(require_write)])
def v1_apps_launch(app_id: str) -> dict[str, Any]:
    app = _resolve_app(app_id)
    if not app:
        return {"ok": False, "manifestFound": False, "message": f"app not found: {app_id}"}
    if _APPS_HTTP_MODE != "real":
        return _mock_app_response(app, "launch")
    cmd = list(app["launch"]["command"])
    env, seat_user, note = _resolve_kiosk_seat_env()
    # If the webserver runs as root (the kiosk case) and we found a seat,
    # drop privs so the launched window joins the operator's wayland/X11
    # session. Without this the process spawns headless and never paints.
    if seat_user and os.geteuid() == 0:
        cmd = ["runuser", "-u", seat_user, "--"] + cmd
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, **env},
        )
    except (OSError, FileNotFoundError) as e:
        return {"ok": False, "appId": app["id"], "host": "web", "message": f"launch failed: {e}"}
    msg = f"launched {app['name']}."
    if note:
        msg += f" ({note})"
    return {"ok": True, "appId": app["id"], "manifestFound": True, "launched": True, "host": "web", "message": msg}


def _resolve_kiosk_seat_env() -> tuple[dict[str, str], Optional[str], Optional[str]]:
    """Find the operator's graphical session env so spawned flatpak apps render.

    Returns (env-overrides, user-to-runuser-as, optional human note).
    Strategy:
      1. Honor explicit overrides via HOSAKA_KIOSK_USER / HOSAKA_KIOSK_DISPLAY
         / HOSAKA_KIOSK_WAYLAND_DISPLAY / HOSAKA_KIOSK_XDG_RUNTIME_DIR.
      2. Otherwise, scan /run/user/<uid>/ for wayland-* sockets; take the
         lowest-uid match >= 1000 as the kiosk seat.
      3. Fall back to no overrides — the launch will still happen, but may
         appear headless if there is no display attached yet.
    """
    user = os.getenv("HOSAKA_KIOSK_USER")
    xdg = os.getenv("HOSAKA_KIOSK_XDG_RUNTIME_DIR")
    wayland = os.getenv("HOSAKA_KIOSK_WAYLAND_DISPLAY")
    display = os.getenv("HOSAKA_KIOSK_DISPLAY")
    note: Optional[str] = None

    if not (user and xdg and (wayland or display)):
        # auto-detect from /run/user/<uid>
        try:
            run_user = Path("/run/user")
            candidates = sorted(
                (int(p.name) for p in run_user.iterdir() if p.name.isdigit() and int(p.name) >= 1000),
            )
        except OSError:
            candidates = []
        for uid in candidates:
            seat = run_user / str(uid)
            wls = sorted(seat.glob("wayland-*"))
            wls = [p for p in wls if not p.name.endswith(".lock")]
            if not wls and not (seat / "X11-unix").exists():
                continue
            try:
                import pwd
                pw = pwd.getpwuid(uid)
            except (KeyError, ImportError):
                continue
            user = user or pw.pw_name
            xdg = xdg or str(seat)
            if wls and not wayland:
                wayland = wls[0].name
            break
        if not user:
            note = "no kiosk seat found — app spawned headless."

    env: dict[str, str] = {}
    if xdg:
        env["XDG_RUNTIME_DIR"] = xdg
    if wayland:
        env["WAYLAND_DISPLAY"] = wayland
    if display:
        env["DISPLAY"] = display
    elif not wayland:
        env["DISPLAY"] = ":0"
    return env, user, note


@router.post("/apps/stage", summary="Stage a Flathub app manifest under hosaka-apps/apps/", dependencies=[Depends(require_write)])
def v1_apps_stage(body: AppStageIn) -> dict[str, Any]:
    flatpak_id = body.flatpak_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", flatpak_id):
        return {"ok": False, "message": "invalid flatpak id"}
    app_id = _normalize_app_token(body.id or flatpak_id.split(".")[-1] or flatpak_id)
    if not app_id:
        return {"ok": False, "message": "invalid app id"}
    target = _APPS_DIR / f"{app_id}.yaml"
    if target.exists() and not body.overwrite:
        return {"ok": False, "message": f"manifest already staged: {app_id}", "path": str(target)}
    manifest = {
        "id": app_id,
        "name": body.name or flatpak_id,
        "category": body.category or "other",
        "description": body.description or f"Flathub app {flatpak_id}.",
        "provider": body.provider or "Flathub",
        "backend": "flatpak",
        "flatpak_id": flatpak_id,
        "install": {"command": ["flatpak", "install", "-y", "--noninteractive", "flathub", flatpak_id]},
        "launch": {"command": ["flatpak", "run", flatpak_id]},
        "aliases": sorted({app_id, flatpak_id.lower()}),
        "memory": {"profile": "unknown"},
        "permissions_notes": ["Staged from Flathub catalog; review the app's own permissions before installing."],
        "account_login_required": False,
        "hosaka_manages_credentials": False,
        "notes": ["User-staged via the HTTP apps fallback."],
    }
    try:
        _APPS_DIR.mkdir(parents=True, exist_ok=True)
        target.write_text(_require_yaml().safe_dump(manifest, sort_keys=False), encoding="utf-8")
    except OSError as e:
        return {"ok": False, "message": f"write failed: {e}"}
    return {"ok": True, "id": app_id, "path": str(target)}
