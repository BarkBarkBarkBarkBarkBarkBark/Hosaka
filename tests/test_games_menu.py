from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hosaka import games
from hosaka.web import games_api
from hosaka.web.api_v1 import require_auth, require_write


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("HOSAKA_PUBLIC_MODE", raising=False)
    app = FastAPI()
    app.include_router(games_api.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_write] = lambda: None
    with TestClient(app) as client:
        yield client


def test_menu_uses_psx_catalog_and_exact_title(client, monkeypatch):
    calls = []

    def play(*args, **kwargs):
        calls.append(args)
        if args == ("list", "psx"):
            return {"ok": True, "games": [
                {"title": "Spyro", "system": "psx"}, {"title": "Crash Bandicoot", "system": "psx"},
                {"title": "Spyro", "system": "psx"},
            ]}
        return {"ok": True, "action": "launch", "title": args[0]}

    monkeypatch.setattr(games_api, "run_play", play)
    assert client.get("/api/v1/games").json() == {"games": [{"title": "Crash Bandicoot"}, {"title": "Spyro"}]}
    result = client.post("/api/v1/games/launch", json={"title": "Spyro"})
    assert result.status_code == 200
    assert "RetroArch" in result.json()["message"]
    assert calls == [("list", "psx"), ("list", "psx"), ("Spyro",)]
    assert client.post("/api/v1/games/launch", json={"title": "Pong"}).status_code == 404


@pytest.mark.parametrize("payload", [
    {"ok": False, "error": "play not installed"},
    {"ok": True, "games": None},
    {"ok": True, "games": [{"title": "Pong", "system": "nes"}]},
    {"ok": True, "games": [{"title": ""}]},
])
def test_menu_does_not_fake_catalog_success(client, monkeypatch, payload):
    monkeypatch.setattr(games_api, "run_play", lambda *a, **k: payload)
    assert client.get("/api/v1/games").status_code == 502


def test_empty_catalog_and_public_boundary(client, monkeypatch):
    monkeypatch.setattr(games_api, "run_play", lambda *a, **k: {"ok": True, "games": []})
    assert client.get("/api/v1/games").json() == {"games": []}
    monkeypatch.setenv("HOSAKA_PUBLIC_MODE", "1")
    assert client.get("/api/v1/games").status_code == 403
    assert client.post("/api/v1/games/stop", json={}).status_code == 403


@pytest.mark.parametrize("payload,status", [
    ({"ok": False, "action": "ambiguous"}, 409),
    ({"ok": False, "error": "Missing RetroArch core"}, 502),
    ({"ok": True, "action": "unknown"}, 502),
])
def test_launch_requires_confirmation(client, monkeypatch, payload, status):
    monkeypatch.setattr(games_api, "run_play", lambda *a, **k:
                        {"ok": True, "games": [{"title": "Spyro"}]} if a == ("list", "psx") else payload)
    assert client.post("/api/v1/games/launch", json={"title": "Spyro"}).status_code == status


@pytest.mark.parametrize("title", ["", "x" * 257, "word\x07word"])
def test_launch_validates_title(client, title):
    assert client.post("/api/v1/games/launch", json={"title": title}).status_code == 422


def test_stop_command(client, monkeypatch):
    calls = []
    monkeypatch.setattr(games_api, "run_play", lambda *a, **k: calls.append(a) or {"ok": True, "message": "Stopped"})
    assert client.post("/api/v1/games/stop", json={}).json()["message"] == "Stopped"
    assert calls == [("stop",)]


def test_real_play_json_command(tmp_path, monkeypatch):
    launcher = tmp_path / "play"
    launcher.write_text("#!/bin/sh\nprintf '%s\\n' '{\"ok\":true,\"games\":[]}'\n")
    launcher.chmod(0o755)
    monkeypatch.setenv("HOSAKA_PLAY", str(launcher))
    assert games.play_argv("list", "psx") == [str(launcher), "--json", "list", "psx"]
    assert games.run_play("list", "psx") == {"ok": True, "games": []}
    assert games.play_env()["PLAY_FOREGROUND"] == "0"

def test_operator_catalog_takes_priority_over_system_play(tmp_path, monkeypatch):
    local = tmp_path / "bin/play"
    local.parent.mkdir()
    local.write_text("#!/bin/sh\n")
    monkeypatch.delenv("HOSAKA_PLAY", raising=False)
    monkeypatch.setattr(games, "play_home", lambda: tmp_path)
    monkeypatch.setattr(games.shutil, "which", lambda _: "/usr/bin/play")
    assert games.play_argv("list", "psx")[0] == str(local)


def test_nonzero_ambiguous_response_is_preserved(tmp_path, monkeypatch):
    launcher = tmp_path / "play"
    launcher.write_text("#!/bin/sh\nprintf '%s\\n' '{\"ok\":false,\"action\":\"ambiguous\"}'\nexit 2\n")
    launcher.chmod(0o755)
    monkeypatch.setattr(games, "play_home", Path.home)
    monkeypatch.setenv("HOSAKA_PLAY", str(launcher))
    assert games.run_play("Spyro") == {"ok": False, "action": "ambiguous"}


def test_play_timeout_is_not_a_success(monkeypatch):
    calls = []

    class Process:
        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("play", timeout)
            calls.append("reaped")
            return "", ""

        def kill(self):
            calls.append("killed")

    monkeypatch.setenv("HOSAKA_PLAY", "/bin/sh")
    monkeypatch.setattr(games.subprocess, "Popen", lambda *a, **k: Process())
    result = games.run_play("Spyro", wait_s=1)
    assert result["ok"] is False
    assert "not confirmed" in result["error"]
    assert calls == ["killed", "reaped"]


def test_play_nonzero_exit_cannot_report_success(tmp_path, monkeypatch):
    launcher = tmp_path / "play"
    launcher.write_text("#!/bin/sh\nprintf '%s\\n' " + repr(json.dumps({"ok": True, "action": "launch"})) + "\nexit 1\n")
    launcher.chmod(0o755)
    monkeypatch.setenv("HOSAKA_PLAY", str(launcher))
    assert games.run_play("Spyro")["ok"] is False
