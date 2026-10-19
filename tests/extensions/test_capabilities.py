from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import time

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hosaka.extensions.manager import Manager
from hosaka.extensions.runner import run
from hosaka.extensions.scheduler import Scheduler
from hosaka.extensions.worker import Context
from hosaka.web.extensions_api import manager as api_manager, router


@pytest.fixture
def managed(tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("Trusted-local approval intentionally refuses root.")
    for name in ("HOSAKA_OPERATOR", "SUDO_USER", "HOSAKA_PUBLIC_MODE", "HOSAKA_EXTENSIONS_SAFE_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOSAKA_DATA_DIR", str(tmp_path / "data"))
    instance = Manager()
    instance.init()
    source = instance.packages / "reference-extension"
    values = yaml.safe_load((source / "extension.yaml").read_text())
    values["permissions"] = {"network": True, "subprocess": False, "filesystem": "data-directory"}
    values["background"] = {"action": "load", "interval_seconds": 15}
    values["limits"]["max_file_bytes"] = 536870912
    (source / "extension.yaml").write_text(yaml.safe_dump(values))
    (source / "main.py").write_text("""
import sqlite3, time
def run(action,params,context):
    if action == 'load':
        time.sleep(.4)
    connection=sqlite3.connect(context.data_path('db.sqlite3'))
    connection.execute('CREATE TABLE IF NOT EXISTS values_table(value TEXT)')
    connection.execute('INSERT INTO values_table VALUES(?)',('x'*300000,))
    connection.commit()
    connection.close()
    try:
        context.require_network()
        network=True
    except PermissionError:
        network=False
    return {'success':True,'message':str(network),'error':None,'rows':[]}
""")
    instance.enable("reference-extension", True)
    return instance


def test_managed_grant_is_required_network_is_optional_and_source_is_not_auto_approved(managed):
    assert not run(managed, "reference-extension", "load", {})["ok"]
    managed.trust("reference-extension", allow_storage=True)
    assert not run(managed, "reference-extension", "load", {})["ok"]
    managed.trust("reference-extension", allow_storage=True, allow_managed_data=True)
    report = run(managed, "reference-extension", "load", {})
    assert report["ok"] and report["result"]["message"] == "False", report
    managed.trust("reference-extension", allow_storage=True, allow_managed_data=True, allow_network=True)
    assert run(managed, "reference-extension", "load", {})["result"]["message"] == "True"
    assert (managed.root / "extension-data/reference-extension/db.sqlite3").stat().st_size > 65536


def test_context_rejects_escape_symlinks_and_ungranted_directory(tmp_path):
    context = Context(tmp_path, True, managed=True)
    for path in ("../outside", "/tmp/outside", "a/../bad", "a\\bad", ""):
        with pytest.raises((ValueError, PermissionError)):
            context.data_path(path)
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        context.data_path("escape/secret")
    with pytest.raises(PermissionError):
        Context(tmp_path, True).data_path("db.sqlite3")


def test_background_requires_grant_and_leaves_foreground_slot(managed):
    managed.trust("reference-extension", allow_storage=True, allow_managed_data=True)
    assert not run(managed, "reference-extension", "load", {}, background=True)["ok"]
    managed.trust("reference-extension", allow_storage=True, allow_managed_data=True, allow_background=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        job = executor.submit(run, managed, "reference-extension", "load", {}, background=True)
        deadline = time.monotonic() + 5
        while not list((managed.root / "state/extension-jobs").glob("*.active")):
            if time.monotonic() > deadline:
                pytest.fail("Background worker did not start")
            time.sleep(.01)
        foreground = run(managed, "reference-extension", "echo", {"message": "foreground"})
        assert foreground["ok"], foreground
        assert job.result()["ok"]
    scheduler = Scheduler()
    scheduler.tick(managed)
    before = dict(scheduler.next_run)
    scheduler.tick(managed)
    assert scheduler.next_run == before
    managed.revoke("reference-extension")
    scheduler.tick(managed)
    assert scheduler.next_run == before


def test_binary_endpoints_require_approval_confine_downloads_and_bound_uploads(managed):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[api_manager] = lambda: managed
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as client:
        assert client.post("/api/v1/extensions/reference-extension/files", content=b"x",
                           headers={"X-Extension-Digest": "0"*64, "X-Extension-Filename": "proof.pdf"}).status_code == 403
        info = managed.trust("reference-extension", allow_storage=True, allow_managed_data=True)
        headers = {"X-Extension-Digest": info["approved_digest"], "X-Extension-Filename": "proof.pdf"}
        response = client.post("/api/v1/extensions/reference-extension/files", content=b"test", headers=headers)
        assert response.status_code == 200, response.text
        token = response.json()["id"]
        root = managed.root / "extension-data/reference-extension"
        assert (root / "uploads" / token).read_bytes() == b"test"
        assert client.post("/api/v1/extensions/reference-extension/files", content=b"x"*(10485761), headers=headers).status_code == 413
        assert len(list((root / "uploads").iterdir())) == 1
        context = Context(root, True, managed=True)
        Path(context.data_path("files/object.pdf")).write_bytes(b"private")
        downloaded = client.get("/api/v1/extensions/reference-extension/files/object.pdf")
        assert downloaded.status_code == 200 and downloaded.content == b"private"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert client.get("/api/v1/extensions/reference-extension/files/db.sqlite3").status_code == 404
        managed.revoke("reference-extension")
        assert client.get("/api/v1/extensions/reference-extension/files/object.pdf").status_code == 403
