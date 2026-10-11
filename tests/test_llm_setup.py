import json
from pathlib import Path

import pytest

from hosaka import llm_setup
from hosaka.secrets import store


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    original = tmp_path / "original" / "config.json"
    original.parent.mkdir()
    original.write_text(json.dumps({
        "version": 2,
        "agents": {"defaults": {"workspace": "workspace", "restrict_to_workspace": True}},
        "model_list": [{"model_name": "existing", "model": "openai/example"}],
    }))
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(original))
    monkeypatch.setenv("HOSAKA_SECRETS_PATH", str(tmp_path / "hosaka" / "secrets.json"))
    return original


@pytest.mark.parametrize("provider,model,target", [
    ("openai", "gpt-4.1", "openai/gpt-4.1"),
    ("anthropic", "claude-sonnet-4-5", "anthropic/claude-sonnet-4-5"),
    ("openai-compatible", "local-model", "openai/local-model"),
])
def test_provider_private_profile(configuration, provider, model, target):
    before = configuration.read_text()
    path = llm_setup.configure(provider, model, "http://localhost:11434/v1", "test-only-key")
    profile = json.loads(path.read_text())
    assert profile["model_list"][0]["model"] == target
    assert profile["model_list"][0]["api_key"] == "test-only-key"
    assert profile["agents"]["defaults"]["restrict_to_workspace"] is True
    assert profile["agents"]["defaults"]["workspace"] == str(configuration.parent / "workspace")
    assert path.stat().st_mode & 0o777 == 0o600
    assert configuration.read_text() == before
    assert store.get("PICOCLAW_MODEL") == "hosaka-user"
    assert store.get("PICOCLAW_CONFIG_PATH") == str(path)


def test_v3_credential_sidecar(configuration):
    config = json.loads(configuration.read_text())
    config["version"] = 3
    configuration.write_text(json.dumps(config))
    path = llm_setup.configure("anthropic", "claude-example", None, "test-key")
    assert "api_key" not in json.loads(path.read_text())["model_list"][0]
    security = path.parent / ".security.yml"
    assert "hosaka-user:0:" in security.read_text()
    assert security.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("base", ["ftp://example.com", "https://user:secret@example.com"])
def test_invalid_endpoint(configuration, base):
    with pytest.raises(ValueError, match="HTTP"):
        llm_setup.configure("openai-compatible", "model", base, "test-key")
    assert not store.json_path().exists()


def test_compatible_requires_endpoint(configuration):
    with pytest.raises(ValueError, match="require"):
        llm_setup.configure("openai-compatible", "model", None, "")


def test_hidden_setup_does_not_print_key(configuration, monkeypatch, capsys):
    monkeypatch.setattr(llm_setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(llm_setup.getpass, "getpass", lambda _: "not-a-real-key")
    assert llm_setup.main(["--provider", "openai", "--model", "gpt-4.1"]) == 0
    assert "not-a-real-key" not in capsys.readouterr().out


def test_noninteractive_key_setup_rejected(configuration, monkeypatch):
    monkeypatch.setattr(llm_setup.sys.stdin, "isatty", lambda: False)
    assert llm_setup.main(["--provider", "anthropic", "--model", "claude-example"]) == 2


def test_no_key_local_setup(configuration):
    assert llm_setup.main(["--provider", "openai-compatible", "--model", "model",
                           "--api-base", "http://localhost:11434/v1", "--no-key"]) == 0


def test_missing_config_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(tmp_path / "missing"))
    assert llm_setup.main(["--provider", "openai-compatible", "--model", "model",
                           "--api-base", "http://localhost:11434/v1", "--no-key"]) == 1
    assert "Cannot read PicoClaw config" in capsys.readouterr().err
