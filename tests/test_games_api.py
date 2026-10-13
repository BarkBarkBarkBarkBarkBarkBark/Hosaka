from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hosaka.web import api_v1, games_api


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(games_api.router)
    app.dependency_overrides[api_v1.require_auth] = lambda: None
    app.dependency_overrides[api_v1.require_write] = lambda: None
    return TestClient(app)


def test_list_returns_catalog_without_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        games_api,
        "run_play",
        lambda *args, **kwargs: {"ok": True, "games": [{"title": "Wipeout", "system": "psx"}]},
    )

    response = _client().get("/api/v1/games")

    assert response.status_code == 200
    game = response.json()["games"][0]
    assert game["title"] == "Wipeout"
    assert "path" not in game


def test_launch_passes_only_id_to_game_manager(monkeypatch) -> None:
    run_play = Mock(
        side_effect=[
            {"ok": True, "games": [{"title": "Wipeout"}]},
            {"ok": True, "action": "launch", "title": "Wipeout"},
        ]
    )
    monkeypatch.setattr(games_api, "run_play", run_play)

    response = _client().post("/api/v1/games/launch", json={"title": "Wipeout"})

    assert response.status_code == 200
    assert run_play.call_args_list == [
        (("list", "psx"), {"wait_s": 45}),
        (("Wipeout",), {"wait_s": 20}),
    ]


def test_launch_rejects_missing_title() -> None:
    response = _client().post("/api/v1/games/launch", json={})

    assert response.status_code == 422