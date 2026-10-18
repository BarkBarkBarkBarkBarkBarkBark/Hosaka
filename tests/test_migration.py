from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from hosaka import migration
from hosaka.llm import llm_config
from hosaka.secrets import store

ROOT = Path(__file__).resolve().parents[1]
SECRET = "private-test-value-never-display"


@pytest.fixture
def home(tmp_path, monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(("HOSAKA_", "PICOCLAW_", "OPENAI_", "ANTHROPIC_")) or name == "SUDO_USER":
            monkeypatch.delenv(name)
    home = tmp_path / "operator home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(llm_config, "_SYSTEM_DIR", tmp_path / "system")
    monkeypatch.setattr(llm_config, "_USER_DIR", home / ".hosaka")
    monkeypatch.setattr(store, "DEFAULT_JSON_PATH", home / ".hosaka/secrets.json")
    monkeypatch.setattr(store, "DEFAULT_ENV_PATH", tmp_path / "system/env")
    monkeypatch.setattr(migration, "CORE_ROOT", tmp_path / "core")
    return home


def write(path: Path, values: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values))
    path.chmod(0o600)
    return path


def pico(path: Path, *, model="openai/gpt-4.1", key=None) -> Path:
    entry = {"model_name": "selected", "model": model}
    if key:
        entry["api_key"] = key
    return write(path, {
        "version": 3, "agents": {"defaults": {"model_name": "selected", "workspace": "workspace"}},
        "model_list": [entry], "unknown": SECRET,
    })


def snapshot(root: Path) -> dict:
    return {
        str(path.relative_to(root)): (
            stat.S_IMODE(path.stat().st_mode),
            path.read_bytes() if path.is_file() else None,
        )
        for path in [root, *root.rglob("*")]
    }


def test_empty_inventory_creates_nothing(home):
    before = snapshot(home)
    report = migration.inventory()
    assert report["status"] == "inventoried"
    assert report["dry_run"] and not report["apply_supported"]
    assert report["effective"]["picoclaw_config"] == str(home / ".picoclaw/config.json")
    assert report["proposed"]["picoclaw_config"] == str(home / ".hosaka/picoclaw/config.json")
    assert snapshot(home) == before


def test_split_layout_preserves_files_modes_environment_and_never_runs_tools(home, monkeypatch):
    write(home / ".hosaka/llm.json", {"provider": "openai", "model": "gpt-4.1", "api_key": SECRET})
    pico(home / ".picoclaw/config.json", key=SECRET)
    write(home / ".picoclaw/workspace/sessions/session.json", {"history": SECRET})
    before, environment = snapshot(home), dict(os.environ)

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only inventory attempted a side effect")

    with monkeypatch.context() as guard:
        guard.setattr(socket, "socket", forbidden)
        guard.setattr(subprocess, "Popen", forbidden)
        guard.setattr(Path, "mkdir", forbidden)
        guard.setattr(Path, "write_text", forbidden)
        guard.setattr(os, "chmod", forbidden)
        guard.setattr(os, "replace", forbidden)
        report = migration.inventory()
    assert snapshot(home) == before
    assert dict(os.environ) == environment
    assert SECRET not in json.dumps(report)
    assert report["effective"]["openai_credential_source"] == "llm.selected"
    assert report["workspaces"]["picoclaw.selected"]["sessions"]["status"] == "present"
    assert report["conflicts"] == []


def test_environment_overrides_and_stored_profile_are_not_applied(home, monkeypatch):
    upstream = pico(home / ".picoclaw/config.json")
    selected = pico(home / "explicit config/config.json", key=SECRET)
    stored = pico(home / "stored config/config.json", model="anthropic/claude-test")
    write(home / ".hosaka/secrets.json", {
        "PICOCLAW_CONFIG_PATH": str(stored), "PICOCLAW_MODEL": "stored-model",
        "OPENAI_API_KEY": "another-private-value",
    })
    monkeypatch.setenv("PICOCLAW_HOME", str(upstream.parent))
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(selected))
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    report = migration.inventory()
    assert report["effective"]["picoclaw_config"] == str(selected)
    assert report["sources"]["picoclaw.stored"]["path"] == str(stored)
    assert report["effective"]["openai_credential_source"] == "environment:OPENAI_API_KEY"
    assert report["conflicts"]
    assert {item["provider"] for item in report["conflicts"]} == {"openai"}
    assert SECRET not in json.dumps(report)
    assert "another-private-value" not in json.dumps(report)
    assert os.environ["PICOCLAW_CONFIG_PATH"] == str(selected)
    assert "PICOCLAW_MODEL" not in os.environ


def test_custom_root_does_not_hide_legacy_files_or_switch_runtime(home, monkeypatch):
    custom = home / "custom data"
    monkeypatch.setenv("HOSAKA_DATA_DIR", str(custom))
    write(home / ".hosaka/llm.json", {"provider": "openai", "model": "gpt-4.1"})
    pico(home / ".picoclaw/config.json")
    report = migration.inventory()
    assert report["proposed"]["secrets"] == str(custom / "secrets.json")
    assert report["sources"]["llm.user"]["status"] == "present"
    assert report["effective"]["secrets"] == str(home / ".hosaka/secrets.json")
    assert report["effective"]["picoclaw_config"] == str(home / ".picoclaw/config.json")
    assert not custom.exists()


def test_explicit_state_secrets_security_and_workspace_overrides(home, monkeypatch):
    state = home / "state with spaces"
    monkeypatch.setenv("HOSAKA_STATE_PATH", str(state / "state.json"))
    monkeypatch.setenv("HOSAKA_SECRETS_PATH", str(home / "secrets elsewhere.json"))
    monkeypatch.setenv("PICOCLAW_SECURITY_PATH", str(home / "security elsewhere.yml"))
    monkeypatch.setenv("HOSAKA_WORKSPACE", str(home / "workspace elsewhere"))
    report = migration.inventory()
    assert report["effective"]["llm_config"] == str(state / "llm.json")
    assert report["effective"]["secrets"] == str(home / "secrets elsewhere.json")
    assert report["effective"]["picoclaw_security"] == str(home / "security elsewhere.yml")
    assert report["effective"]["workspace"]["path"] == str(home / "workspace elsewhere")
    assert list(home.iterdir()) == []


def test_system_llm_precedence_and_saved_provider_profiles(home):
    write(llm_config._SYSTEM_DIR / "llm.json", {
        "provider": "openai", "model": "system-model", "api_key": SECRET,
        "profiles": {"saved": {"provider": "openai-compatible", "model": "local-model", "api_key": SECRET}},
    })
    write(home / ".hosaka/llm.json", {"provider": "openai", "model": "user-model"})
    report = migration.inventory()
    assert report["effective"]["openai_model"] == "system-model"
    assert any(profile["model"] == "local-model" for profile in report["profiles"])
    assert SECRET not in json.dumps(report)


def test_v3_sidecar_and_multiple_models_do_not_merge_credentials(home):
    path = pico(home / ".picoclaw/config.json", model="anthropic/claude-test")
    config = json.loads(path.read_text())
    config["model_list"].append({"model_name": "local", "model": "ollama/local-test"})
    write(path, config)
    security = path.parent / ".security.yml"
    security.write_text(f'model_list:\n  selected:0:\n    api_keys:\n      - "{SECRET}"\n')
    security.chmod(0o600)
    report = migration.inventory()
    assert report["effective"]["openai_credential_source"] == "picoclaw.selected.security"
    assert any(profile["provider"] == "anthropic" and profile["credential_present"] for profile in report["profiles"])
    assert any(profile["provider"] == "ollama" and not profile["credential_present"] for profile in report["profiles"])
    assert not report["conflicts"]
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize("body", ["{}", "[]", "{broken-private-key", '{"agents": [], "model_list": []}'])
def test_malformed_config_is_explicit_and_never_echoed(home, body, capsys):
    path = home / ".picoclaw/config.json"
    path.parent.mkdir()
    path.write_text(body)
    assert migration.main(["--dry-run", "--json"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "blocked"
    assert "broken-private-key" not in output.out + output.err


def test_invalid_yaml_never_falls_back_to_success_or_echoes_parser_details(home):
    config = pico(home / ".picoclaw/config.json")
    (config.parent / ".security.yml").write_text(f"model_list: [invalid: {SECRET}")
    report = migration.inventory()
    assert report["status"] == "blocked"
    assert not report["effective"]["credential_resolution_complete"]
    assert SECRET not in json.dumps(report)


def test_missing_yaml_parser_is_an_explicit_blocker(home, monkeypatch):
    import builtins

    config = pico(home / ".picoclaw/config.json")
    (config.parent / ".security.yml").write_text("model_list: {}")
    original = builtins.__import__

    def without_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("not installed")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_yaml)
    report = migration.inventory()
    assert report["status"] == "blocked"
    assert any(issue["code"] == "yaml_parser_unavailable_rerun_dependency_setup" for issue in report["issues"])


def test_local_first_missing_config_matches_runtime_defaults_without_writing(home, monkeypatch):
    monkeypatch.setenv("HOSAKA_LOCAL_FIRST", "1")
    report = migration.inventory()
    assert report["effective"]["openai_model"] == llm_config.OLLAMA_DEFAULT_MODEL
    assert report["effective"]["openai_credential_source"] == "openai-compatible default"
    assert not report["effective"]["llm_config_present"]
    assert list(home.iterdir()) == []


def test_compatible_endpoint_placeholder_is_not_reported_as_a_stored_key(home, monkeypatch):
    write(home / ".hosaka/llm.json", {"provider": "openai-compatible", "base_url": "http://localhost:11434/v1"})
    report = migration.inventory()
    assert report["effective"]["openai_model"] == llm_config.OLLAMA_DEFAULT_MODEL
    assert report["effective"]["openai_credential_source"] == "openai-compatible default"
    assert report["credential_sources"] == []


@pytest.mark.parametrize("change", [
    {"model_list": [{"model_name": "selected", "model": 123}]},
    {"agents": {"defaults": {"workspace": 123}}},
])
def test_invalid_picoclaw_field_types_are_reported(home, change):
    path = pico(home / ".picoclaw/config.json")
    config = json.loads(path.read_text())
    config.update(change)
    write(path, config)
    assert migration.inventory()["status"] == "blocked"


def test_unmapped_security_entries_remain_visible_without_disclosing_aliases_or_keys(home):
    config = pico(home / ".picoclaw/config.json")
    (config.parent / ".security.yml").write_text(
        f'model_list:\n  unmapped:0:\n    api_keys:\n      - "{SECRET}"\n'
    )
    report = migration.inventory()
    metadata = report["sources"]["picoclaw.selected.security"]
    assert metadata["unmapped_model_entries"] == 1
    assert metadata["credential_count"] == 1
    assert SECRET not in json.dumps(report)


def test_nonstandard_operator_uses_explicit_account_without_bootstrap(home, monkeypatch):
    import pwd

    account = pwd.struct_passwd(("deck-owner", "x", os.getuid(), os.getgid(), "", str(home), "/bin/sh"))
    monkeypatch.setenv("HOSAKA_OPERATOR", "deck-owner")
    monkeypatch.setattr(pwd, "getpwnam", lambda name: account)
    report = migration.inventory()
    assert report["operator"]["name"] == "deck-owner"
    assert report["operator"]["home"] == str(home)
    assert list(home.iterdir()) == []


def test_oversized_configuration_is_reported_without_dumping_contents(home):
    path = pico(home / ".picoclaw/config.json")
    path.write_text(SECRET * (migration.MAX_CONFIG_BYTES // len(SECRET) + 1))
    report = migration.inventory()
    assert report["status"] == "blocked"
    assert SECRET not in json.dumps(report)


def test_unreadable_source_is_reported_without_exception_contents(home, monkeypatch):
    target = pico(home / ".picoclaw/config.json")
    original = Path.open

    def unreadable(self, *args, **kwargs):
        if self == target:
            raise PermissionError(SECRET)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable)
    report = migration.inventory()
    assert report["status"] == "blocked"
    assert SECRET not in json.dumps(report)


def test_readonly_files_remain_readonly_and_permissions_are_visible(home):
    target = pico(home / ".picoclaw/config.json")
    target.chmod(0o400)
    target.parent.chmod(0o500)
    try:
        before = snapshot(home)
        report = migration.inventory()
        assert report["sources"]["picoclaw.selected"]["mode"] == "0400"
        assert snapshot(home) == before
    finally:
        target.parent.chmod(0o700)


def test_env_file_is_inventoried_without_execution_or_interpolation(home, monkeypatch):
    env = home / "service.env"
    marker = home / "must-not-exist"
    env.write_text(f'OPENAI_API_KEY="{SECRET}"\nPICOCLAW_CONFIG_PATH="$(touch {marker})"\n')
    monkeypatch.setenv("HOSAKA_ENV_FILE", str(env))
    before = dict(os.environ)
    report = migration.inventory()
    assert "env.system:OPENAI_API_KEY" in report["credential_sources"]
    assert report["effective"]["openai_credential_source"] is None
    assert not marker.exists()
    assert dict(os.environ) == before
    assert SECRET not in json.dumps(report)


def test_requires_dry_run_and_rejects_apply(home):
    for args in ([], ["--apply"], ["--dry-run", "--apply"]):
        with pytest.raises(SystemExit) as result:
            migration.main(args)
        assert result.value.code == 2


def test_conflicts_have_distinct_exit_status_without_values(home, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    write(home / ".hosaka/llm.json", {"provider": "openai", "model": "gpt-4.1", "api_key": "different-key"})
    assert migration.main(["--dry-run", "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "needs_review"
    assert report["conflicts"][0]["requires_operator_choice"]
    assert SECRET not in json.dumps(report) and "different-key" not in json.dumps(report)


def test_module_route_skips_boot_logging_dotenv_and_secrets_hydration(home):
    before = snapshot(home)
    result = subprocess.run(
        [sys.executable, "-B", "-X", "importtime", "-m", "hosaka", "migrate", "--dry-run", "--json"],
        cwd=home, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["dry_run"]
    assert "hosaka.boot" not in result.stderr
    assert not (home / ".hosaka").exists()
    assert snapshot(home) == before
