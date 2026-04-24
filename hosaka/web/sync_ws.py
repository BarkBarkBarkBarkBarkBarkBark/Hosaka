"""/ws/sync — Automerge change relay for Hosaka nodes.

The Python server here is a DUMB relay. All CRDT / conflict-resolution
logic lives in the browser (`frontend/src/sync/repo.ts`). Our only jobs:

  1. Fan out messages between connected clients on this node (all the
     browser tabs open against :8421, plus any peer-node WS we've dialed).
  2. Dial every reachable tailnet peer's `/ws/sync` and forward browser
     traffic to them + their traffic to local browsers.
  3. Keep a durable JSON-blob snapshot of the latest wire bytes per doc
     at `~/.hosaka/state/<doc>.am` so a headless Pi with no open browser
     doesn't lose data written while it was dark.

Message format is plain JSON strings:

    {"type":"hello","node_id":"abc123","role":"browser"|"peer"}
    {"type":"snapshot","doc":"todo","b64":"..."}
    {"type":"changes", "doc":"todo","b64":"..."}

Binary Automerge payloads are base64-encoded so we can use JSON and keep
the WS protocol trivially debuggable with `websocat`. Overhead is ~33%
of the payload — negligible at our scale (todo doc <10 KB).

Loop prevention: messages arriving from a peer are re-sent to all local
browsers but NOT forwarded back out to other peers. Peers trust each
other to have their own browser clients.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hosaka.network import tailscale as ts

log = logging.getLogger("hosaka.sync")

router = APIRouter()

STATE_DIR = Path(os.getenv("HOSAKA_STATE_DIR", str(Path.home() / ".hosaka" / "state")))
HOSAKA_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))

# Known doc names. Anything else from a misbehaving or outdated peer we
# still relay (because we can't introspect encrypted payloads later), but
# we won't persist snapshots for unknown docs — keep disk footprint tight.
KNOWN_DOCS = {"todo", "messages", "ui", "lang", "llm"}


class SyncHub:
    """Single-process state for all connected clients + outbound peer dials."""

    def __init__(self) -> None:
        self.browsers: set[WebSocket] = set()
        self.peers: dict[str, _PeerLink] = {}   # ip -> link
        # Latest wire bytes per doc, used to hydrate newly-arriving clients
        # and to persist to disk. Value is the raw bytes (already decoded
        # from base64) for the most recent snapshot of that doc.
        self.latest: dict[str, bytes] = {}
        self._peer_refresher_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Idempotent. Kick off the peer-refresh loop once per process."""
        if self._peer_refresher_task is None:
            self._peer_refresher_task = asyncio.create_task(self._refresh_peers_loop())
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for name in KNOWN_DOCS:
            path = STATE_DIR / f"{name}.am"
            if path.exists():
                try:
                    self.latest[name] = path.read_bytes()
                except OSError as exc:
                    log.warning("could not load %s snapshot: %s", name, exc)

    async def attach_browser(self, ws: WebSocket) -> None:
        """Register a browser tab. Hydrate it with the latest snapshots we
        have on disk (so it sees data from peers even if none are online now)."""
        self.browsers.add(ws)
        for doc, raw in self.latest.items():
            try:
                await ws.send_text(json.dumps({
                    "type": "snapshot",
                    "doc": doc,
                    "b64": base64.b64encode(raw).decode("ascii"),
                }))
            except Exception:  # noqa: BLE001
                break

    async def detach_browser(self, ws: WebSocket) -> None:
        self.browsers.discard(ws)

    async def on_browser_message(self, raw: str) -> None:
        """Process a message from a local browser: persist snapshot bytes
        (for known docs), fan out to other local browsers, and forward to
        all dialed peers."""
        msg = self._parse(raw)
        if msg is None:
            return

        self._persist(msg)
        await self._fanout_local(raw, exclude=None)
        await self._forward_to_peers(raw)

    async def on_peer_message(self, raw: str, from_ip: str) -> None:
        """Process a message from a remote peer: persist + fan out to our
        local browsers only. We DO NOT echo to other peers (loop prevention)."""
        msg = self._parse(raw)
        if msg is None:
            return
        self._persist(msg)
        await self._fanout_local(raw, exclude=None)

    # ── internals ──

    def _parse(self, raw: str) -> dict[str, Any] | None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(msg, dict):
            return None
        return msg

    def _persist(self, msg: dict[str, Any]) -> None:
        doc = msg.get("doc")
        if msg.get("type") not in ("snapshot", "changes"):
            return
        if not isinstance(doc, str) or doc not in KNOWN_DOCS:
            return
        b64 = msg.get("b64")
        if not isinstance(b64, str):
            return
        try:
            raw_bytes = base64.b64decode(b64, validate=True)
        except (ValueError, TypeError):
            return

        # For a `changes` message we APPEND to the accumulated bytes —
        # Automerge treats concatenated change-bytes as equivalent to a
        # single incremental load. For a `snapshot` we replace outright
        # (snapshot is the full save, guaranteed to contain everything).
        if msg["type"] == "snapshot":
            self.latest[doc] = raw_bytes
        else:
            prev = self.latest.get(doc, b"")
            self.latest[doc] = prev + raw_bytes

        try:
            (STATE_DIR / f"{doc}.am").write_bytes(self.latest[doc])
        except OSError as exc:
            log.warning("could not persist %s: %s", doc, exc)

    async def _fanout_local(self, raw: str, exclude: WebSocket | None) -> None:
        dead: list[WebSocket] = []
        for ws in self.browsers:
            if ws is exclude:
                continue
            try:
                await ws.send_text(raw)
            except Exception:  # noqa: BLE001 — client gone, prune
                dead.append(ws)
        for ws in dead:
            self.browsers.discard(ws)

    async def _forward_to_peers(self, raw: str) -> None:
        for link in list(self.peers.values()):
            await link.send(raw)

    async def _refresh_peers_loop(self) -> None:
        """Every 20s, reconcile our outbound peer connections with the
        current tailnet peer list from `tailscale status`."""
        while True:
            try:
                await self._reconcile_peers()
            except Exception as exc:  # noqa: BLE001
                log.debug("peer reconcile error: %s", exc)
            await asyncio.sleep(20)

    async def _reconcile_peers(self) -> None:
        if not ts.is_installed():
            return
        status = ts.status_json()
        if not status.get("connected"):
            return

        wanted: dict[str, dict[str, Any]] = {}
        for peer in ts.peers():
            if not peer.get("online"):
                continue
            ip = peer.get("ip")
            if ip:
                wanted[ip] = peer

        # Dial any peer we don't already have a link to.
        for ip, peer in wanted.items():
            if ip not in self.peers:
                link = _PeerLink(ip=ip, hub=self)
                self.peers[ip] = link
                link.start()

        # Close links to peers that disappeared.
        for ip in list(self.peers):
            if ip not in wanted:
                await self.peers[ip].stop()
                del self.peers[ip]


class _PeerLink:
    """Persistent outbound WS to a single tailnet peer's /ws/sync."""

    def __init__(self, ip: str, hub: SyncHub) -> None:
        self.ip = ip
        self.hub = hub
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._ws = None  # httpx_ws / websockets client; dialed lazily

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped = True
        task = self._task
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def send(self, raw: str) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            await ws.send(raw)
        except Exception:  # noqa: BLE001
            pass

    async def _run(self) -> None:
        """Connect, send our snapshots, forward messages until closed."""
        try:
            import websockets  # type: ignore[import-not-found]
        except ImportError:
            log.info("websockets lib not available; peer sync disabled")
            return

        url = f"ws://{self.ip}:{HOSAKA_PORT}/ws/sync"
        backoff = 1.0
        while not self._stopped:
            try:
                async with websockets.connect(
                    url,
                    open_timeout=3,
                    close_timeout=3,
                    ping_interval=20,
                ) as ws:
                    self._ws = ws
                    backoff = 1.0
                    # Hello + snapshot flush so the remote side catches up.
                    await ws.send(json.dumps({
                        "type": "hello",
                        "node_id": f"peer:{self.ip}",
                        "role": "peer",
                    }))
                    for doc, raw in self.hub.latest.items():
                        await ws.send(json.dumps({
                            "type": "snapshot",
                            "doc": doc,
                            "b64": base64.b64encode(raw).decode("ascii"),
                        }))
                    async for raw in ws:
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode("utf-8", errors="replace")
                        await self.hub.on_peer_message(raw, self.ip)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                log.debug("peer %s link dropped: %s (backoff %.1fs)", self.ip, exc, backoff)
            finally:
                self._ws = None

            if self._stopped:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


_hub: SyncHub | None = None


def get_hub() -> SyncHub:
    global _hub
    if _hub is None:
        _hub = SyncHub()
    return _hub


# ── endpoint ──────────────────────────────────────────────────────────────────


@router.websocket("/ws/sync")
async def ws_sync(ws: WebSocket) -> None:
    """Sync relay for a single WebSocket client (browser tab or peer node).

    The role is declared by the client in its first `hello` message. If we
    never get one, we default to browser — which is safe (fan-out to locals).
    Peers identify as `peer`; their messages are not forwarded back to other
    peers, only to our local browsers.
    """
    await ws.accept()
    hub = get_hub()
    await hub.start()

    role = "browser"
    await hub.attach_browser(ws)

    try:
        while True:
            raw = await ws.receive_text()
            if not raw:
                continue
            # Peek at the hello to switch mode. Anything else goes to the
            # appropriate on_*_message handler.
            if role == "browser":
                # First-message peek: a peer-role hello flips us to peer mode
                # and stops us from being listed as a browser.
                try:
                    preview = json.loads(raw)
                except (ValueError, TypeError):
                    preview = {}
                if preview.get("type") == "hello" and preview.get("role") == "peer":
                    role = "peer"
                    await hub.detach_browser(ws)
                    continue

            if role == "browser":
                await hub.on_browser_message(raw)
            else:
                # Ingest from remote peer; fan to locals but not other peers.
                await hub.on_peer_message(raw, from_ip="incoming")
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.debug("sync ws error: %s", exc)
    finally:
        if role == "browser":
            await hub.detach_browser(ws)


