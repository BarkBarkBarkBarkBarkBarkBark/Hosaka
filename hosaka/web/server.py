"""Hosaka web server — appliance edition.

Serves three things from a single FastAPI process:
  1. The static SPA (built frontend/dist → hosaka/web/ui/)
  2. API routes for the React shell to call (/api/chat, /ws/agent, /api/health)
  3. The legacy setup-wizard HTML pages (mounted under /setup/)

LLM routing mirrors hosaka/llm/router.py:
  picoclaw gateway → OpenAI API → offline stub

The /ws/agent WebSocket endpoint runs picoclaw as a local subprocess — no
Fly.io, no cloud intermediary. Identical wire protocol to agent-server/server.py
so agentClient.ts works without modification.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from hosaka.setup.orchestrator import build_default_orchestrator

log = logging.getLogger("hosaka.web")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# ── paths & config ────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
UI_DIR = HERE / "ui"              # built SPA lives here after `npm run build`
STATE_PATH_ENV = "HOSAKA_STATE_PATH"
DEFAULT_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))

# picoclaw
ACCESS_TOKEN = os.environ.get("HOSAKA_ACCESS_TOKEN", "").strip()
PICOCLAW_BIN = os.environ.get("PICOCLAW_BIN", "picoclaw")
PICOCLAW_MODEL = os.environ.get("PICOCLAW_MODEL", "").strip()
MSG_TIMEOUT_SECONDS = int(os.environ.get("HOSAKA_MSG_TIMEOUT", "90"))
MSG_MAX_CHARS = int(os.environ.get("HOSAKA_MSG_MAX_CHARS", "4000"))
RATE_LIMIT_PER_MIN = int(os.environ.get("HOSAKA_RATE_PER_MIN", "30"))
PING_INTERVAL = int(os.environ.get("HOSAKA_PING_INTERVAL", "15"))

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_BANNER_HINTS = (
    "picoclaw", "interactive mode", "goodbye", "ctrl+c",
    "saving config", "checking for updates", "no updates available",
)

# ── setup-wizard orchestrator ─────────────────────────────────────────────────

orchestrator = build_default_orchestrator(
    Path(os.getenv(STATE_PATH_ENV)) if os.getenv(STATE_PATH_ENV) else None
)

# ── rate-limit state (per-connection, keyed by remote addr) ──────────────────

_rate: dict[str, list[float]] = {}


def _check_rate(key: str) -> bool:
    now = time.monotonic()
    bucket = [t for t in _rate.get(key, []) if now - t < 60]
    _rate[key] = bucket
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        return False
    bucket.append(now)
    return True


# ── auth ──────────────────────────────────────────────────────────────────────

def _auth_ok(token: str) -> bool:
    if not ACCESS_TOKEN:
        return True   # open in local-only deployments
    return hmac.compare_digest(ACCESS_TOKEN.encode(), token.encode())


# ── picoclaw helpers ──────────────────────────────────────────────────────────

def _picoclaw_available() -> bool:
    return bool(shutil.which(PICOCLAW_BIN))


def _strip_picoclaw_banner(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = _ANSI_RE.sub("", raw).strip()
        if any(hint in line.lower() for hint in _BANNER_HINTS):
            continue
        lines.append(raw)
    return "\n".join(lines).strip()


async def _run_picoclaw(message: str, session_key: str) -> AsyncGenerator[str, None]:
    """Run picoclaw as a subprocess and stream its output."""
    args = [PICOCLAW_BIN]
    if PICOCLAW_MODEL:
        args += ["--model", PICOCLAW_MODEL]
    args += ["--session", session_key, "--message", message]

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
    }
    if os.environ.get("OPENAI_API_KEY"):
        env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
    if PICOCLAW_MODEL:
        env["PICOCLAW_MODEL"] = PICOCLAW_MODEL

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        assert proc.stdout is not None
        buffer = b""
        async with asyncio.timeout(MSG_TIMEOUT_SECONDS):
            while True:
                chunk = await proc.stdout.read(256)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    decoded = line.decode("utf-8", errors="replace")
                    cleaned = _strip_picoclaw_banner(decoded)
                    if cleaned:
                        yield cleaned + "\n"
        if buffer:
            cleaned = _strip_picoclaw_banner(buffer.decode("utf-8", errors="replace"))
            if cleaned:
                yield cleaned
        await proc.wait()
    except asyncio.TimeoutError:
        yield "[hosaka: picoclaw timed out]"
    except Exception as exc:  # noqa: BLE001
        yield f"[hosaka: picoclaw error — {exc}]"


# ── OpenAI fallback ───────────────────────────────────────────────────────────

async def _openai_stream(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
    """Async wrapper around openai_adapter.chat_stream."""
    from hosaka.llm.openai_adapter import chat_stream

    loop = asyncio.get_event_loop()

    def _collect() -> list[str]:
        return list(chat_stream(messages))

    try:
        tokens = await asyncio.wait_for(
            loop.run_in_executor(None, _collect), timeout=MSG_TIMEOUT_SECONDS
        )
        for token in tokens:
            yield token
    except asyncio.TimeoutError:
        yield "[hosaka: openai timed out]"
    except Exception as exc:  # noqa: BLE001
        yield f"[hosaka: openai error — {exc}]"


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    log.info("Hosaka web server starting. UI dir: %s (exists=%s)", UI_DIR, UI_DIR.exists())
    yield
    log.info("Hosaka web server stopping.")


app = FastAPI(title="Hosaka Appliance", lifespan=lifespan)


# ── /api/health ───────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> JSONResponse:
    from hosaka.llm.openai_adapter import is_available as openai_ok
    from hosaka.llm.openclaw import is_gateway_up

    ui_built = False
    if UI_DIR.exists():
        try:
            ui_built = any(UI_DIR.iterdir())
        except OSError:
            pass

    return JSONResponse({
        "web": "ok",
        "picoclaw_bin": _picoclaw_available(),
        "picoclaw_gateway": is_gateway_up(),
        "openai_key": openai_ok(),
        "ui_built": ui_built,
    })


# ── /api/video  (inject a video URL into the web panel from the terminal) ────

_video_queue: list[dict] = []

@app.get("/api/video/next")
def video_next() -> JSONResponse:
    """The VideoPanel polls this to pick up injected URLs."""
    if _video_queue:
        return JSONResponse(_video_queue.pop(0))
    return JSONResponse({"url": None})


@app.post("/api/video")
async def video_inject(request: Request) -> JSONResponse:
    """Terminal injects a video URL; the web panel picks it up on next poll."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    url: str = body.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "no url"}, status_code=400)
    _video_queue.append({"url": url})
    return JSONResponse({"queued": True})


# ── /api/chat  (REST, single-turn, used by /ask in the web shell) ────────────

@app.post("/api/chat")
async def chat(request: Request) -> JSONResponse:
    """OpenAI-compatible single-turn chat endpoint."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    messages: list[dict[str, str]] = body.get("messages", [])
    if not messages:
        return JSONResponse({"error": "no messages"}, status_code=400)

    tokens: list[str] = []
    if _picoclaw_available():
        session_key = str(uuid.uuid4())[:8]
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        async for chunk in _run_picoclaw(last[:MSG_MAX_CHARS], session_key):
            tokens.append(chunk)
    else:
        async for chunk in _openai_stream(messages):
            tokens.append(chunk)

    text = "".join(tokens)
    return JSONResponse({"text": text, "model": PICOCLAW_MODEL or "openai"})


# ── /api/gemini  (alias — the React frontend's gemini.ts calls this path) ────

@app.post("/api/gemini")
async def gemini_alias(request: Request) -> JSONResponse:
    """Drop-in alias: the frontend calls /api/gemini; we route to local LLM.

    Accepts both Gemini wire format ({contents: [...]}) and plain chat format
    ({messages: [...]}) so the same endpoint works for both the cloud SPA and
    the appliance build.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    messages: list[dict[str, str]] = []

    # Gemini wire format: {contents: [{role, parts: [{text}]}]}
    for item in body.get("contents", []):
        role = item.get("role", "user")
        text = "".join(p.get("text", "") for p in item.get("parts", []))
        messages.append({"role": role, "content": text})

    # Plain chat format fallback
    if not messages:
        messages = body.get("messages", [])

    if not messages:
        return JSONResponse({"error": "no messages"}, status_code=400)

    tokens: list[str] = []
    if _picoclaw_available():
        session_key = str(uuid.uuid4())[:8]
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        async for chunk in _run_picoclaw(last[:MSG_MAX_CHARS], session_key):
            tokens.append(chunk)
    else:
        async for chunk in _openai_stream(messages):
            tokens.append(chunk)

    text = "".join(tokens)
    # Return in Gemini response shape so gemini.ts parser is happy
    return JSONResponse({
        "candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}],
        "modelVersion": PICOCLAW_MODEL or "gpt-4o-mini",
    })


# ── /ws/agent  (WebSocket — picoclaw agentic mode) ───────────────────────────

@app.websocket("/ws/agent")
async def agent_ws(ws: WebSocket) -> None:
    """WebSocket bridge to local picoclaw.
    Wire protocol mirrors agent-server/server.py so agentClient.ts works as-is.
    """
    await ws.accept()

    token = ws.query_params.get("token", "")
    if not _auth_ok(token):
        await ws.send_json({"type": "error", "error": "unauthorized"})
        await ws.close(code=4001)
        return

    sid = str(uuid.uuid4())
    remote = ws.client.host if ws.client else "local"

    picoclaw_ok = _picoclaw_available()
    await ws.send_json({
        "type": "hello",
        "sid": sid,
        "picoclaw": picoclaw_ok,
        "model": PICOCLAW_MODEL or None,
        "ttl_seconds": MSG_TIMEOUT_SECONDS,
    })

    async def _ping_loop() -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break

    ping_task: asyncio.Task[Any] = asyncio.create_task(_ping_loop())
    busy = False

    try:
        while True:
            raw = await ws.receive_text()

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "error": "bad json"})
                continue

            message: str = payload.get("message", "").strip()
            if not message:
                continue

            if len(message) > MSG_MAX_CHARS:
                await ws.send_json({"type": "error", "error": "message too long"})
                continue

            if not _check_rate(remote):
                await ws.send_json({"type": "error", "error": "rate_limited"})
                continue

            if busy:
                await ws.send_json({"type": "error", "error": "busy"})
                continue

            busy = True
            await ws.send_json({"type": "thinking"})

            reply_chunks: list[str] = []
            try:
                if picoclaw_ok:
                    async for chunk in _run_picoclaw(message, sid):
                        reply_chunks.append(chunk)
                else:
                    msgs = [{"role": "user", "content": message}]
                    async for chunk in _openai_stream(msgs):
                        reply_chunks.append(chunk)

                reply = "".join(reply_chunks)
                await ws.send_json({
                    "type": "reply",
                    "text": reply,
                    "stdout": reply,
                    "stderr": "",
                })
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"type": "error", "error": str(exc)})
            finally:
                busy = False

    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()


# ── /setup/* legacy wizard ────────────────────────────────────────────────────

def _layout(title: str, body: str) -> str:
    return f"""
    <html><head><title>{title}</title><meta name='viewport' content='width=device-width,initial-scale=1'/>
    <style>
      body {{ font-family: system-ui; background:#0b0f17; color:#e5ecff; margin:0; padding:20px; }}
      .card {{ max-width:760px; margin:0 auto; background:#121827; padding:20px; border-radius:12px; }}
      a,button {{ color:#0b0f17; background:#56d5ff; border:none; border-radius:8px; padding:10px 12px; text-decoration:none; cursor:pointer; }}
      input {{ width:100%; margin:8px 0 14px; padding:10px; border-radius:8px; border:1px solid #2b3a5a; background:#0b0f17; color:#fff; }}
      .muted {{ color:#91a4d4; font-size:0.9rem; }}
    </style></head><body><div class='card'>{body}</div></body></html>
    """


@app.get("/setup", response_class=HTMLResponse)
@app.get("/setup/", response_class=HTMLResponse)
def setup_home() -> str:
    orchestrator.update_runtime_network()
    summary = orchestrator.summary()
    body = f"""
    <h1>Hosaka Setup</h1>
    <p class='muted'>Terminal remains the primary appliance interface.</p>
    <p>Step: <strong>{summary['current_step']}</strong> ({summary['step_index']}/{summary['total_steps']})</p>
    <p>
      <a href='/setup/network'>Network</a>
      <a href='/setup/identity'>Identity</a>
      <a href='/setup/backend'>Backend</a>
      <a href='/setup/picoclaw'>Picoclaw</a>
      <a href='/api/health'>Health JSON</a>
    </p>
    """
    return _layout("Hosaka Setup", body)


@app.get("/setup/network", response_class=HTMLResponse)
def network_status() -> str:
    orchestrator.update_runtime_network()
    s = orchestrator.summary()
    body = (
        f"<h2>Network</h2>"
        f"<p>Local IP: <strong>{s['local_ip']}</strong></p>"
        f"<p>Tailscale: <strong>{s['tailscale_status']}</strong></p>"
        f"<p><a href='/setup/'>Back</a></p>"
    )
    return _layout("Network", body)


@app.get("/setup/identity", response_class=HTMLResponse)
def device_identity() -> str:
    s = orchestrator.summary()
    body = f"""
    <h2>Device Identity</h2>
    <form method='post' action='/setup/identity'>
      <label>Hostname</label><input name='hostname' value='{s["hostname"]}' placeholder='hosaka-field-terminal'/>
      <button type='submit'>Save</button>
    </form><p><a href='/setup/'>Back</a></p>
    """
    return _layout("Identity", body)


@app.post("/setup/identity")
def save_identity(hostname: str = Form(...)) -> RedirectResponse:
    orchestrator.set_field("hostname", hostname)
    return RedirectResponse("/setup/", status_code=303)


@app.get("/setup/backend", response_class=HTMLResponse)
def backend_config() -> str:
    s = orchestrator.summary()
    body = f"""
    <h2>Backend Config</h2>
    <form method='post' action='/setup/backend'>
      <label>Endpoint URL</label>
      <input name='backend_endpoint' value='{s["backend_endpoint"]}' placeholder='https://api.example.com'/>
      <button type='submit'>Save</button>
    </form><p><a href='/setup/'>Back</a></p>
    """
    return _layout("Backend", body)


@app.post("/setup/backend")
def save_backend(backend_endpoint: str = Form("")) -> RedirectResponse:
    orchestrator.set_field("backend_endpoint", backend_endpoint)
    return RedirectResponse("/setup/", status_code=303)


@app.get("/setup/picoclaw", response_class=HTMLResponse)
def picoclaw_config() -> str:
    s = orchestrator.summary()
    enabled = "yes" if s["picoclaw_enabled"] else "no"
    body = f"""
    <h2>Picoclaw Setup</h2>
    <form method='post' action='/setup/picoclaw'>
      <label>Enable Picoclaw (yes/no)</label>
      <input name='picoclaw_enabled' value='{enabled}' />
      <button type='submit'>Save</button>
    </form><p><a href='/setup/'>Back</a></p>
    """
    return _layout("Picoclaw", body)


@app.post("/setup/picoclaw")
def save_picoclaw(picoclaw_enabled: str = Form("yes")) -> RedirectResponse:
    enabled = picoclaw_enabled.strip().lower() not in {"no", "false", "0"}
    orchestrator.set_field("picoclaw_enabled", enabled)
    orchestrator.set_field("picoclaw_ready", enabled)
    return RedirectResponse("/setup/", status_code=303)


@app.get("/setup/progress")
def progress_status() -> JSONResponse:
    return JSONResponse(orchestrator.summary())


# ── static SPA (must be last — catches everything not matched above) ──────────

if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="spa")
else:
    log.warning(
        "SPA UI directory not found at %s. "
        "Run `cd frontend && npm ci && npm run build` then copy dist/ to hosaka/web/ui/. "
        "Setup wizard available at /setup/",
        UI_DIR,
    )

    @app.get("/", response_class=HTMLResponse)
    def root_fallback() -> str:
        body = """
        <h1>Hosaka — UI not built yet</h1>
        <p>Run the frontend build, then copy <code>dist/</code> to
        <code>hosaka/web/ui/</code>.</p>
        <p><a href='/setup/'>Setup wizard</a> &nbsp;&nbsp; <a href='/api/health'>Health</a></p>
        """
        return _layout("Hosaka", body)
