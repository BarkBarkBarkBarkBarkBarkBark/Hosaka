from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from hosaka.extensions.__main__ import main
from hosaka.extensions.manager import Manager, REFERENCE, digest
from hosaka.extensions.manifest import ExtensionError, validate_package, validate_view

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def manager(tmp_path, monkeypatch):
    for key in ("HOSAKA_OPERATOR", "SUDO_USER", "HOSAKA_DATA_DIR", "HOSAKA_GAMES_DIR", "HOSAKA_PSX_ROMS", "HOSAKA_PUBLIC_MODE"):
        monkeypatch.delenv(key, raising=False)
    home = tmp_path / "operator home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return Manager()


def package(tmp_path, identifier="example-extension"):
    target = tmp_path / identifier
    shutil.copytree(REFERENCE, target)
    manifest = target / "extension.yaml"
    manifest.write_text(manifest.read_text().replace("reference-extension", identifier))
    return target


def mutate(path, change):
    manifest = path / "extension.yaml"
    values = yaml.safe_load(manifest.read_text())
    change(values)
    manifest.write_text(yaml.safe_dump(values))


def snapshot(root):
    return {
        str(path.relative_to(root)): (path.stat().st_mode, path.read_bytes() if path.is_file() else None)
        for path in root.rglob("*") if "__pycache__" not in path.parts
    }


def test_reference_contract_does_not_import_code_or_create_state(manager, tmp_path, monkeypatch):
    target = package(tmp_path)
    (target / "main.py").write_text("raise RuntimeError('must not be imported')\n")
    before = snapshot(manager.root.parent)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Validation contacted a network"))
    validated = validate_package(target)
    assert validated.manifest.id == "example-extension"
    assert snapshot(manager.root.parent) == before
    assert not manager.root.exists()


def test_init_seeds_disabled_reference_and_private_registry_idempotently(manager):
    first = manager.init()
    assert first["seeded"] and not first["reference_differs"]
    assert len(first["extensions"]) == 1
    assert first["extensions"][0]["enabled"] is False
    assert first["extensions"][0]["grants"] == []
    assert not first["execution_available"] and first["ui_available"]
    assert not first["extensions"][0]["ui_available"]
    assert manager.lock.stat().st_mode & 0o777 == 0o600
    assert manager.root.stat().st_mode & 0o777 == 0o700
    before = snapshot(manager.root)
    second = manager.init()
    assert not second["seeded"]
    assert snapshot(manager.root) == before


def test_init_preserves_modified_code_data_enablement_and_grants(manager):
    manager.init()
    info = manager.enable("reference-extension", True)
    source = Path(info["path"]) / "main.py"
    source.write_text(source.read_text() + "\n# owner modification\n")
    data = manager.root / "extension-data/reference-extension/receipt.txt"
    data.parent.mkdir()
    data.write_text("saved receipt")
    registry = json.loads(manager.lock.read_text())
    registry["extensions"]["reference-extension"]["grants"] = ["storage:self"]
    manager.lock.write_text(json.dumps(registry))
    result = manager.init()
    assert result["reference_differs"]
    assert "owner modification" in source.read_text()
    assert data.read_text() == "saved receipt"
    assert result["extensions"][0]["enabled"]
    assert result["extensions"][0]["grants"] == ["storage:self"]


def test_create_second_external_package_without_core_changes(manager, tmp_path):
    core_before = digest(ROOT / "hosaka/extensions")
    status_before = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)
    target = tmp_path / "independent project"
    created = manager.create("second-extension", target)
    assert created["id"] == "second-extension"
    assert created["name"] == "Second Extension"
    assert created["path"] == str(target)
    assert not created["enabled"]
    assert not (target / "example.txt").exists()
    assert validate_package(target).manifest.id == "second-extension"
    assert digest(ROOT / "hosaka/extensions") == core_before
    assert subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True) == status_before
    with pytest.raises(ExtensionError, match="already registered"):
        manager.create("second-extension", target)


def test_link_and_lifecycle_preserve_package_and_data(manager, tmp_path):
    target = package(tmp_path)
    manager.link(target)
    assert manager.enable("example-extension", True)["enabled"]
    assert not manager.enable("example-extension", False)["enabled"]
    before = snapshot(target)
    result = manager.remove("example-extension")
    assert result["data_retained"] and result["code_retained"]
    assert manager.discover()["extensions"] == []
    assert snapshot(target) == before
    manager.link(target)
    assert not manager.info("example-extension")["enabled"]


def test_remove_managed_reference_survives_rerun(manager):
    manager.init()
    manager.remove("reference-extension")
    assert manager.discover()["extensions"] == []
    report = manager.init()
    assert not report["seeded"]
    assert report["extensions"] == []
    assert (manager.packages / "reference-extension/main.py").exists()


def test_duplicate_ids_have_no_arbitrary_winner(manager, tmp_path):
    manager.init()
    shutil.copytree(REFERENCE, manager.packages / "another-directory")
    report = manager.discover()
    assert report["extensions"] == []
    assert len(report["errors"]) == 2
    with pytest.raises(ExtensionError):
        manager.enable("reference-extension", True)
    with pytest.raises(ExtensionError, match="already registered"):
        manager.link(package(tmp_path, "reference-extension"))


def test_invalid_package_does_not_hide_good_packages(manager):
    manager.init()
    invalid = manager.packages / "bad-extension"
    invalid.mkdir()
    (invalid / "extension.yaml").write_text("invalid: [")
    report = manager.discover()
    assert len(report["extensions"]) == 1
    assert len(report["errors"]) == 1
    assert manager.doctor()["status"] == "fail"


def test_bootstrap_diagnoses_unrelated_invalid_package_without_blocking_core(manager, capsys):
    manager.init()
    invalid = manager.packages / "bad-extension"
    invalid.mkdir()
    (invalid / "extension.yaml").write_text("invalid: [")
    assert main(["init", "--json"]) == 0
    output = capsys.readouterr()
    assert len(json.loads(output.out)["errors"]) == 1
    assert "invalid packages were preserved and skipped" in output.err
    assert main(["doctor", "--json"]) == 1


@pytest.mark.parametrize("change", [
    lambda m: m.update(schema_version=True),
    lambda m: m.update(schema_version=2),
    lambda m: m.update(requires={"hosaka_api": 2}),
    lambda m: m.update(requires={"hosaka_api": True}),
    lambda m: m.update(id="../escape"),
    lambda m: m.update(id="settings"),
    lambda m: m.update(version="v1.0"),
    lambda m: m.update(unknown_field="ignored?"),
    lambda m: m["entrypoint"].update(file="../outside.py"),
    lambda m: m["entrypoint"].update(file="/tmp/absolute.py"),
    lambda m: m["entrypoint"].update(callable="os.system"),
    lambda m: m["permissions"].update(network=True),
    lambda m: m["permissions"].update(subprocess=True),
    lambda m: m["permissions"].update(filesystem="home"),
    lambda m: m["limits"].update(timeout_seconds=0),
    lambda m: m["limits"].update(max_output_bytes=999999999),
    lambda m: m["actions"]["echo"].update(input_schema="../input.json"),
    lambda m: m["actions"].update(shell=m["actions"]["echo"]),
])
def test_invalid_manifests_rejected_without_execution(tmp_path, change):
    target = package(tmp_path)
    mutate(target, change)
    with pytest.raises(ExtensionError):
        validate_package(target)


def test_duplicate_yaml_fields_are_rejected(tmp_path):
    target = package(tmp_path)
    path = target / "extension.yaml"
    path.write_text(path.read_text() + "\nid: replacement\n")
    with pytest.raises(ExtensionError, match="unique"):
        validate_package(target)


def test_symlink_escape_and_missing_file_are_rejected(tmp_path):
    target = package(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("raise RuntimeError('never execute')")
    (target / "main.py").unlink()
    (target / "main.py").symlink_to(outside)
    with pytest.raises(ExtensionError, match="escapes"):
        validate_package(target)
    (target / "main.py").unlink()
    with pytest.raises(ExtensionError, match="missing"):
        validate_package(target)


@pytest.mark.parametrize("schema", [
    {"type": "not-a-json-schema-type"},
    {"$ref": "https://example.invalid/input.json"},
    {"$ref": "file:///etc/passwd"},
    {"$dynamicRef": "#/test"},
    {"$ref": "#/$defs/missing"},
    {"$schema": "http://json-schema.org/draft-07/schema#"},
])
def test_invalid_or_remote_action_schema_is_rejected(tmp_path, schema):
    target = package(tmp_path)
    (target / "schemas/message.input.json").write_text(json.dumps(schema))
    with pytest.raises(ExtensionError):
        validate_package(target)


@pytest.mark.parametrize("view", [
    {"type": "HTML", "html": "<script>alert(1)</script>"},
    {"type": "Text", "text": "hello", "style": "anything"},
    {"type": "Button", "label": "Execute", "action": "unknown"},
    {"type": "Button", "label": "Execute", "action": []},
    {"type": "Result", "bind": "result.message.toUpperCase()"},
    {"type": "Result", "bind": "params.missing"},
    {"type": "TextInput", "id": "input", "label": "Input", "default": 1},
    {"type": "NumberInput", "id": "count", "label": "Count", "default": True},
    {"type": "Checkbox", "id": "choice", "label": "Choice", "default": "yes"},
    {"type": "Select", "id": "choice", "label": "Choice", "options": ["a", "a"]},
])
def test_invalid_declarative_ui_is_rejected(view):
    with pytest.raises(ExtensionError):
        validate_view({"version": 1, "view": view}, {"echo"})


def test_recursive_or_oversized_ui_is_rejected():
    stack = {"type": "Stack", "children": []}
    stack["children"].append(stack)
    with pytest.raises(ExtensionError, match="nesting"):
        validate_view({"version": 1, "view": stack}, {"echo"})


def test_symlinked_managed_directory_cannot_redirect_bootstrap(manager, tmp_path):
    manager.root.mkdir()
    elsewhere = tmp_path / "other-code"
    elsewhere.mkdir()
    manager.packages.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ExtensionError, match="escapes"):
        manager.init()
    assert list(elsewhere.iterdir()) == []


def test_registry_symlink_and_duplicate_json_are_rejected(manager, tmp_path):
    manager.root.mkdir()
    outside = tmp_path / "keep.json"
    outside.write_text('{"schema_version": 1, "extensions": {}}')
    manager.lock.symlink_to(outside)
    with pytest.raises(ExtensionError, match="symlink"):
        manager.init()
    manager.lock.unlink()
    manager.lock.write_text('{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(ExtensionError, match="unique"):
        manager.registry()


def test_changed_reference_version_is_reported_not_replaced(manager):
    manager.init()
    target = manager.packages / "reference-extension"
    mutate(target, lambda manifest: manifest.update(version="2.0.0"))
    result = manager.init()
    assert result["reference_differs"]
    info = manager.info("reference-extension")
    assert info["version"] == "2.0.0"
    assert info["registered_version"] == validate_package(REFERENCE).manifest.version
    assert info["source_modified"]


def test_corrupt_registry_is_not_reset_or_overwritten(manager):
    manager.root.mkdir()
    manager.lock.write_text('{"schema_version": 99}')
    original = manager.lock.read_bytes()
    with pytest.raises(ExtensionError, match="restore"):
        manager.init()
    assert manager.lock.read_bytes() == original
    assert not (manager.packages / "reference-extension").exists()


def test_unknown_registry_grants_fail_explicitly(manager):
    manager.init()
    values = json.loads(manager.lock.read_text())
    values["extensions"]["reference-extension"]["grants"] = ["shell"]
    manager.lock.write_text(json.dumps(values))
    with pytest.raises(ExtensionError, match="Invalid"):
        manager.registry()


def test_create_never_overwrites_existing_folder(manager, tmp_path):
    target = tmp_path / "owner-code"
    target.mkdir()
    (target / "sentinel").write_text("kept")
    with pytest.raises(ExtensionError, match="overwrite"):
        manager.create("my-extension", target)
    assert (target / "sentinel").read_text() == "kept"


def test_authoring_does_not_allow_package_inside_core(manager):
    with pytest.raises(ExtensionError, match="outside core"):
        manager.create("my-extension", ROOT / "new-user-content")


def test_cli_json_diagnostics_and_unsupported_execution(manager, capsys):
    assert main(["init", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["extensions"]
    assert main(["validate", "reference-extension", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert main(["run", "reference-extension", "echo"]) != 0
    assert main(["test", "reference-extension"]) != 0
    assert main(["doctor", "--json"]) == 0
    assert "execution" in capsys.readouterr().out.lower()


def test_module_management_skips_boot_secrets_and_workspace_creation(manager):
    environment = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONPROFILEIMPORTTIME": "1"}
    result = subprocess.run(
        [sys.executable, "-B", "-m", "hosaka", "extensions", "list", "--json"],
        cwd=manager.root.parent, env=environment, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["extensions"] == []
    assert "hosaka.boot" not in result.stderr and "hosaka.secrets" not in result.stderr
    assert not manager.root.exists()


def test_public_mode_blocks_management_without_creating_state(manager, monkeypatch, capsys):
    monkeypatch.setenv("HOSAKA_PUBLIC_MODE", "1")
    assert main(["init"]) == 1
    assert "unavailable in public/hosted mode" in capsys.readouterr().err
    assert not manager.root.exists()


def test_reference_local_suite_and_scaffolded_second_package_execute_real_tests(manager, tmp_path):
    for target in (REFERENCE, tmp_path / "second-package"):
        if target != REFERENCE:
            manager.create("second-package", target)
        result = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(target / "tests"), "-v"],
            cwd=target, env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Ran 5 tests" in result.stderr
