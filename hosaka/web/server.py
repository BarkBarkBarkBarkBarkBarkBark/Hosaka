from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from hosaka.setup.orchestrator import build_default_orchestrator

STATE_PATH_ENV = "HOSAKA_STATE_PATH"
DEFAULT_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))

app = FastAPI(title="Hosaka Setup Web")
orchestrator = build_default_orchestrator(Path(os.getenv(STATE_PATH_ENV)) if os.getenv(STATE_PATH_ENV) else None)


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


@app.get("/", response_class=HTMLResponse)
def setup_home() -> str:
    orchestrator.update_runtime_network()
    summary = orchestrator.summary()
    body = f"""
    <h1>Hosaka Field Terminal Setup</h1>
    <p class='muted'>Terminal remains the primary appliance interface.</p>
    <p>Current step: <strong>{summary['current_step']}</strong> ({summary['step_index']}/{summary['total_steps']})</p>
    <p>Progress: {summary['progress_percent']}%</p>
    <p><a href='/network'>Network Status</a> <a href='/identity'>Device Identity</a> <a href='/backend'>Backend</a> <a href='/workspace'>Workspace</a> <a href='/theme'>Theme</a> <a href='/openclaw'>OpenClaw</a> <a href='/progress'>Progress</a></p>
    """
    return _layout("Hosaka Setup", body)


@app.get("/network", response_class=HTMLResponse)
def network_status() -> str:
    orchestrator.update_runtime_network()
    s = orchestrator.summary()
    body = f"<h2>Network Status</h2><p>Local IP: <strong>{s['local_ip']}</strong></p><p>Tailscale: <strong>{s['tailscale_status']}</strong></p><p><a href='/'>Back</a></p>"
    return _layout("Network", body)


@app.get("/identity", response_class=HTMLResponse)
def device_identity() -> str:
    s = orchestrator.summary()
    body = f"""
    <h2>Device Identity</h2>
    <form method='post' action='/identity'>
      <label>Hostname</label><input name='hostname' value='{s['hostname']}' placeholder='hosaka-field-terminal'/>
      <button type='submit'>Save</button>
    </form><p><a href='/'>Back</a></p>
    """
    return _layout("Identity", body)


@app.post("/identity")
def save_identity(hostname: str = Form(...)) -> RedirectResponse:
    orchestrator.set_field("hostname", hostname)
    return RedirectResponse("/", status_code=303)


@app.get("/backend", response_class=HTMLResponse)
def backend_config() -> str:
    s = orchestrator.summary()
    body = f"""
    <h2>Backend Config (Optional)</h2>
    <form method='post' action='/backend'>
      <label>Endpoint URL</label><input name='backend_endpoint' value='{s['backend_endpoint']}' placeholder='https://api.example.com'/>
      <button type='submit'>Save</button>
    </form><p><a href='/'>Back</a></p>
    """
    return _layout("Backend", body)


@app.post("/backend")
def save_backend(backend_endpoint: str = Form("")) -> RedirectResponse:
    orchestrator.set_field("backend_endpoint", backend_endpoint)
    return RedirectResponse("/", status_code=303)


@app.get("/workspace", response_class=HTMLResponse)
def workspace_config() -> str:
    s = orchestrator.summary()
    body = f"""
    <h2>Workspace Root</h2>
    <form method='post' action='/workspace'>
      <label>Path</label><input name='workspace_root' value='{s['workspace_root']}' />
      <button type='submit'>Save</button>
    </form><p><a href='/'>Back</a></p>
    """
    return _layout("Workspace", body)


@app.post("/workspace")
def save_workspace(workspace_root: str = Form(...)) -> RedirectResponse:
    orchestrator.set_field("workspace_root", workspace_root)
    return RedirectResponse("/", status_code=303)


@app.get("/theme", response_class=HTMLResponse)
def theme_config() -> str:
    s = orchestrator.summary()
    body = f"""
    <h2>Theme</h2>
    <form method='post' action='/theme'>
      <label>Theme (dark/amber/blue)</label><input name='theme' value='{s['theme']}' />
      <button type='submit'>Save</button>
    </form><p><a href='/'>Back</a></p>
    """
    return _layout("Theme", body)


@app.post("/theme")
def save_theme(theme: str = Form(...)) -> RedirectResponse:
    orchestrator.set_field("theme", theme)
    return RedirectResponse("/", status_code=303)


@app.get("/openclaw", response_class=HTMLResponse)
def openclaw_config() -> str:
    s = orchestrator.summary()
    enabled = "yes" if s["openclaw_enabled"] else "no"
    body = f"""
    <h2>OpenClaw Setup</h2>
    <form method='post' action='/openclaw'>
      <label>Enable OpenClaw (yes/no)</label><input name='openclaw_enabled' value='{enabled}' />
      <label>OpenClaw Path</label><input name='openclaw_path' value='{s['openclaw_path']}' />
      <button type='submit'>Save</button>
    </form><p><a href='/'>Back</a></p>
    """
    return _layout("OpenClaw", body)


@app.post("/openclaw")
def save_openclaw(openclaw_enabled: str = Form("yes"), openclaw_path: str = Form("/opt/openclaw")) -> RedirectResponse:
    enabled = openclaw_enabled.strip().lower() not in {"no", "false", "0"}
    orchestrator.set_field("openclaw_enabled", enabled)
    orchestrator.set_field("openclaw_path", openclaw_path)
    orchestrator.set_field("openclaw_ready", enabled and bool(openclaw_path.strip()))
    return RedirectResponse("/", status_code=303)


@app.get("/progress", response_class=JSONResponse)
def progress_status() -> JSONResponse:
    return JSONResponse(orchestrator.summary())


@app.post("/next")
def next_step() -> RedirectResponse:
    orchestrator.next_step()
    return RedirectResponse("/", status_code=303)


@app.post("/back")
def back_step() -> RedirectResponse:
    orchestrator.previous_step()
    return RedirectResponse("/", status_code=303)


@app.get("/complete", response_class=HTMLResponse)
def completion_page() -> str:
    orchestrator.finalize()
    body = "<h2>Setup Complete</h2><p>Return to terminal to enter Hosaka main console.</p><p><a href='/'>Home</a></p>"
    return _layout("Complete", body)
