"""Regression tests for Picoclaw v2 security overlay handling.

These guard the bug that knocked the Hosaka frontend offline on the field
device: the TUI was writing ``model_list[*].api_key`` into
``~/.picoclaw/config.json``, which Picoclaw v2 rejects with::

    config.json contains unknown field(s): model_list[0].api_key

After the fix, secrets only ever land in ``~/.picoclaw/.security.yml`` and
``config.json`` stays a pure structural / routing file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hosaka import main_console


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Redirect Path.home() so the test can mutate ~/.picoclaw safely."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / ".picoclaw").mkdir()
    return tmp_path


def test_check_api_key_skips_when_env_present(fake_home, monkeypatch, capsys):
    """If OPENAI_API_KEY is in the env, _check_api_key must be a silent no-op."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-env")
    # Ensure no prompt path is reached (would block on stdin).
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    main_console._check_api_key()

    # No file should have been created.
    assert not (fake_home / ".picoclaw" / ".security.yml").exists()
    out = capsys.readouterr().out
    assert "No OpenAI API key" not in out


def test_check_api_key_strips_legacy_api_key_from_config(fake_home, monkeypatch):
    """If config.json carries a legacy api_key field, it must be migrated out."""
    cfg_path = fake_home / ".picoclaw" / "config.json"
    cfg_path.write_text(json.dumps({
        "agents": {"defaults": {"model_name": "gpt-4.1-mini"}},
        "model_list": [
            {
                "model_name": "gpt-4.1-mini",
                "model": "openai/gpt-4.1-mini",
                "api_key": "sk-legacy-inside-config",   # the bug
                "api_base": "https://api.openai.com/v1",
            }
        ],
    }))
    # Pre-seed a key in the env so we don't prompt — we only care about the
    # config.json migration path here.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-already-set")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    main_console._check_api_key()

    cfg = json.loads(cfg_path.read_text())
    for entry in cfg["model_list"]:
        assert "api_key" not in entry, "legacy api_key field must be stripped"
        assert "api_keys" not in entry, "legacy api_keys field must be stripped"


def test_write_picoclaw_security_key_writes_v2_schema(fake_home):
    """The .security.yml file must match Picoclaw v2's overlay schema."""
    target = fake_home / ".picoclaw" / ".security.yml"
    main_console._write_picoclaw_security_key(target, "gpt-4.1-mini", "sk-fresh")

    assert target.exists()
    # Permissions must be 0600 — operator credential.
    mode = target.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    text = target.read_text()
    assert "model_list" in text
    assert "gpt-4.1-mini" in text
    assert "api_keys" in text
    assert "sk-fresh" in text


def test_write_picoclaw_security_key_preserves_other_models(fake_home):
    """Adding a key for one model must not clobber entries for others."""
    target = fake_home / ".picoclaw" / ".security.yml"
    main_console._write_picoclaw_security_key(target, "qwen2.5", "ollama-token")
    main_console._write_picoclaw_security_key(target, "gpt-4.1-mini", "sk-openai")

    text = target.read_text()
    assert "qwen2.5" in text and "ollama-token" in text
    assert "gpt-4.1-mini" in text and "sk-openai" in text


def test_write_picoclaw_security_key_promotes_new_key_to_front(fake_home):
    """Re-running with a new key for the same model must promote it to active.

    Picoclaw v2's ``api_keys`` is a list to support graceful rotation. The
    operative key is the first one, so the only invariant we care about is
    that the most recently written key is at index 0.
    """
    target = fake_home / ".picoclaw" / ".security.yml"
    main_console._write_picoclaw_security_key(target, "gpt-4.1-mini", "sk-old")
    main_console._write_picoclaw_security_key(target, "gpt-4.1-mini", "sk-new")

    import yaml
    data = yaml.safe_load(target.read_text())
    keys = data["model_list"]["gpt-4.1-mini"]["api_keys"]
    assert keys[0] == "sk-new", f"new key must be active (first); got {keys}"
    # The new key must appear exactly once (no accumulation of duplicates on re-run).
    assert keys.count("sk-new") == 1


def test_check_api_key_never_writes_api_key_into_config(fake_home, monkeypatch):
    """End-to-end: config.json must remain credential-free after onboarding flow."""
    cfg_path = fake_home / ".picoclaw" / "config.json"
    cfg_path.write_text(json.dumps({
        "agents": {"defaults": {"model_name": "gpt-4.1-mini"}},
        "model_list": [
            {"model_name": "gpt-4.1-mini", "model": "openai/gpt-4.1-mini"}
        ],
    }))
    # Force the function to take the "prompt for a key" branch by clearing
    # all sources and giving it a TTY plus a fake getpass.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HOSAKA_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "sk-typed-by-operator")

    main_console._check_api_key()

    # config.json untouched at the credential level
    cfg = json.loads(cfg_path.read_text())
    for entry in cfg["model_list"]:
        assert "api_key" not in entry
        assert "api_keys" not in entry

    # .security.yml carries the typed key
    sec = fake_home / ".picoclaw" / ".security.yml"
    assert sec.exists()
    assert "sk-typed-by-operator" in sec.read_text()
