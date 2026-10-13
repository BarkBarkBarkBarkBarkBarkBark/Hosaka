import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hosaka import picoclaw_runtime as runtime


@pytest.mark.parametrize("local_first,alias,model", [
    (None, "gpt-4.1", "openai/gpt-4.1"),
    ("1", "qwen2.5", "ollama/qwen2.5:0.5b"),
])
def test_fresh_runtime_defaults_and_repeat_install(tmp_path, monkeypatch, local_first, alias, model):
    monkeypatch.delenv("HOSAKA_LOCAL_FIRST", raising=False)
    if local_first:
        monkeypatch.setenv("HOSAKA_LOCAL_FIRST", local_first)
    runtime.ensure_picoclaw_runtime(home=tmp_path, seed_config=True)
    path = tmp_path / ".picoclaw/config.json"
    config = json.loads(path.read_text())
    assert config["agents"]["defaults"]["model_name"] == alias
    assert config["model_list"][0]["model"] == model
    assert config["tools"]["web"]["prefer_native"] is False
    before = path.read_bytes()
    runtime.ensure_picoclaw_runtime(home=tmp_path, seed_config=True)
    assert path.read_bytes() == before
    assert "api_key" not in config["model_list"][0]


@pytest.mark.parametrize("local_first", ["0", "1"])
def test_update_preserves_explicit_model_and_credentials(tmp_path, monkeypatch, local_first):
    monkeypatch.setenv("HOSAKA_LOCAL_FIRST", local_first)
    path = tmp_path / ".picoclaw/config.json"
    path.parent.mkdir()
    entry = {"model_name": "selected", "model": "openai/custom", "api_key": "test-key"}
    path.write_text(json.dumps({
        "agents": {"defaults": {"model_name": "selected", "restrict_to_workspace": True}},
        "model_list": [entry], "tools": {"web": {"prefer_native": True}},
    }))
    runtime.ensure_picoclaw_runtime(home=tmp_path, seed_config=True)
    config = json.loads(path.read_text())
    assert config["agents"]["defaults"]["model_name"] == "selected"
    assert config["agents"]["defaults"]["restrict_to_workspace"] is True
    assert entry in config["model_list"]
    assert config["tools"]["web"]["prefer_native"] is False


def test_invalid_config_is_not_overwritten(tmp_path):
    path = tmp_path / ".picoclaw/config.json"
    path.parent.mkdir()
    path.write_text("invalid-json")
    with pytest.raises(json.JSONDecodeError):
        runtime.ensure_picoclaw_runtime(home=tmp_path, seed_config=True)
    assert path.read_text() == "invalid-json"


def test_appliance_setup_preserves_saved_provider_and_prepares_both_users(tmp_path, monkeypatch):
    import pwd

    state = tmp_path / "state"
    state.mkdir()
    path = state / "llm.json"
    saved = {"provider": "openai-compatible", "model": "chosen", "api_key": "private"}
    path.write_text(json.dumps(saved))
    monkeypatch.setenv("HOSAKA_STATE_PATH", str(state / "state.json"))
    monkeypatch.setenv("OPENAI_API_KEY", "new-key-must-not-replace-selection")
    monkeypatch.setattr(runtime.os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=123, pw_gid=456, pw_dir="/home/seat"))
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir="/root"))
    owners, commands, homes = [], [], []
    monkeypatch.setattr(runtime.os, "chown", lambda *args: owners.append(args))
    monkeypatch.setattr(runtime.subprocess, "run", lambda command, **kwargs: commands.append((command, kwargs)))
    monkeypatch.setattr(runtime, "ensure_picoclaw_runtime", lambda **kwargs: homes.append(kwargs))
    runtime.configure_appliance_runtime("seat")
    assert json.loads(path.read_text()) == saved
    assert path.stat().st_mode & 0o777 == 0o600
    assert owners == [(state, 123, 456), (path, 123, 456)]
    assert commands[0][0][:4] == ["runuser", "-u", "seat", "--"]
    assert commands[0][0][-3:] == ["--home", "/home/seat", "--seed-config"]
    assert commands[0][1]["check"] is True
    assert homes == [{"home": "/root", "seed_config": True}]


def test_appliance_setup_rejects_unprivileged_run(monkeypatch):
    monkeypatch.setattr(runtime.os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="requires root"):
        runtime.configure_appliance_runtime("operator")


@pytest.mark.parametrize("key", ["", "test-only-key"])
def test_appliance_fresh_setup_persists_openai_and_optional_key(tmp_path, monkeypatch, key):
    import pwd
    from hosaka.llm import llm_config

    state = tmp_path / "state"
    monkeypatch.setenv("HOSAKA_STATE_PATH", str(state / "state.json"))
    monkeypatch.delenv("HOSAKA_LOCAL_FIRST", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setattr(runtime.os, "geteuid", lambda: 0)
    monkeypatch.setattr(runtime.os, "chown", lambda *a: None)
    monkeypatch.setattr(llm_config.os, "fchown", lambda *a: None)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=123, pw_gid=456, pw_dir="/home/seat"))
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir="/root"))
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(runtime, "ensure_picoclaw_runtime", lambda **k: None)
    runtime.configure_appliance_runtime("seat")
    config = json.loads((state / "llm.json").read_text())
    assert config["provider"] == "openai"
    assert config["model"] == "gpt-4.1"
    assert config.get("api_key", "") == key
    assert (state / "llm.json").stat().st_mode & 0o777 == 0o600
