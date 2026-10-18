import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hosaka.extensions.manager import Manager
from hosaka.web import api_v1, extensions_api


@pytest.fixture
def api(tmp_path, monkeypatch):
    for name in ("HOSAKA_OPERATOR", "SUDO_USER", "HOSAKA_DATA_DIR", "HOSAKA_GAMES_DIR", "HOSAKA_PSX_ROMS", "HOSAKA_PUBLIC_MODE", "HOSAKA_EXTENSIONS_SAFE_MODE"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    instance = Manager()
    instance.init()
    instance.enable("reference-extension", True)
    monkeypatch.setattr(api_v1, "_load_token", lambda: None)
    app = FastAPI()
    app.include_router(extensions_api.router)
    app.dependency_overrides[extensions_api.manager] = lambda: instance
    return app, instance


def local(app):
    return TestClient(app, base_url="http://127.0.0.1:8421", client=("127.0.0.1", 1234))


def test_dynamic_menu_and_validated_view_need_no_per_package_routes(api):
    app, instance = api
    client = local(app)
    report = client.get("/api/v1/extensions").json()
    assert [entry["id"] for entry in report["extensions"]] == ["reference-extension"]
    assert "path" not in report["extensions"][0]
    view = client.get("/api/v1/extensions/reference-extension/view").json()
    assert view["view"]["version"] == 1
    assert view["actions"]["echo"]["input_keys"] == ["message"]
    assert not view["execution_available"]
    instance.create("second-extension")
    instance.enable("second-extension", True)
    assert len(client.get("/api/v1/extensions").json()["extensions"]) == 2
    instance.enable("reference-extension", False)
    assert [entry["id"] for entry in client.get("/api/v1/extensions").json()["extensions"]] == ["second-extension"]
    assert client.get("/api/v1/extensions/reference-extension/view").status_code == 409


def test_real_action_success_persistence_and_controlled_failure(api):
    if os.geteuid() == 0:
        pytest.skip("Root execution is intentionally refused.")
    app, instance = api
    instance.trust("reference-extension", allow_storage=True)
    client = local(app)
    digest = client.get("/api/v1/extensions/reference-extension/view").json()["digest"]
    def invoke(action, params):
        return client.post(f"/api/v1/extensions/reference-extension/actions/{action}", json={
            "invocation_id": str(uuid4()), "digest": digest, "params": params,
        })
    assert invoke("save", {"message": "<script>not executable</script>"}).json()["ok"]
    loaded = invoke("load", {})
    assert loaded.status_code == 200 and loaded.json()["result"]["message"] == "<script>not executable</script>"
    failed = invoke("fail", {})
    assert failed.status_code == 200 and not failed.json()["ok"]
    assert invoke("echo", {"message": 1}).status_code == 422
    assert invoke("missing", {}).status_code == 404


def test_unapproved_action_is_denied_and_body_is_bounded(api):
    app, instance = api
    client = local(app)
    body = {"invocation_id": str(uuid4()), "digest": "0" * 64, "params": {}}
    response = client.post("/api/v1/extensions/reference-extension/actions/load", json=body)
    assert response.status_code == 403 and not response.json()["ok"]
    assert not (instance.root / "extension-data/reference-extension").exists()
    assert client.post("/api/v1/extensions/reference-extension/actions/load", content="x" * 33000).status_code == 413
    assert client.post("/api/v1/extensions/reference-extension/actions/load", json={"params": {}}).status_code == 422


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:12345"])
def test_cross_origin_requests_are_blocked(api, origin):
    app, _ = api
    assert local(app).get("/api/v1/extensions", headers={"origin": origin}).status_code == 403


def test_public_dns_rebinding_and_remote_auth_fail_closed(api, monkeypatch):
    app, _ = api
    assert local(app).get("/api/v1/extensions", headers={"host": "evil.example", "origin": "http://evil.example"}).status_code == 403
    remote = TestClient(app, base_url="http://deck.example", client=("192.168.1.10", 1234))
    assert remote.get("/api/v1/extensions").status_code == 403
    monkeypatch.setattr(api_v1, "_load_token", lambda: "test-token")
    assert remote.get("/api/v1/extensions", headers={"authorization": "Bearer wrong"}).status_code == 401
    assert remote.get("/api/v1/extensions", headers={"authorization": "Bearer test-token"}).status_code == 200
    monkeypatch.setenv("HOSAKA_PUBLIC_MODE", "1")
    assert local(app).get("/api/v1/extensions").status_code == 403


def test_api_does_not_expose_trust_or_enablement_mutations(api):
    app, _ = api
    client = local(app)
    assert client.post("/api/v1/extensions/reference-extension/trust", json={}).status_code == 404
    assert client.post("/api/v1/extensions/reference-extension/enable", json={}).status_code == 404


def test_cancel_endpoint_cancels_a_real_invocation(api):
    if os.geteuid() == 0:
        pytest.skip("Root execution is intentionally refused.")
    app, instance = api
    source = instance.packages / "reference-extension/main.py"
    source.write_text("""import time
def run(action, params, context):
 context.write_data('started', 'yes')
 time.sleep(8)
 return {'success': True, 'message': 'finished', 'error': None, 'rows': []}
""")
    instance.trust("reference-extension", allow_storage=True)
    client = local(app)
    digest = client.get("/api/v1/extensions/reference-extension/view").json()["digest"]
    invocation = str(uuid4())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, "/api/v1/extensions/reference-extension/actions/load", json={
            "invocation_id": invocation, "digest": digest, "params": {},
        })
        started = instance.root / "extension-data/reference-extension/started"
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists()
        response = client.post(f"/api/v1/extensions/reference-extension/cancel/{invocation}", json={})
        assert response.status_code == 200 and response.json()["cancel_requested"]
        completed = future.result(timeout=3)
        assert completed.status_code == 409
        assert completed.json()["error"]["code"] == "cancelled"


def test_action_body_is_documented_in_openapi(api):
    app, _ = api
    operation = local(app).get("/openapi.json").json()["paths"]["/api/v1/extensions/{identifier}/actions/{action}"]["post"]
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    assert set(body["required"]) == {"invocation_id", "digest", "params"}
