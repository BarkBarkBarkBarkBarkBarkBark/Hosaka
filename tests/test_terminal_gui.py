from __future__ import annotations

import os
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hosaka.web import bluetooth_api, tui_ws
from hosaka.web.api_v1 import require_auth, require_write


def test_uvicorn_has_websocket_transport():
    from uvicorn import Config

    config = Config(FastAPI())
    config.load()
    assert config.ws_protocol_class is not None


def test_menu_orbs_match_terminal_frames():
    from hosaka.tui.style import _ORB_FRAMES

    source = (Path(__file__).resolve().parents[1] / "frontend/src/orb.ts").read_text()
    lines = [json.loads(line) for line in re.findall(r'^\s*(".*"),$', source, re.MULTILINE)]
    assert lines == [line for frame in _ORB_FRAMES for line in frame]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("HOSAKA_PUBLIC_MODE", raising=False)
    monkeypatch.delenv("HOSAKA_TUI_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(tui_ws.router)
    app.include_router(bluetooth_api.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_write] = lambda: None
    with TestClient(app, client=("127.0.0.1", 1234)) as test_client:
        yield test_client


@pytest.mark.parametrize("origin", ["https://example.com", "null", "http://127.0.0.1.evil.test", ""])
def test_tui_rejects_nonlocal_origin(client, origin):
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/ws/tui", headers={"origin": origin}):
            pass
    assert error.value.code == 1008


@pytest.mark.parametrize("setting", ["HOSAKA_PUBLIC_MODE", "HOSAKA_TUI_ENABLED"])
def test_tui_disabled(client, monkeypatch, setting):
    monkeypatch.setenv(setting, "1" if setting == "HOSAKA_PUBLIC_MODE" else "0")
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/ws/tui", headers={"origin": "http://localhost:5173"}):
            pass
    assert error.value.code == 1008


def test_tui_rejects_remote_client():
    app = FastAPI()
    app.include_router(tui_ws.router)
    with TestClient(app, client=("192.168.1.10", 1234)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/tui", headers={"origin": "http://localhost"}):
                pass


def test_invalid_initial_size(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/tui?cols=0", headers={"origin": "http://localhost"}):
            pass


def test_canonical_tui_command(client, monkeypatch):
    calls = []

    async def fake_bridge(ws, command, cols, rows):
        calls.append((command, cols, rows))
        await ws.send_bytes(b"ready")
        await ws.close()

    monkeypatch.setattr(tui_ws, "bridge", fake_bridge)
    with client.websocket_connect("/ws/tui?cols=100&rows=30", headers={"origin": "http://localhost"}) as ws:
        assert ws.receive_bytes() == b"ready"
    command, cols, rows = calls[0]
    assert command[0] == sys.executable
    assert "'-m','hosaka','tui'" in command[2]
    assert "TIOCSCTTY" in command[2]
    assert (cols, rows) == (100, 30)


def test_real_pty_input_resize_and_cleanup():
    app = FastAPI()
    command = [
        sys.executable, "-u", "-c",
        "import os,sys; print('PID',os.getpid(),flush=True);"
        "\nfor line in sys.stdin:"
        "\n print('RESULT',os.get_terminal_size(0).columns,line.strip(),os.environ.get('HOSAKA_TERMINAL_GUI'),flush=True)",
    ]

    @app.websocket("/test")
    async def terminal(ws: WebSocket):
        await ws.accept()
        await tui_ws.bridge(ws, command, 80, 24)

    with TestClient(app) as client:
        with client.websocket_connect("/test") as ws:
            first = ws.receive_bytes().decode()
            pid = int(first.split()[1])
            ws.send_json({"type": "resize", "cols": 120, "rows": 40})
            ws.send_json({"type": "input", "data": "hello 世界\n"})
            output = b""
            while "RESULT 120 hello 世界 1".encode() not in output:
                output += ws.receive_bytes()
            assert "RESULT 120 hello 世界 1" in output.decode()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_invalid_message_closes_pty():
    app = FastAPI()

    @app.websocket("/test")
    async def terminal(ws: WebSocket):
        await ws.accept()
        await tui_ws.bridge(ws, [sys.executable, "-c", "import time; time.sleep(60)"], 80, 24)

    with TestClient(app) as client:
        with client.websocket_connect("/test") as ws:
            ws.send_json({"type": "resize", "cols": 10000})
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_bytes()
            assert error.value.code == 1008


def test_bluetooth_unavailable(client, monkeypatch):
    monkeypatch.setattr(bluetooth_api.shutil, "which", lambda _: None)
    assert client.get("/api/v1/bluetooth/devices").status_code == 501


def test_bluetooth_pair_and_confirm(client, monkeypatch):
    calls = []
    infos = iter(["Paired: no", "Paired: yes", "Connected: yes"])

    def run(command, timeout=8):
        calls.append(command)
        return 0, next(infos) if command[1] == "info" else "succeeded", ""

    monkeypatch.setattr(bluetooth_api.shutil, "which", lambda _: "/usr/bin/bluetoothctl")
    monkeypatch.setattr(bluetooth_api, "_run", run)
    response = client.post("/api/v1/bluetooth/pair", json={"address": "AA:BB:CC:DD:EE:FF"})
    assert response.status_code == 200
    assert response.json()["ok"]
    assert any("pair" in command for command in calls)
    assert any("trust" in command for command in calls)
    assert any("connect" in command for command in calls)


def test_bluetooth_failure_not_success(client, monkeypatch):
    monkeypatch.setattr(bluetooth_api.shutil, "which", lambda _: "/usr/bin/bluetoothctl")
    monkeypatch.setattr(bluetooth_api, "_run", lambda *a, **kw: (0, "Failed to pair", ""))
    assert client.post("/api/v1/bluetooth/pair", json={"address": "AA:BB:CC:DD:EE:FF"}).status_code == 502
    assert client.post("/api/v1/bluetooth/pair", json={"address": "--help"}).status_code == 422


def test_bluetooth_incomplete_pairing_not_success(client, monkeypatch):
    monkeypatch.setattr(bluetooth_api.shutil, "which", lambda _: "/usr/bin/bluetoothctl")
    monkeypatch.setattr(bluetooth_api, "_run", lambda *a, **kw: (0, "Paired: no", ""))
    response = client.post("/api/v1/bluetooth/pair", json={"address": "AA:BB:CC:DD:EE:FF"})
    assert response.status_code == 502
    assert "did not complete" in response.json()["detail"]


def test_bluetooth_scan_and_list(client, monkeypatch):
    def run(command, timeout=8):
        return 0, "Device AA:BB:CC:DD:EE:FF Headphones" if command[1] == "devices" else "succeeded", ""

    monkeypatch.setattr(bluetooth_api.shutil, "which", lambda _: "/usr/bin/bluetoothctl")
    monkeypatch.setattr(bluetooth_api, "_run", run)
    response = client.post("/api/v1/bluetooth/scan", json={})
    assert response.json() == {"devices": [{"address": "AA:BB:CC:DD:EE:FF", "name": "Headphones"}]}


def test_bluetooth_public_disabled(client, monkeypatch):
    monkeypatch.setenv("HOSAKA_PUBLIC_MODE", "1")
    assert client.get("/api/v1/bluetooth/devices").status_code == 403


def test_display_preference_is_persistent(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/hosaka"
    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path))
    def cli(*args):
        return subprocess.run(["bash", str(script), "display", *args], env=env, text=True, capture_output=True, check=True).stdout
    assert cli("show").strip() == "gui"
    cli("gui")
    assert cli("show").strip() == "gui"
    cli("tui")
    assert cli("show").strip() == "tui"


@pytest.mark.parametrize("script", ["scripts/hosaka-lxqt-kiosk.sh", "dotfiles/openbox/autostart"])
def test_graphical_boot_preserves_explicit_tui(tmp_path, script):
    launcher = tmp_path / "bin/hosaka-tui-term"
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\nprintf 'CANONICAL_TUI\\n'\n")
    launcher.chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / ".config"))
    env["HOSAKA_DISPLAY_MODE"] = "tui"
    source = Path(__file__).resolve().parents[1] / script
    if script == "dotfiles/openbox/autostart":
        delegated = tmp_path / "autostart"
        delegated.write_text(source.read_text().replace(
            "/usr/local/bin/hosaka-lxqt-kiosk", str(source.parents[2] / "scripts/hosaka-lxqt-kiosk.sh")))
        source = delegated
    result = subprocess.run(["bash", str(source)], env=env, capture_output=True, text=True, timeout=5, check=True)
    assert result.stdout.strip() == "CANONICAL_TUI"


@pytest.mark.parametrize("script", ["scripts/hosaka-lxqt-kiosk.sh", "dotfiles/openbox/autostart"])
def test_graphical_boot_default_is_gui(tmp_path, script):
    tools = tmp_path / "bin"
    tools.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (state / "mode").write_text("console\n")
    for name in ("curl", "sleep", "xset", "xsetroot", "unclutter"):
        command = tools / name
        command.write_text("#!/bin/sh\nexit 0\n")
        command.chmod(0o755)
    systemctl = tools / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 1\n")
    systemctl.chmod(0o755)
    launcher = tools / "electron"
    launcher.write_text('#!/bin/sh\nprintf "CANONICAL_GUI\\n"\nkill -TERM "$PPID"\n')
    launcher.chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / ".config"),
               HOSAKA_STATE_DIR=str(state), HOSAKA_KIOSK_LAUNCHER=str(launcher),
               HOSAKA_KIOSK_ELECTRON_BIN=str(launcher), HOSAKA_KIOSK_LOG=str(tmp_path / "kiosk.log"),
               HOSAKA_DESKTOP_BRANDING=str(tools / "curl"), PATH=str(tools) + os.pathsep + os.environ["PATH"])
    env.pop("HOSAKA_DISPLAY_MODE", None)
    source = Path(__file__).resolve().parents[1] / script
    if script == "dotfiles/openbox/autostart":
        delegated = tmp_path / "autostart"
        delegated.write_text(source.read_text().replace(
            "/usr/local/bin/hosaka-lxqt-kiosk", str(source.parents[2] / "scripts/hosaka-lxqt-kiosk.sh")))
        source = delegated
    result = subprocess.run(["bash", str(source)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode in (0, -15)
    assert "CANONICAL_GUI" in (tmp_path / "kiosk.log").read_text()


def test_lxqt_autostart_is_enabled():
    entry = Path(__file__).resolve().parents[1] / "dotfiles/autostart/hosaka-kiosk.desktop"
    values = dict(line.split("=", 1) for line in entry.read_text().splitlines() if "=" in line and not line.startswith("#"))
    assert values["Hidden"] == "false"
    assert values["X-GNOME-Autostart-enabled"] == "true"
    assert values["OnlyShowIn"] == "LXQt;"
    assert values["Exec"] == "/usr/local/bin/hosaka-lxqt-kiosk"


@pytest.mark.parametrize("stalled", ["backend", "frontend"])
def test_dev_refuses_occupied_but_unresponsive_ports(tmp_path, stalled):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    lsof = bin_dir / "lsof"
    lsof.write_text("#!/bin/sh\nprintf '12345\\n'\n")
    lsof.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *api/health*) [ \"$STALLED_SERVER\" != backend ] ;;\n"
        "  *) [ \"$STALLED_SERVER\" != frontend ] ;;\n"
        "esac\n"
    )
    curl.chmod(0o755)
    script = Path(__file__).resolve().parents[1] / "scripts/hosaka"
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", STALLED_SERVER=stalled)
    result = subprocess.run(
        ["bash", str(script), "dev", "--web"], env=env,
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode != 0
    assert f"{stalled} port" in result.stderr
    assert "HTTP is unresponsive" in result.stderr
    assert "hosaka dev -fresh" in result.stderr
