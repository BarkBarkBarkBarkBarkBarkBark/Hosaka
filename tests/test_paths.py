from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
from pathlib import Path

import pytest

from hosaka import doctor, paths

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native_home(tmp_path, monkeypatch):
    for key in (
        "HOSAKA_OPERATOR", "SUDO_USER", "HOSAKA_DATA_DIR", "HOSAKA_GAMES_DIR",
        "HOSAKA_PSX_ROMS", "HOSAKA_SECRETS_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    home = tmp_path / "operator home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def initialize(tmp_path):
    core = tmp_path / "core checkout"
    (core / "hosaka").mkdir(parents=True, exist_ok=True)
    launcher = tmp_path / "bin" / "hosaka"
    launcher.parent.mkdir(exist_ok=True)
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o755)
    paths.initialize(
        paths.resolve_paths(), mode="source", repo=core, runtime=core,
        launcher=launcher, python=Path(sys.executable),
    )


def test_default_paths_are_external_and_inspection_does_not_write(native_home):
    resolved = paths.resolve_paths()
    assert resolved.root == native_home / ".hosaka"
    assert resolved.psx_roms == native_home / "Games/Hosaka/roms/psx"
    assert resolved.as_dict()["installation"] is None
    assert list(native_home.iterdir()) == []


def test_sudo_uses_selected_account_home_not_root_home(native_home, monkeypatch):
    account = pwd.getpwuid(os.getuid())
    monkeypatch.setenv("SUDO_USER", account.pw_name)
    operator = paths.resolve_operator()
    assert operator.name == account.pw_name
    assert operator.home == Path(account.pw_dir).resolve()


def test_unknown_operator_fails_without_guessing(native_home, monkeypatch):
    monkeypatch.setenv("HOSAKA_OPERATOR", "hosaka-no-such-test-account")
    with pytest.raises(ValueError, match="Unknown Hosaka operator"):
        paths.resolve_paths()


def test_explicit_nonstandard_operator_uses_account_home(native_home, monkeypatch):
    account = pwd.struct_passwd(("deck-builder", "x", os.getuid(), os.getgid(), "", str(native_home), "/bin/sh"))
    monkeypatch.setenv("HOSAKA_OPERATOR", "deck-builder")
    monkeypatch.setenv("SUDO_USER", "root")
    monkeypatch.setattr(pwd, "getpwnam", lambda name: account)
    resolved = paths.resolve_paths()
    assert resolved.operator.name == "deck-builder"
    assert resolved.root == native_home / ".hosaka"


@pytest.mark.parametrize("value", ["relative/path", "", "~another-user/config"])
def test_invalid_data_override_is_not_silently_ignored(native_home, monkeypatch, value):
    monkeypatch.setenv("HOSAKA_DATA_DIR", value)
    with pytest.raises(ValueError, match="must be absolute"):
        paths.resolve_paths()


def test_tilde_override_uses_operator_home(native_home, monkeypatch):
    monkeypatch.setenv("HOSAKA_DATA_DIR", "~/private data")
    assert paths.resolve_paths().root == native_home / "private data"


def test_game_override_and_compatibility_rom_override(native_home, monkeypatch):
    monkeypatch.setenv("HOSAKA_GAMES_DIR", "~/game library")
    assert paths.resolve_paths().psx_roms == native_home / "game library/roms/psx"
    monkeypatch.setenv("HOSAKA_PSX_ROMS", "~/existing roms")
    assert paths.resolve_paths().psx_roms == native_home / "existing roms"


def test_populated_old_library_wins_over_empty_earlier_directory(native_home):
    (native_home / "RetroPie/roms/psx").mkdir(parents=True)
    populated = native_home / "Games/PlayStation"
    populated.mkdir(parents=True)
    (populated / "Twisted Metal.cue").touch()
    assert paths.resolve_paths().psx_roms == populated


def test_configured_game_path_overrides_discovery(native_home):
    root = native_home / ".hosaka"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"paths": {"games_dir": "~/configured"}}))
    assert paths.resolve_paths().psx_roms == native_home / "configured/roms/psx"


@pytest.mark.parametrize("body", ["invalid-json", "[]", '{"paths": []}', '{"paths": {"games_dir": 42}}'])
def test_bad_config_is_explicit_failure(native_home, body, capsys):
    root = native_home / ".hosaka"
    root.mkdir()
    (root / "config.json").write_text(body)
    assert paths.main(["--json"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Hosaka paths failed" in output.err


def test_initialization_is_private_idempotent_and_preserves_user_content(native_home, tmp_path):
    initialize(tmp_path)
    root = native_home / ".hosaka"
    record = root / "installation.json"
    original = record.read_bytes()
    (root / "extensions" / "owner-code.py").write_text("user content")
    (root / "extension-data" / "receipt.txt").write_text("saved receipt")
    (root / "config.json").write_text('{"owner_setting": true}')
    initialize(tmp_path)
    assert record.read_bytes() == original
    assert root.stat().st_mode & 0o777 == 0o700
    assert record.stat().st_mode & 0o777 == 0o600
    assert (root / "extensions" / "owner-code.py").read_text() == "user content"
    assert (root / "extension-data" / "receipt.txt").read_text() == "saved receipt"
    assert (root / "config.json").read_text() == '{"owner_setting": true}'
    assert (native_home / "Games/Hosaka/roms/psx").is_dir()


def test_initialization_remembers_external_library_without_moving_it(native_home, tmp_path):
    library = native_home / "Games/PlayStation"
    library.mkdir(parents=True)
    rom = library / "Tekken.cue"
    rom.write_text("test fixture, not a ROM")
    initialize(tmp_path)
    assert paths.resolve_paths().installation["psx_roms"] == str(library)
    assert rom.read_text() == "test fixture, not a ROM"
    # The recorded library is not silently replaced when temporarily unavailable.
    rom.unlink()
    library.rmdir()
    assert paths.resolve_paths().psx_roms == library


def test_record_preserves_venv_python_symlink(native_home, tmp_path):
    initialize(tmp_path)
    record = native_home / ".hosaka/installation.json"
    data = json.loads(record.read_text())
    venv_python = tmp_path / "venv/bin/python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(sys.executable)
    data["python"] = str(venv_python)
    record.write_text(json.dumps(data))
    assert paths.resolve_paths().installation["python"] == str(venv_python)


def test_failed_atomic_update_preserves_previous_record_and_cleans_temporary_file(native_home, tmp_path, monkeypatch):
    initialize(tmp_path)
    root = native_home / ".hosaka"
    original = (root / "installation.json").read_bytes()

    def fail_replace(source, destination):
        raise PermissionError("read-only destination")

    monkeypatch.setattr(paths.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="read-only"):
        initialize(tmp_path)
    assert (root / "installation.json").read_bytes() == original
    assert not list(root.glob(".installation-*"))


@pytest.mark.parametrize("change", [{"schema_version": 2}, {"schema_version": True}, {"mode": "unknown"}, {"mode": []}, {"operator": "someone-else"}, {"launcher": None}])
def test_invalid_installation_record_is_rejected(native_home, tmp_path, change):
    initialize(tmp_path)
    record = native_home / ".hosaka/installation.json"
    data = json.loads(record.read_text())
    data.update(change)
    record.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        paths.resolve_paths()


def test_record_output_never_dumps_unknown_values(native_home, tmp_path):
    initialize(tmp_path)
    record = native_home / ".hosaka/installation.json"
    data = json.loads(record.read_text())
    data["api_key"] = "do-not-emit"
    record.write_text(json.dumps(data))
    assert "do-not-emit" not in json.dumps(paths.resolve_paths().as_dict())


def test_data_cannot_be_initialized_inside_core(native_home, tmp_path, monkeypatch):
    core = tmp_path / "checkout"
    (core / "hosaka").mkdir(parents=True)
    monkeypatch.setenv("HOSAKA_DATA_DIR", str(core / "user-data"))
    with pytest.raises(ValueError, match="outside"):
        paths.initialize(paths.resolve_paths(), mode="source", repo=core, runtime=core,
                         launcher=tmp_path / "launcher", python=Path(sys.executable))
    assert not (core / "user-data").exists()


def test_escaped_managed_directory_is_rejected(native_home, tmp_path):
    root = native_home / ".hosaka"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "extensions").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        initialize(tmp_path)
    assert not (root / "installation.json").exists()
    assert any(check["name"] == "extensions" and check["status"] == "fail"
               for check in paths.offline_report()["checks"])


def test_no_implicit_install_mode_conversion(native_home, tmp_path):
    initialize(tmp_path)
    resolved = paths.resolve_paths()
    with pytest.raises(ValueError, match="another installation mode"):
        paths.initialize(resolved, mode="appliance", repo=tmp_path, runtime=tmp_path,
                         launcher=tmp_path / "launcher", python=Path(sys.executable))


def test_container_initialization_creates_layout_and_records_docker_mode(native_home, tmp_path):
    core = tmp_path / "container-core"
    (core / "hosaka").mkdir(parents=True)
    for _ in range(2):
        paths.initialize(paths.resolve_paths(), mode="docker", repo=core, runtime=core,
                         launcher=Path(sys.executable), python=Path(sys.executable))
    resolved = paths.resolve_paths()
    assert resolved.installation["mode"] == "docker"
    assert all(directory.is_dir() for directory in resolved.directories().values())
    assert resolved.psx_roms.is_dir()
    assert not resolved.root.is_relative_to(core)


@pytest.mark.parametrize("mode", ["source", "docker"])
def test_only_container_mode_accepts_writable_host_owned_mounts(native_home, tmp_path, monkeypatch, mode):
    core = tmp_path / "core"
    (core / "hosaka").mkdir(parents=True)
    resolved = paths.resolve_paths()
    managed = set(resolved.directories().values())
    original_stat = Path.stat

    def host_owned_stat(self, *args, **kwargs):
        result = original_stat(self, *args, **kwargs)
        if self in managed:
            fields = list(result)
            fields[4] = os.getuid() + 1
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(Path, "stat", host_owned_stat)
    if mode == "source":
        with pytest.raises(ValueError, match="not owned"):
            paths.initialize(resolved, mode=mode, repo=core, runtime=core,
                             launcher=Path(sys.executable), python=Path(sys.executable))
    else:
        paths.initialize(resolved, mode=mode, repo=core, runtime=core,
                         launcher=Path(sys.executable), python=Path(sys.executable))
        report = paths.offline_report()
        assert not any(check["status"] == "fail" for check in report["checks"])


def test_offline_doctor_does_not_probe_provider_or_require_web(native_home, tmp_path, monkeypatch, capsys):
    initialize(tmp_path)
    monkeypatch.setattr(doctor, "build_report", lambda *a, **kw: pytest.fail("network diagnostics called"))
    assert doctor.main(["--offline", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["provider_request_verified"] is False
    assert any(c["name"] == "installation" and c["status"] == "pass" for c in report["checks"])


def test_offline_doctor_checks_recorded_launcher(native_home, tmp_path, capsys):
    initialize(tmp_path)
    (tmp_path / "bin/hosaka").unlink()
    assert doctor.main(["--offline", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert any(c["name"] == "record.launcher" and c["status"] == "fail" for c in report["checks"])


def test_offline_doctor_strict_reports_missing_setup(native_home, capsys):
    assert doctor.main(["--offline", "--strict", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["overall_status"] == "warn"


def test_executable_candidates_report_distinct_path_entries(native_home, tmp_path, monkeypatch):
    bins = [tmp_path / "one", tmp_path / "two"]
    for directory in bins:
        directory.mkdir()
        executable = directory / "hosaka"
        executable.write_text("#!/bin/sh\n")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join(str(p) for p in [*bins, bins[0]]))
    assert paths.executable_candidates("hosaka") == [str(p / "hosaka") for p in bins]


def test_aliases_of_the_same_launcher_are_not_conflicting_installations(native_home, tmp_path, monkeypatch):
    initialize(tmp_path)
    target = tmp_path / "bin/hosaka"
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    (alias_dir / "hosaka").symlink_to(target)
    monkeypatch.setenv("PATH", os.pathsep.join((str(target.parent), str(alias_dir))))
    check = next(check for check in paths.offline_report()["checks"] if check["name"] == "binary.hosaka")
    assert check["status"] == "pass"
    assert str(target) in check["message"] and str(alias_dir) in check["message"]


@pytest.mark.parametrize("arguments", [["paths", "--json"], ["doctor", "--offline", "--json"]])
def test_module_diagnostics_do_not_load_boot_or_read_secret_values(native_home, arguments):
    root = native_home / ".hosaka"
    root.mkdir(mode=0o700)
    (root / "secrets.json").write_text('{"OPENAI_API_KEY": "never-expose-this"}')
    environment = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONPROFILEIMPORTTIME": "1"}
    result = subprocess.run([sys.executable, "-m", "hosaka", *arguments], cwd=native_home,
                            env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    json.loads(result.stdout)
    assert "never-expose-this" not in result.stdout + result.stderr
    assert "hosaka.boot" not in result.stderr
    assert "hosaka.secrets" not in result.stderr
    assert not (root / "state").exists()


def test_cli_defaults_to_tui_even_with_a_display_and_no_frontend(native_home, tmp_path):
    core = tmp_path / "checkout"
    (core / "hosaka").mkdir(parents=True)
    (core / "README.md").touch()
    (core / "scripts").mkdir()
    script = core / "scripts/hosaka"
    script.write_bytes((ROOT / "scripts/hosaka").read_bytes())
    python = core / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "ARGS=%s\\n" "$*"\nprintf "CWD=%s\\n" "$PWD"\n')
    python.chmod(0o755)
    environment = {**os.environ, "HOSAKA_SOURCE_INSTALL": "1", "DISPLAY": ":0"}
    result = subprocess.run(["bash", str(script)], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "ARGS=-m hosaka tui" in result.stdout
    assert f"CWD={tmp_path}" in result.stdout
