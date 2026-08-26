"""Live voice diagnostics: ring buffer, status file, tiny HTTP panel."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PORT = int(os.getenv("HOSAKA_VOICE_DEBUG_PORT", "8788"))
STATUS_PATH = Path(os.getenv("HOSAKA_VOICE_STATUS", str(Path.home() / ".hosaka" / "voice-status.txt")))
_BARS = " ▁▂▃▄▅▆▇█"

_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>hosaka voice</title>
<style>
  body { font: 14px/1.4 ui-monospace, Menlo, Consolas, monospace; background:#0b0d10; color:#c8d0d8; margin:24px; }
  h1 { font-size:14px; font-weight:600; color:#7ee0c8; letter-spacing:.08em; text-transform:uppercase; }
  .row { display:flex; gap:24px; flex-wrap:wrap; }
  .card { flex:1; min-width:280px; border:1px solid #1e262e; padding:12px 14px; }
  .k { color:#6a7680; }
  .v { color:#e8eef2; }
  .wave { font-size:18px; letter-spacing:1px; color:#7ee0c8; white-space:pre; }
  pre { max-height:420px; overflow:auto; color:#9aa8b3; }
  .hi { color:#ffb454; }
</style>
<h1>hosaka voice</h1>
<div class="row">
  <div class="card">
    <div class="wave" id="wave"></div>
    <p><span class="k">state</span> <span class="v" id="state"></span>
       <span class="k">rms</span> <span class="v" id="rms"></span>
       <span class="k">energy</span> <span class="v" id="energy"></span></p>
    <p><span class="k">busy</span> <span class="v" id="busy"></span>
       <span class="k">speak</span> <span class="v" id="speaking"></span>
       <span class="k">game</span> <span class="v" id="game"></span></p>
    <p><span class="k">rt</span> <span class="v" id="rt"></span></p>
    <p><span class="k">you</span> <span class="v" id="you"></span></p>
    <p><span class="k">bot</span> <span class="v" id="agent"></span></p>
    <p><span class="k">tool</span> <span class="hi" id="tool"></span></p>
    <p><span class="k">hint</span> <span class="v" id="hint"></span></p>
  </div>
  <div class="card" style="flex:1.4">
    <div class="k">events</div>
    <pre id="log"></pre>
  </div>
</div>
<script>
const bars = " ▁▂▃▄▅▆▇█";
async function tick() {
  const d = await (await fetch("/api.json")).json();
  const s = d.snap || {};
  const lv = s.levels || [];
  document.getElementById("wave").textContent = lv.map(v => bars[Math.min(8, Math.max(0, v*9|0))]).join("");
  for (const k of ["state","rms","energy","busy","speaking","game","rt","you","agent","tool","hint"]) {
    const el = document.getElementById(k);
    if (el) el.textContent = s[k] ?? "";
  }
  const log = (d.events || []).slice().reverse().map(e => {
    const t = new Date((e.t||0)*1000).toISOString().slice(11,23);
    return t + "  " + e.kind + (e.detail ? "  " + e.detail : "");
  }).join("\\n");
  document.getElementById("log").textContent = log;
}
setInterval(tick, 200);
tick();
</script>
"""


class VoiceTrace:
    def __init__(self, *, maxlen: int = 120) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self.snap: dict[str, Any] = {
            "state": "idle",
            "rms": 0.0,
            "energy": 0.0,
            "levels": [],
            "busy": False,
            "game": False,
            "speaking": False,
            "you": "",
            "agent": "",
            "rt": "",
            "tool": "",
            "hint": "",
        }
        self._lock = threading.Lock()
        self._http: ThreadingHTTPServer | None = None
        self._last_status = 0.0

    def update(self, **fields: Any) -> None:
        with self._lock:
            for key, val in fields.items():
                if key in self.snap:
                    self.snap[key] = val
            now = time.monotonic()
            if now - self._last_status >= 0.12:
                self._last_status = now
                self._write_status()

    def emit(self, kind: str, detail: str = "", **fields: Any) -> None:
        ev = {"t": time.time(), "kind": kind, "detail": detail[:200]}
        with self._lock:
            self.events.append(ev)
            if kind == "rt":
                self.snap["rt"] = detail[:80]
            elif kind == "you":
                self.snap["you"] = detail[:120]
            elif kind == "agent":
                self.snap["agent"] = (self.snap.get("agent") or "") + detail
                self.snap["agent"] = self.snap["agent"][-160:]
            elif kind == "tool":
                self.snap["tool"] = detail[:120]
            elif kind in self.snap and kind not in {"levels"}:
                pass
            for key, val in fields.items():
                if key in self.snap:
                    self.snap[key] = val
            self._write_status()

    def dump(self) -> dict[str, Any]:
        with self._lock:
            return {
                "snap": dict(self.snap),
                "events": list(self.events),
            }

    def _write_status(self) -> None:
        s = self.snap
        levels = s.get("levels") or []
        wave = "".join(_BARS[min(8, max(0, int(v * 9)))] for v in levels)
        rms = float(s.get("rms") or 0)
        energy = float(s.get("energy") or 0)
        lines = [
            f"state    {s.get('state')}   busy={s.get('busy')}  speak={s.get('speaking')}  game={s.get('game')}",
            f"hear     {wave}  rms={rms:.0f}  e={energy:.2f}",
            f"rt       {s.get('rt')}",
            f"you      {s.get('you')}",
            f"bot      {s.get('agent')}",
            f"tool     {s.get('tool')}",
            f"hint     {s.get('hint')}",
            "",
            "events (newest last)",
        ]
        for ev in list(self.events)[-16:]:
            ts = time.strftime("%H:%M:%S", time.localtime(ev["t"]))
            lines.append(f"  {ts}  {ev['kind']:<10} {ev.get('detail','')}")
        try:
            STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def serve(self, port: int = PORT) -> str:
        trace = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/api"):
                    body = json.dumps(trace.dump()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = _PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self._http = httpd
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return f"http://0.0.0.0:{port}/"


TRACE = VoiceTrace()


def lan_urls(port: int = PORT) -> list[str]:
    urls: list[str] = [f"http://127.0.0.1:{port}/"]
    try:
        hostname = socket.gethostname()
        urls.append(f"http://{hostname}:{port}/")
    except OSError:
        pass
    try:
        import subprocess

        for ip in subprocess.check_output(["hostname", "-I"], text=True).split():
            if ip and not ip.startswith("127."):
                urls.append(f"http://{ip}:{port}/")
    except Exception:
        pass
    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    return seen
