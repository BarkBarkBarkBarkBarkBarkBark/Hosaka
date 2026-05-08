"""Smoke for hosaka.web.manual_api — /suggest, /manual, /manual/{id}, /features."""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
yaml = pytest.importorskip("yaml")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _boot(tmp_path: Path):
    catalog = tmp_path / "features.yaml"
    catalog.write_text(
        yaml.safe_dump(
            {
                "features": [
                    {
                        "id": "device.health",
                        "name": "Device Health",
                        "category": "device",
                        "status": "stable",
                        "commands": ["/health"],
                        "baller_command": "/health now",
                        "why_you_care": "see if pi is alive",
                    },
                    {
                        "id": "network.wifi",
                        "name": "Wifi",
                        "category": "network",
                        "status": "stable",
                        "commands": ["/wifi"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "device.health.md").write_text("# device health\n\nliveness check.\n", encoding="utf-8")

    agent_ctx = tmp_path / "agent_context.json"
    agent_ctx.write_text(
        json.dumps({"schema_version": "1", "features": [{"id": "device.health"}]}),
        encoding="utf-8",
    )

    db = tmp_path / "events.db"
    for k in [k for k in os.environ if k.startswith("HOSAKA_")]:
        del os.environ[k]
    os.environ["HOSAKA_OBS"] = "on"
    os.environ["HOSAKA_OBS_DB"] = str(db)
    os.environ["HOSAKA_FEATURES_YAML"] = str(catalog)
    os.environ["HOSAKA_MANUAL_DIR"] = str(manual_dir)
    os.environ["HOSAKA_AGENT_CTX"] = str(agent_ctx)

    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs") or mod.startswith("hosaka.web.manual_api"):
            del sys.modules[mod]

    importlib.import_module("hosaka.obs")
    manual_api = importlib.import_module("hosaka.web.manual_api")
    app = FastAPI()
    app.include_router(manual_api.router)
    return TestClient(app)


def test_suggest_endpoint_finds_typo(tmp_path):
    client = _boot(tmp_path)
    r = client.get("/api/v1/suggest", params={"q": "/healht"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["did_you_mean"] == "/health"
    assert body["feature_id"] == "device.health"
    assert "device.health" in body["manual_url"]


def test_manual_index_lists_features(tmp_path):
    client = _boot(tmp_path)
    r = client.get("/api/v1/manual")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    ids = {f["id"] for f in body["features"]}
    assert {"device.health", "network.wifi"} == ids


def test_manual_page_returns_markdown(tmp_path):
    client = _boot(tmp_path)
    r = client.get("/api/v1/manual/device.health")
    assert r.status_code == 200
    assert "device health" in r.text


def test_manual_page_404_includes_suggestion(tmp_path):
    client = _boot(tmp_path)
    r = client.get("/api/v1/manual/devicehealth")  # close but missing
    assert r.status_code == 404
    body = r.json()
    detail = body["detail"]
    assert "suggestion" in detail
    # it should suggest something close
    assert detail["suggestion"]["did_you_mean"] in {"/health", "device health", "device.health", None}


def test_manual_page_path_traversal_rejected(tmp_path):
    client = _boot(tmp_path)
    r = client.get("/api/v1/manual/..%2F..%2Fetc%2Fpasswd")
    # FastAPI normalizes %2F → /, which trips our "/" guard → 400
    assert r.status_code in (400, 404)


def test_features_endpoint_includes_known_commands(tmp_path):
    client = _boot(tmp_path)
    r = client.get("/api/v1/features")
    assert r.status_code == 200
    body = r.json()
    assert "known_commands" in body
    assert "/health" in body["known_commands"]
