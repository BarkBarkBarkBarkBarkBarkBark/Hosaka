"""Hosaka beacon registry.

The beacon is a tiny capability advertisement for Hosaka nodes on the
same tailnet. It is intentionally small and append-only friendly so it
can travel in three places without schema drift:

  1. `/api/health` as a local capability manifest
  2. `/ws/sync` peer hello frames for low-latency gossip
  3. a durable JSON cache on disk so the Nodes panel survives restarts

The current scope is intentionally modest: presence, commit/version,
capabilities, and the last place we observed the peer. Todos/messages
still sync through their existing CRDT flows; this beacon is discovery
and capability metadata only.
"""
from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from hosaka.network import tailscale as ts

STATE_DIR = Path(os.getenv("HOSAKA_STATE_DIR", str(Path.home() / ".hosaka" / "state")))
BEACON_PATH = STATE_DIR / "beacons.json"
BEACON_PROTOCOL_VERSION = 1
BEACON_TTL_SECONDS = int(os.getenv("HOSAKA_BEACON_TTL", "180"))


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _public_mode() -> bool:
    return _env_flag("HOSAKA_PUBLIC_MODE", False)


def _capabilities() -> list[str]:
    if _public_mode():
        return ["api.v1"]

    caps = ["api.v1", "beacon.v1"]
    if _env_flag("HOSAKA_SYNC_ENABLED", True):
        caps.append("sync.ws")
    if _env_flag("HOSAKA_TAILSCALE_API_ENABLED", True):
        caps.extend(["tailscale.cli", "nodes.panel"])
    if _env_flag("HOSAKA_WEB_PANEL_ENABLED", True):
        caps.append("web.panel")
    if _env_flag("HOSAKA_SETTINGS_ENABLED", True):
        caps.append("settings.drawer")
    return caps


def _local_identity() -> tuple[str, dict[str, Any]]:
    info = ts.self_info()
    hostname = info.get("hostname") or socket.gethostname()
    dns_name = info.get("dns_name") or ""
    seed = os.getenv("HOSAKA_NODE_ID") or dns_name or hostname
    node_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))
    return node_id, info


def build_local_beacon() -> dict[str, Any]:
    node_id, info = _local_identity()
    connected = bool(info.get("connected"))
    return {
        "protocol": BEACON_PROTOCOL_VERSION,
        "node_id": node_id,
        "hostname": info.get("hostname") or socket.gethostname(),
        "dns_name": info.get("dns_name") or "",
        "ip": info.get("ip"),
        "os": info.get("os") or os.getenv("HOST_OS", "unknown"),
        "commit": os.getenv("HOSAKA_COMMIT", "dev"),
        "version": os.getenv("HOSAKA_VERSION", os.getenv("HOSAKA_COMMIT", "dev")),
        "transport": ["health", "sync.ws"],
        "capabilities": _capabilities(),
        "public_mode": _public_mode(),
        "tailscale_connected": connected,
        "last_seen": time.time(),
        "source": "local",
    }


class BeaconRegistry:
    def __init__(self) -> None:
        self._loaded = False
        self._remote: dict[str, dict[str, Any]] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not BEACON_PATH.exists():
            return
        try:
            data = json.loads(BEACON_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        peers = data.get("peers")
        if not isinstance(peers, list):
            return
        for raw in peers:
            if isinstance(raw, dict):
                beacon = self._sanitize(raw)
                if beacon is not None:
                    self._remote[beacon["node_id"]] = beacon
        self.prune()

    def _persist(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "protocol": BEACON_PROTOCOL_VERSION,
            "saved_at": time.time(),
            "peers": sorted(self._remote.values(), key=lambda b: str(b.get("hostname", "")).lower()),
        }
        try:
            BEACON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            return

    def _sanitize(self, raw: dict[str, Any], source_ip: str | None = None) -> dict[str, Any] | None:
        node_id = str(raw.get("node_id") or "").strip()
        if not node_id:
            return None
        capabilities_raw = raw.get("capabilities") or []
        capabilities: list[str] = []
        if isinstance(capabilities_raw, list):
            for cap in capabilities_raw:
                if not isinstance(cap, str):
                    continue
                text = cap.strip()
                if text and text not in capabilities:
                    capabilities.append(text[:64])

        transport_raw = raw.get("transport") or []
        transport: list[str] = []
        if isinstance(transport_raw, list):
            for entry in transport_raw:
                if isinstance(entry, str):
                    text = entry.strip()
                    if text and text not in transport:
                        transport.append(text[:64])

        last_seen = raw.get("last_seen")
        try:
            seen = float(last_seen) if last_seen is not None else time.time()
        except (TypeError, ValueError):
            seen = time.time()

        beacon = {
            "protocol": BEACON_PROTOCOL_VERSION,
            "node_id": node_id[:128],
            "hostname": str(raw.get("hostname") or "unknown")[:128],
            "dns_name": str(raw.get("dns_name") or "")[:255],
            "ip": str(raw.get("ip") or source_ip or "")[:64] or None,
            "os": str(raw.get("os") or "unknown")[:64],
            "commit": str(raw.get("commit") or "")[:128],
            "version": str(raw.get("version") or "")[:128],
            "transport": transport,
            "capabilities": capabilities,
            "public_mode": bool(raw.get("public_mode", False)),
            "tailscale_connected": bool(raw.get("tailscale_connected", False)),
            "last_seen": seen,
            "source": str(raw.get("source") or "peer")[:32],
        }
        if source_ip:
            beacon["source_ip"] = source_ip
        return beacon

    def prune(self) -> None:
        self._ensure_loaded()
        cutoff = time.time() - BEACON_TTL_SECONDS
        stale = [node_id for node_id, beacon in self._remote.items() if float(beacon.get("last_seen", 0)) < cutoff]
        if not stale:
            return
        for node_id in stale:
            del self._remote[node_id]
        self._persist()

    def local_beacon(self) -> dict[str, Any]:
        self._ensure_loaded()
        return build_local_beacon()

    def register_remote(self, raw: dict[str, Any], source_ip: str | None = None) -> dict[str, Any] | None:
        self._ensure_loaded()
        beacon = self._sanitize(raw, source_ip=source_ip)
        if beacon is None:
            return None
        beacon["last_seen"] = time.time()
        beacon["source"] = "peer"
        self._remote[beacon["node_id"]] = beacon
        self.prune()
        self._persist()
        return dict(beacon)

    def get_for_ip(self, ip: str | None) -> dict[str, Any] | None:
        self._ensure_loaded()
        self.prune()
        if not ip:
            return None
        for beacon in self._remote.values():
            if beacon.get("ip") == ip or beacon.get("source_ip") == ip:
                return dict(beacon)
        return None

    def snapshot(self) -> dict[str, Any]:
        self._ensure_loaded()
        self.prune()
        peers = sorted(self._remote.values(), key=lambda b: str(b.get("hostname", "")).lower())
        return {
            "protocol": BEACON_PROTOCOL_VERSION,
            "self": self.local_beacon(),
            "peers": [dict(peer) for peer in peers],
        }


_registry: BeaconRegistry | None = None


def get_registry() -> BeaconRegistry:
    global _registry
    if _registry is None:
        _registry = BeaconRegistry()
    return _registry