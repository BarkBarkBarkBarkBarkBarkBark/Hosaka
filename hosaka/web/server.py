"""Hosaka web server — appliance edition.

Serves three things from a single FastAPI process:
  1. The static SPA (`frontend` Vite build → hosaka/web/ui/)
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
import pty
import re
import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from hosaka.setup.orchestrator import build_default_orchestrator
from hosaka.web.beacon_registry import get_registry

log = logging.getLogger("hosaka.web")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# ── paths & config ────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
UI_DIR = HERE / "ui"              # built SPA lives here after `npm run build`
STATE_PATH_ENV = "HOSAKA_STATE_PATH"
DEFAULT_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


PUBLIC_MODE = _env_flag("HOSAKA_PUBLIC_MODE", False)
if PUBLIC_MODE:
    # Public mode is a hard boundary for the shared/public deployment.
    # Do not let env overrides quietly re-enable sensitive local features.
    SETTINGS_ENABLED = False
    WEB_PANEL_ENABLED = False
    NODES_UI_ENABLED = False
    TAILSCALE_API_ENABLED = False
    SYNC_ENABLED = False
    INBOX_ENABLED = False
else:
    SETTINGS_ENABLED = _env_flag("HOSAKA_SETTINGS_ENABLED", True)
    WEB_PANEL_ENABLED = _env_flag("HOSAKA_WEB_PANEL_ENABLED", True)
    NODES_UI_ENABLED = _env_flag("HOSAKA_NODES_UI_ENABLED", True)
    TAILSCALE_API_ENABLED = _env_flag("HOSAKA_TAILSCALE_API_ENABLED", NODES_UI_ENABLED)
    SYNC_ENABLED = _env_flag("HOSAKA_SYNC_ENABLED", NODES_UI_ENABLED)
    INBOX_ENABLED = _env_flag("HOSAKA_INBOX_ENABLED", True)

# picoclaw
ACCESS_TOKEN = os.environ.get("HOSAKA_ACCESS_TOKEN", "").strip()
PICOCLAW_BIN = os.environ.get("PICOCLAW_BIN", "picoclaw")
PICOCLAW_MODEL = os.environ.get("PICOCLAW_MODEL", "").strip()
def _default_picoclaw_home() -> str:
    """Pick Picoclaw's config root, not the operator's account home."""
    home = str(Path.home())
    if home == "/root" and Path("/home/operator").exists():
        return "/home/operator/.picoclaw"
    return str(Path(home) / ".picoclaw")


# Picoclaw 0.2.x honors PICOCLAW_HOME as its config root. The expected layout is
# $PICOCLAW_HOME/config.json and $PICOCLAW_HOME/workspace. Do not point this at
# the user's account home, or Picoclaw will silently use ~/config.json instead
# of ~/.picoclaw/config.json.
PICOCLAW_HOME = os.environ.get("PICOCLAW_HOME", _default_picoclaw_home())
MSG_TIMEOUT_SECONDS = int(os.environ.get("HOSAKA_MSG_TIMEOUT", "90"))
MSG_MAX_CHARS = int(os.environ.get("HOSAKA_MSG_MAX_CHARS", "4000"))
RATE_LIMIT_PER_MIN = int(os.environ.get("HOSAKA_RATE_PER_MIN", "30"))
PING_INTERVAL = int(os.environ.get("HOSAKA_PING_INTERVAL", "15"))
SHELL_ENABLED = _env_flag("HOSAKA_SHELL_ENABLED", not PUBLIC_MODE)
SHELL_TIMEOUT_SECONDS = int(os.environ.get("HOSAKA_SHELL_TIMEOUT", "20"))
SHELL_MAX_CHARS = int(os.environ.get("HOSAKA_SHELL_MAX_CHARS", "20000"))
SHELL_CWD = Path(os.environ.get("HOSAKA_SHELL_CWD", os.getcwd())).expanduser()

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_BANNER_HINTS = (
    "picoclaw", "interactive mode", "goodbye", "ctrl+c",
    "saving config", "checking for updates", "no updates available",
)
# Matches Go's default logger prefix, e.g. "2026/04/18 23:25:01 session: ..."
_GOLOG_RE = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\b")
# Anything in this set is "decorative box-drawing / banner glyphs". A line
# composed *only* of these (after ANSI strip + whitespace strip) is junk.
_BANNER_GLYPHS = set("█▓▒░╔╗╚╝║═╠╣╦╩╬─│┌┐└┘├┤┬┴┼ ")

# ── setup-wizard orchestrator ─────────────────────────────────────────────────

orchestrator = build_default_orchestrator(
    Path(os.getenv(STATE_PATH_ENV)) if os.getenv(STATE_PATH_ENV) else None
)

# Load persisted LLM config and inject into env so openai_adapter picks it up
try:
    from hosaka.llm.llm_config import apply_to_env as _llm_apply, load as _llm_load
    _llm_apply(_llm_load())
except Exception as _llm_exc:  # noqa: BLE001
    log.warning("could not load llm config: %s", _llm_exc)

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


def _picoclaw_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")
    env["PICOCLAW_HOME"] = PICOCLAW_HOME
    env.setdefault("HOME", str(Path(PICOCLAW_HOME).expanduser().parent))
    env.setdefault("XDG_CONFIG_HOME", f"{PICOCLAW_HOME}/.config")
    env.setdefault("XDG_CACHE_HOME", f"{PICOCLAW_HOME}/.cache")
    if PICOCLAW_MODEL:
        env["PICOCLAW_MODEL"] = PICOCLAW_MODEL
    return env


def _picoclaw_readiness() -> tuple[bool, str]:
    """Fast readiness check with operator-facing remediation text."""
    if not _picoclaw_available():
        return (
            False,
            "picoclaw is not installed on this host. Run `/configure picoclaw` "
            "inside Hosaka, or run `hosaka configure picoclaw` from Terminal.",
        )
    try:
        result = subprocess.run(
            [PICOCLAW_BIN, "status"],
            env=_picoclaw_env(),
            capture_output=True,
            text=True,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return False, "picoclaw status timed out. Run `hosaka configure picoclaw --no-onboard`, then restart `hosaka dev -fresh`."
    except OSError as exc:
        return False, f"picoclaw could not start: {exc}. Run `hosaka configure picoclaw`."

    status = result.stdout + result.stderr
    if result.returncode != 0:
        detail = _strip_picoclaw_banner(status).strip()
        if detail:
            return False, f"picoclaw status failed: {detail}. Run `hosaka configure picoclaw --no-onboard`, then restart `hosaka dev -fresh`."
        return False, "picoclaw status failed. Run `hosaka configure picoclaw --no-onboard`, then restart `hosaka dev -fresh`."
    if "Config:" not in status or "✓" not in status:
        return False, "picoclaw config is missing. Run `/configure picoclaw` or `hosaka configure picoclaw`."
    if not re.search(r"Model:\s*\S+", status, re.IGNORECASE):
        return False, "picoclaw has no default model. Run `/configure picoclaw` or `hosaka configure picoclaw`."
    if re.search(r"OpenAI API:\s*(missing|not set|✗)", status, re.IGNORECASE) and not os.environ.get("OPENAI_API_KEY"):
        return False, "picoclaw has no OpenAI key. Add it in `/settings`, then run `/configure picoclaw`."
    if not os.environ.get("OPENAI_API_KEY") and "OpenAI API:" not in status:
        return False, "Hosaka has no OpenAI key in its service env. Add it in `/settings`, then run `/configure picoclaw`."
    return True, ""


def _picoclaw_not_ready_reply(reason: str) -> str:
    return (
        "picoclaw is not ready yet.\n\n"
        f"{reason}\n\n"
        "try:\n"
        "  /configure picoclaw\n"
        "  /agent local\n"
        "  /agent test\n\n"
        "if you are in macOS Terminal instead, run:\n"
        "  hosaka configure picoclaw --no-onboard\n"
        "  hosaka dev -fresh"
    )


def _shell_bin() -> str:
    configured = os.environ.get("SHELL", "").strip()
    if configured and Path(configured).exists():
        return configured
    for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
        if Path(candidate).exists():
            return candidate
    return "sh"


async def _run_local_shell(cmd: str) -> dict[str, Any]:
    """Run one non-interactive local shell command for the dev/appliance UI."""
    if PUBLIC_MODE or not SHELL_ENABLED:
        return {"stdout": "", "stderr": "local shell is disabled on this host", "exit": 126}
    if not cmd.strip():
        return {"stdout": "", "stderr": "empty command", "exit": 2}
    if len(cmd) > MSG_MAX_CHARS:
        return {"stdout": "", "stderr": "command too long", "exit": 2}

    env = _picoclaw_env()
    cwd = SHELL_CWD if SHELL_CWD.exists() else Path.cwd()
    try:
        proc = await asyncio.create_subprocess_exec(
            _shell_bin(),
            "-lc",
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"stdout": "", "stderr": f"timeout after {SHELL_TIMEOUT_SECONDS}s", "exit": 124}
        stdout = stdout_b.decode("utf-8", errors="replace")[:SHELL_MAX_CHARS]
        stderr = stderr_b.decode("utf-8", errors="replace")[:SHELL_MAX_CHARS]
        return {"stdout": stdout, "stderr": stderr, "exit": int(proc.returncode or 0)}
    except FileNotFoundError as exc:
        return {"stdout": "", "stderr": f"shell not found: {exc}", "exit": 127}
    except Exception as exc:  # noqa: BLE001
        return {"stdout": "", "stderr": f"shell failed: {exc}", "exit": 1}


def _strip_picoclaw_banner(text: str) -> str:
    """Drop picoclaw's startup banner + Go log noise from a chunk of stdout.

    What we filter:
      - The big PICOCLAW block-letter ASCII banner (any line whose visible
        characters are all box-drawing glyphs is treated as decoration).
      - Go-default-logger lines ("2026/04/18 23:25:01 ...") — these are
        diagnostic, not user-facing.
      - Lines containing well-known banner phrases (interactive mode, etc.).
    """
    lines: list[str] = []
    for raw in text.splitlines():
        visible = _ANSI_RE.sub("", raw).strip()
        if not visible:
            # Line has no printable characters — usually a leftover terminal
            # control sequence (cursor moves, color resets) that picoclaw uses
            # to redraw its spinner. Keep a blank line for paragraph spacing
            # but drop the ANSI noise; otherwise xterm renders it as a
            # mysterious "empty" line full of invisible escapes.
            lines.append("")
            continue
        if _GOLOG_RE.match(visible):
            continue
        if any(hint in visible.lower() for hint in _BANNER_HINTS):
            continue
        if all(ch in _BANNER_GLYPHS for ch in visible):
            continue
        lines.append(raw)
    return "\n".join(lines).strip()


async def _run_picoclaw(message: str, session_key: str) -> AsyncGenerator[str, None]:
    """Run picoclaw as a subprocess and stream its output.

    Picoclaw 0.2+ exposes the non-interactive single-shot path under the
    `agent` subcommand, not as top-level flags:
        picoclaw agent --session <key> --message <text> [--model <name>]
    """
    args = [PICOCLAW_BIN, "agent", "--session", session_key, "--message", message]
    if PICOCLAW_MODEL:
        args += ["--model", PICOCLAW_MODEL]

    env = _picoclaw_env()
    if os.environ.get("OPENAI_API_KEY"):
        env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]

    try:
        # Merge stderr into stdout. Picoclaw writes its real errors (LLM 429s,
        # auth failures, "model not found", Cobra usage text, etc.) to stderr.
        # If we leave it on a separate pipe we never drain, those errors are
        # invisible to the operator — they just see blank lines.
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        assert proc.stdout is not None
        buffer = b""
        emitted_any = False
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
                        emitted_any = True
                        yield cleaned + "\n"
        if buffer:
            cleaned = _strip_picoclaw_banner(buffer.decode("utf-8", errors="replace"))
            if cleaned:
                emitted_any = True
                yield cleaned
        await proc.wait()
        # If picoclaw exited non-zero AND we filtered everything to empty, the
        # operator would otherwise see nothing. Surface a hint instead.
        if proc.returncode and not emitted_any:
            yield (
                f"[hosaka: picoclaw exited with code {proc.returncode} but produced "
                "no readable output — check the OpenAI/api-key / model config in "
                "~/.picoclaw/config.json, or run `picoclaw agent --message hi` "
                "directly to see the raw error]"
            )
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


app = FastAPI(
    title="Hosaka Appliance",
    description=(
        "API for the Hosaka Field Terminal Pi. The `/api/v1/*` surface is the "
        "public, versioned contract that hosakactl (Mac/Linux client) and the "
        "kiosk SPA both consume. See the published reference at "
        "https://<your-gh-user>.github.io/Hosaka/ for static docs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── v1 API (single source of truth for remote clients) ───────────────────────
from hosaka.web.api_v1 import router as v1_router  # noqa: E402
from hosaka.web.voice_api import router as voice_router  # noqa: E402
from hosaka.web.docs_api import router as docs_router  # noqa: E402
from hosaka.web.diag_api import router as diag_router  # noqa: E402
from hosaka.web.events_api import router as events_router  # noqa: E402
from hosaka.web.manual_api import router as manual_router  # noqa: E402
from hosaka.web.nodes import router as nodes_router  # noqa: E402
from hosaka.web.sync_ws import router as sync_router  # noqa: E402

app.include_router(v1_router)
app.include_router(voice_router)
app.include_router(docs_router)
app.include_router(diag_router)
app.include_router(events_router)
app.include_router(manual_router)
if TAILSCALE_API_ENABLED:
    app.include_router(nodes_router)
if SYNC_ENABLED:
    app.include_router(sync_router)


# ── /device — minimal HTML mirror of the TTY device dashboard ─────────────────

@app.get("/device", response_class=HTMLResponse)
def device_page() -> str:
    """Same info as the tty1 dashboard, viewable from any browser on the LAN.

    Auto-refreshes the JSON every 4 s. Has a "Switch to console mode" button
    and a wifi add form so an operator with only a phone can fix connectivity.
    """
    return _DEVICE_HTML


_DEVICE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Hosaka — device mode</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body { font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
         background: #0b0b14; color: #e6e6e6; margin: 0; padding: 16px;
      max-width: 920px; }
  h1 { color: #f5b042; font-size: 18px; margin: 0 0 4px; letter-spacing: 1px; }
  .sub { color: #888; margin-bottom: 16px; }
  .card { border: 1px solid #222; border-radius: 6px; padding: 12px 14px;
          margin: 12px 0; background: #11111c; }
  .card h2 { font-size: 12px; letter-spacing: 1px; color: #6cf;
             margin: 0 0 8px; text-transform: uppercase; }
  .row { display: grid; grid-template-columns: 110px 1fr; gap: 4px 12px; }
  .row span:first-child { color: #777; }
  .row span.v { color: #fff; word-break: break-all; }
  .ok { color: #6f6; } .bad { color: #f66; } .warn { color: #fb6; }
  button, input { font: inherit; }
  button { background: #1d2630; color: #f5b042; border: 1px solid #2c3a48;
           padding: 8px 14px; border-radius: 4px; cursor: pointer; }
  button.danger { color: #f66; border-color: #582; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  input { background: #0a0a12; color: #fff; border: 1px solid #333;
          padding: 8px 10px; border-radius: 4px; width: 100%; box-sizing: border-box; }
  form { display: grid; gap: 8px; margin-top: 8px; }
  ul { padding-left: 16px; margin: 0; }
  a { color: #6cf; }
  .hint { color: #888; font-size: 12px; margin-top: 6px; }
    details { border-top: 1px solid #222; margin-top: 8px; padding-top: 8px; }
    summary { color: #f5b042; cursor: pointer; }
    pre { overflow: auto; white-space: pre-wrap; word-break: break-word; margin: 8px 0 0;
                color: #ccc; background: #08080f; border: 1px solid #1b1b28; padding: 8px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
    .meter { height: 8px; background: #07070d; border: 1px solid #222; margin-top: 4px; }
    .meter > span { display:block; height:100%; background: linear-gradient(90deg,#6cf,#f5b042); }
    #terminal-wrap { display: none; margin-top: 10px; }
    #terminal { height: 260px; overflow: auto; padding: 10px; background: #050508; color: #d6ffd6;
                            border: 1px solid #273827; white-space: pre-wrap; word-break: break-word; }
    #terminal-input { margin-top: 8px; }
</style></head><body>
<h1>HOSAKA · device mode</h1>
<div class="sub" id="ts">loading diagnostics…</div>

<div class="grid">
    <div class="card"><h2>network</h2><div class="row" id="net"></div><details><summary>interfaces + wifi</summary><pre id="net-extra"></pre></details></div>
    <div class="card"><h2>system</h2><div class="row" id="sys"></div><details><summary>mounts</summary><pre id="mounts"></pre></details></div>
    <div class="card"><h2>peripherals</h2><div class="row" id="peripherals"></div><details open><summary>audio / video / usb / bluetooth</summary><pre id="peripheral-extra"></pre></details></div>
    <div class="card"><h2>services</h2><ul id="svcs"></ul></div>
    <div class="card"><h2>urls</h2><ul id="urls"></ul></div>
</div>

<div class="card"><h2>plain terminal</h2>
    <button id="shell-toggle">open shell</button>
    <div class="hint">available only when the server allows the guarded device shell. loopback by default.</div>
    <div id="terminal-wrap">
        <div id="terminal" role="log" aria-live="polite"></div>
        <input id="terminal-input" placeholder="type command, press enter" autocomplete="off">
    </div>
</div>

<div class="card"><h2>wifi — add network</h2>
  <form id="wifi-form">
    <input name="ssid" placeholder="SSID (e.g. Cafe Free WiFi)" required>
    <input name="psk"  placeholder="password (leave blank for open)" type="password">
    <button type="submit">connect</button>
    <div class="hint" id="wifi-status"></div>
  </form>
</div>

<div class="card"><h2>mode</h2>
  <button id="to-console" class="danger">switch to console mode</button>
  <div class="hint">stops this dashboard, starts kiosk on the touchscreen.</div>
</div>

<script>
async function j(url, opts) {
  const r = await fetch(url, Object.assign({headers:{'Accept':'application/json'}}, opts||{}));
  if (!r.ok) throw new Error(url + ' -> ' + r.status);
  return r.json();
}
function row(el, k, v, cls) {
  el.insertAdjacentHTML('beforeend',
    '<span>'+k+'</span><span class="v '+(cls||'')+'">'+(v??'—')+'</span>');
}
function textLines(lines) { return Array.isArray(lines) ? lines.join('\n') : String(lines || ''); }
function svcClass(active) { return active ? 'ok' : 'bad'; }
async function refresh() {
  try {
        const d = await j('/api/v1/diag/snapshot');
        const s = d.system;
        const n = d.network;
        const p = d.peripherals || {};
        const primary = n.primary || {};
    document.getElementById('ts').textContent =
            d.hostname + ' · ' + d.mode + ' · uptime ' + Math.round(s.uptime_seconds/60) + ' min · ' + new Date().toLocaleTimeString();
    const net = document.getElementById('net'); net.innerHTML='';
        row(net,'ip',       primary.ip);
        row(net,'iface',    primary.iface);
        row(net,'ssid',     primary.ssid);
        row(net,'mac',      primary.mac);
        row(net,'tailscale',primary.tailscale_ip);
        document.getElementById('net-extra').textContent =
            'interfaces\n' + textLines((n.interfaces||[]).map(x => JSON.stringify(x))) + '\n\nwifi\n' + textLines(n.wifi_visible||[]) + '\n\nnmcli\n' + textLines(n.nmcli_devices||[]);
    const sys = document.getElementById('sys'); sys.innerHTML='';
        row(sys,'mode', s.mode, s.mode==='device'?'warn':'ok');
        row(sys,'platform', s.platform);
    row(sys,'cpu temp', s.cpu_temp_c==null?null:(s.cpu_temp_c+' °C'));
    row(sys,'memory', s.mem.used_mb+' / '+s.mem.total_mb+' MB  (free '+s.mem.available_mb+')');
    row(sys,'swap',   s.mem.swap_used_mb+' MB');
        row(sys,'disk /', s.disk_root.used_gb+' / '+s.disk_root.total_gb+' GB ('+s.disk_root.used_percent+'%)');
        row(sys,'ports',  n.listening_ports.join(', '));
        document.getElementById('mounts').textContent = textLines((s.mounts||[]).map(x => `${x.mount}  ${x.used}/${x.size}  ${x.use_percent}  ${x.filesystem}`));
        const per = document.getElementById('peripherals'); per.innerHTML='';
        row(per,'audio', p.audio?.available ? 'detected' : 'browser / unavailable', p.audio?.available ? 'ok' : 'warn');
        row(per,'video', p.video?.available ? 'detected' : 'browser / unavailable', p.video?.available ? 'ok' : 'warn');
        row(per,'usb', p.usb?.available ? 'detected' : 'unavailable', p.usb?.available ? 'ok' : 'warn');
        row(per,'bluetooth', p.bluetooth?.available ? 'detected' : 'unavailable', p.bluetooth?.available ? 'ok' : 'warn');
        row(per,'battery', p.battery?.available ? 'detected' : 'not present', p.battery?.available ? 'ok' : 'warn');
        document.getElementById('peripheral-extra').textContent = JSON.stringify(p, null, 2);
    const sv = document.getElementById('svcs'); sv.innerHTML='';
    s.services.forEach(x => sv.insertAdjacentHTML('beforeend',
            '<li><span class="'+svcClass(x.active)+'">'+(x.active?'●':'○')+'</span> '+x.name+' — '+x.sub+'</li>'));
    const u = document.getElementById('urls'); u.innerHTML='';
        Object.entries(n.urls).forEach(([k,v]) => u.insertAdjacentHTML('beforeend',
      '<li>'+k+' · <a href="'+v+'">'+v+'</a></li>'));
  } catch(e) { document.getElementById('ts').textContent = 'error: '+e.message; }
}

let shellSocket = null;
const term = document.getElementById('terminal');
const shellWrap = document.getElementById('terminal-wrap');
const shellInput = document.getElementById('terminal-input');
function shellWrite(text) { term.textContent += text; term.scrollTop = term.scrollHeight; }
document.getElementById('shell-toggle').addEventListener('click', () => {
    if (shellSocket) { shellSocket.close(); shellSocket = null; shellWrap.style.display='none'; return; }
    shellWrap.style.display='block'; term.textContent='connecting…\n';
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    shellSocket = new WebSocket(proto + '//' + location.host + '/ws/device-shell');
    shellSocket.onopen = () => { term.textContent=''; shellInput.focus(); };
    shellSocket.onmessage = (ev) => shellWrite(ev.data);
    shellSocket.onclose = (ev) => { shellWrite('\n[shell closed '+(ev.reason||ev.code)+']\n'); shellSocket = null; };
    shellSocket.onerror = () => shellWrite('\n[shell error]\n');
});
shellInput.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' || !shellSocket) return;
    shellSocket.send(shellInput.value + '\n');
    shellInput.value='';
});
document.getElementById('wifi-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const status = document.getElementById('wifi-status');
  status.textContent = 'connecting…';
  try {
    const r = await j('/api/v1/wifi/networks', {
      method:'POST',
      headers:{'Content-Type':'application/json','Accept':'application/json'},
      body: JSON.stringify({ssid: f.get('ssid'), psk: f.get('psk') || null}),
    });
    status.textContent = (r.ok?'✓ ':'✗ ') + r.message;
    if (r.ok) ev.target.reset();
  } catch(e) { status.textContent = '✗ ' + e.message; }
});
document.getElementById('to-console').addEventListener('click', async () => {
  if (!confirm('Switch this Pi to console mode? The kiosk will start and this page will become read-only.')) return;
  try {
    await j('/api/v1/mode', {
      method:'POST',
      headers:{'Content-Type':'application/json','Accept':'application/json'},
      body: JSON.stringify({mode:'console', persist:true}),
    });
    alert('Mode change requested. Reload in ~5 s.');
  } catch(e) { alert('failed: '+e.message); }
});
refresh();
setInterval(refresh, 4000);
</script>
</body></html>"""


def _device_shell_allowed(websocket: WebSocket) -> tuple[bool, str]:
    """Gate the interactive PTY: never in public mode; default to loopback + device mode."""
    if PUBLIC_MODE or not SHELL_ENABLED:
        return False, "local shell disabled"
    try:
        from hosaka.web.api_v1 import _read_mode as _api_read_mode
        if _api_read_mode() != "device" and not _env_flag("HOSAKA_DEVICE_SHELL_ALWAYS", False):
            return False, "shell only available in device mode"
    except Exception as exc:  # noqa: BLE001
        return False, f"mode check failed: {exc}"

    allow_lan = _env_flag("HOSAKA_DEVICE_SHELL_LAN", False)
    host = websocket.client.host if websocket.client else ""
    if not allow_lan and host not in {"127.0.0.1", "::1", "localhost"}:
        return False, "shell limited to loopback; set HOSAKA_DEVICE_SHELL_LAN=1 to allow LAN"
    return True, ""


@app.websocket("/ws/device-shell")
async def device_shell_ws(websocket: WebSocket) -> None:
    ok, reason = _device_shell_allowed(websocket)
    if not ok:
        await websocket.close(code=1008, reason=reason[:120])
        return

    await websocket.accept()
    master_fd, slave_fd = pty.openpty()
    env = _picoclaw_env()
    env.setdefault("TERM", "xterm-256color")
    cwd = SHELL_CWD if SHELL_CWD.exists() else Path.cwd()
    proc: subprocess.Popen[bytes] | None = None
    loop = asyncio.get_running_loop()

    try:
        proc = subprocess.Popen(
            [_shell_bin(), "-l"],
            cwd=str(cwd),
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
        )
        os.close(slave_fd)

        async def read_pty() -> None:
            while proc and proc.poll() is None:
                try:
                    data = await loop.run_in_executor(None, os.read, master_fd, 2048)
                except OSError:
                    break
                if not data:
                    break
                await websocket.send_text(data.decode("utf-8", errors="replace"))

        async def write_pty() -> None:
            while proc and proc.poll() is None:
                try:
                    message = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                except Exception:
                    break
                try:
                    os.write(master_fd, message.encode("utf-8", errors="replace"))
                except OSError:
                    break

        done, pending = await asyncio.wait(
            {asyncio.create_task(read_pty()), asyncio.create_task(write_pty())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            with suppress(Exception):
                task.result()
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


# ── /api/health ───────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> JSONResponse:
    from hosaka.llm.openai_adapter import is_available as openai_ok
    from hosaka.llm.gateway.client import PicoclawGatewayClient

    ui_built = False
    if UI_DIR.exists():
        try:
            ui_built = any(UI_DIR.iterdir())
        except OSError:
            pass

    return JSONResponse({
        "web": "ok",
        "commit": os.environ.get("HOSAKA_COMMIT", "dev"),
        "picoclaw_bin": _picoclaw_available(),
        "picoclaw_gateway": PicoclawGatewayClient.is_gateway_reachable(),
        "openai_key": openai_ok(),
        "ui_built": ui_built,
        "beacon": get_registry().local_beacon(),
        "public_mode": PUBLIC_MODE,
        "settings_enabled": SETTINGS_ENABLED,
        "web_panel_enabled": WEB_PANEL_ENABLED,
        "nodes_enabled": NODES_UI_ENABLED,
        "nodes_ui_enabled": NODES_UI_ENABLED,
        "tailscale_api_enabled": TAILSCALE_API_ENABLED,
        "sync_enabled": SYNC_ENABLED,
        "inbox_enabled": INBOX_ENABLED,
    })


# ── /api/llm-key  (LLM provider config — never returns the key itself) ─────────

@app.get("/api/llm-key")
def get_llm_key() -> JSONResponse:
    """Return LLM provider metadata (provider, model, base_url) — never the key."""
    from hosaka.llm.llm_config import load as _llm_load
    cfg = _llm_load()
    env_key = bool(os.environ.get("OPENAI_API_KEY"))
    return JSONResponse({
        "provider":   cfg.get("provider", "openai"),
        "model":      cfg.get("model") or os.environ.get("OPENAI_MODEL", ""),
        "base_url":   cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL", ""),
        "configured": bool(cfg.get("api_key")) or env_key,
    })


@app.patch("/api/llm-key")
async def patch_llm_key(request: Request) -> JSONResponse:
    """Store provider/model/api_key/base_url and apply immediately."""
    from hosaka.llm.llm_config import apply_to_env as _llm_apply, load as _llm_load, save as _llm_save
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    cfg = _llm_load()
    for field in ("provider", "model", "api_key", "base_url"):
        if field in body and body[field] is not None:
            cfg[field] = str(body[field])
    _llm_save(cfg)
    _llm_apply(cfg)
    return JSONResponse({"ok": True})


# ── /api/config  (system settings — hostname, backend, picoclaw) ─────────────

@app.get("/api/config")
def get_config() -> JSONResponse:
    """Return persisted system config (hostname, backend endpoint, picoclaw toggle)."""
    s = orchestrator.summary()
    return JSONResponse({
        "hostname": s.get("hostname", ""),
        "backend_endpoint": s.get("backend_endpoint", ""),
        "picoclaw_enabled": bool(s.get("picoclaw_enabled", False)),
    })


@app.patch("/api/config")
async def patch_config(request: Request) -> JSONResponse:
    """Update system config fields — JSON body, all fields optional."""
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    if "hostname" in body:
        orchestrator.set_field("hostname", str(body["hostname"]))
    if "backend_endpoint" in body:
        orchestrator.set_field("backend_endpoint", str(body["backend_endpoint"]))
    if "picoclaw_enabled" in body:
        enabled = bool(body["picoclaw_enabled"])
        orchestrator.set_field("picoclaw_enabled", enabled)
        orchestrator.set_field("picoclaw_ready", enabled)
    return JSONResponse({"ok": True})


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
    ready, reason = _picoclaw_readiness()
    if ready:
        session_key = str(uuid.uuid4())[:8]
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        async for chunk in _run_picoclaw(last[:MSG_MAX_CHARS], session_key):
            tokens.append(chunk)
    else:
        tokens.append(_picoclaw_not_ready_reply(reason))

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

    picoclaw_ok, picoclaw_reason = _picoclaw_readiness()
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

            if payload.get("type") == "shell":
                cmd = str(payload.get("cmd", "")).strip()
                if not _check_rate(remote):
                    await ws.send_json({"type": "error", "error": "rate_limited"})
                    continue
                if busy:
                    await ws.send_json({"type": "error", "error": "busy"})
                    continue
                busy = True
                try:
                    result = await _run_local_shell(cmd)
                    await ws.send_json({"type": "shell_reply", **result})
                finally:
                    busy = False
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
            log.info("agent ws message sid=%s chars=%d", sid, len(message))
            await ws.send_json({"type": "thinking"})

            reply_chunks: list[str] = []
            try:
                picoclaw_ok, picoclaw_reason = _picoclaw_readiness()
                if picoclaw_ok:
                    async for chunk in _run_picoclaw(message, sid):
                        reply_chunks.append(chunk)
                else:
                    log.info("agent ws picoclaw not ready sid=%s reason=%s", sid, picoclaw_reason)
                    reply_chunks.append(_picoclaw_not_ready_reply(picoclaw_reason))

                reply = "".join(reply_chunks)
                log.info("agent ws reply sid=%s chars=%d", sid, len(reply))
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
        "Run `cd frontend && npm ci && npm run build` (output goes to hosaka/web/ui/). "
        "Setup wizard available at /setup/",
        UI_DIR,
    )

    @app.get("/", response_class=HTMLResponse)
    def root_fallback() -> str:
        body = """
        <h1>Hosaka — UI not built yet</h1>
        <p>Run <code>cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</code> (writes <code>hosaka/web/ui/</code>).</p>
        <p><a href='/setup/'>Setup wizard</a> &nbsp;&nbsp; <a href='/api/health'>Health</a></p>
        """
        return _layout("Hosaka", body)
