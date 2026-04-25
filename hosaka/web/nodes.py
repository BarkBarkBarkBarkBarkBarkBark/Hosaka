"""Nodes + Tailscale API — powers the frontend Nodes panel.

Three endpoints:
  GET  /api/tailscale/status   → light shape of `tailscale status`
  POST /api/tailscale/up       → SSE stream of the `tailscale up` browser flow
  GET  /api/nodes              → tailnet peers that answer on :8421/api/health

Gated by `nodes_enabled` in /api/health. Never exposed from the hosted
Vercel build — field-terminal's api/health.ts returns {nodes_enabled: false}
so App.tsx never renders the Nodes panel there and never calls these routes.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from hosaka.network import tailscale as ts
from hosaka.web.beacon_registry import BEACON_PROTOCOL_VERSION, get_registry

router = APIRouter()

# Port Hosaka serves its UI + API on. Peers must be running the same port;
# anything else is not reachable by us. Matches DEFAULT_PORT in server.py.
HOSAKA_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))

# Health-probe timeout per peer. Keep short — we want /api/nodes to feel
# snappy even when half the tailnet is offline.
PROBE_TIMEOUT = 1.5


# ── /api/tailscale/status ─────────────────────────────────────────────────────


@router.get("/api/tailscale/status")
def tailscale_status() -> JSONResponse:
    """Return a small shape describing the local node's tailnet state."""
    status = ts.status_json()
    if not status.get("installed"):
        return JSONResponse({"installed": False, "connected": False})
    if not status.get("connected"):
        return JSONResponse({"installed": True, "connected": False})

    return JSONResponse({
        **ts.self_info(),
        "beacon": get_registry().local_beacon(),
        "peer_count": len(status.get("Peer") or {}),
    })


@router.get("/api/beacon")
def beacon_snapshot() -> JSONResponse:
    """Return the local beacon plus the last seen peer beacons."""
    return JSONResponse(get_registry().snapshot())


# ── /api/tailscale/up  (SSE stream of browser login flow) ─────────────────────


@router.post("/api/tailscale/up")
async def tailscale_up(hostname: str | None = None) -> StreamingResponse:
    """Stream the `tailscale up` output as Server-Sent Events.

    Browser usage:
        const es = new EventSource("/api/tailscale/up", { method: "POST" });
        es.addEventListener("login_url", (e) => window.open(e.data, "_blank"));
        es.addEventListener("done", () => es.close());

    Events emitted: `line`, `login_url`, `done`. See hosaka.network.tailscale.
    """
    async def gen() -> Any:
        # SSE framing: "event: X\ndata: Y\n\n"
        async for evt in ts.up_interactive(hostname=hostname):
            event = evt["event"]
            data = evt["data"].replace("\n", " ")
            yield f"event: {event}\ndata: {data}\n\n".encode("utf-8")
            if event == "done":
                break

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "cache-control": "no-cache",
        "x-accel-buffering": "no",  # disable nginx buffering if proxied
    })


# ── /api/tailscale/logout ─────────────────────────────────────────────────────


@router.post("/api/tailscale/logout")
def tailscale_logout() -> JSONResponse:
    ok, msg = ts.logout()
    return JSONResponse({"ok": ok, "message": msg}, status_code=200 if ok else 500)


# ── /api/nodes  (probe each tailnet peer for a live Hosaka) ───────────────────


async def _probe_peer(client: httpx.AsyncClient, peer: dict[str, Any]) -> dict[str, Any]:
    """Probe a single peer's /api/health. Non-Hosaka peers return reachable=False."""
    ip = peer.get("ip")
    if not ip:
        return {**peer, "reachable": False}

    url = f"http://{ip}:{HOSAKA_PORT}/api/health"
    try:
        resp = await client.get(url, timeout=PROBE_TIMEOUT)
    except (httpx.HTTPError, OSError):
        return {**peer, "reachable": False}

    if resp.status_code != 200:
        return {**peer, "reachable": False}

    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        return {**peer, "reachable": False}

    # Only peers whose /api/health looks like ours count as "Hosaka nodes".
    # We check for a string field we know the Python server returns.
    if data.get("web") != "ok":
        return {**peer, "reachable": False}

    return {
        **peer,
        "reachable": True,
        "commit": data.get("commit"),
        "ui_built": bool(data.get("ui_built")),
        "beacon": data.get("beacon") if isinstance(data.get("beacon"), dict) else None,
    }


@router.get("/api/nodes")
async def list_nodes() -> JSONResponse:
    """Return the list of tailnet peers with a `reachable` flag set to True
    for those running Hosaka. The frontend uses this to populate the Nodes
    panel; it also surfaces non-Hosaka peers so the user can see what else
    is on their tailnet, but greys them out.
    """
    if not ts.is_installed():
        return JSONResponse({"installed": False, "connected": False, "self": None, "nodes": []})

    info = ts.self_info()
    if not info.get("connected"):
        return JSONResponse({"installed": True, "connected": False, "self": None, "nodes": []})

    peers = ts.peers()
    async with httpx.AsyncClient() as client:
        probed = await asyncio.gather(*(_probe_peer(client, p) for p in peers))

    registry = get_registry()
    nodes: list[dict[str, Any]] = []
    for peer in probed:
        beacon = peer.get("beacon") if isinstance(peer.get("beacon"), dict) else None
        if beacon is not None:
            beacon = registry.register_remote(beacon, source_ip=peer.get("ip")) or beacon
        else:
            beacon = registry.get_for_ip(peer.get("ip"))

        enriched = dict(peer)
        enriched["beacon"] = beacon
        if beacon is not None:
            enriched.setdefault("commit", beacon.get("commit"))
            enriched["node_id"] = beacon.get("node_id")
            enriched["capabilities"] = beacon.get("capabilities") or []
            enriched["beacon_seen_at"] = beacon.get("last_seen")
        nodes.append(enriched)

    return JSONResponse({
        "beacon_protocol": BEACON_PROTOCOL_VERSION,
        "installed": True,
        "connected": True,
        "self": {**info, "beacon": registry.local_beacon()},
        "nodes": nodes,
    })
