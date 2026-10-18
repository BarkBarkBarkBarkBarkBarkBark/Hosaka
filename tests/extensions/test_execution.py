from __future__ import annotations

import json
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from hosaka.extensions.manager import Manager
from hosaka.extensions.runner import _record, cancel, run


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("Real trusted-local execution intentionally requires a non-root account.")
    for name in ("HOSAKA_OPERATOR", "SUDO_USER", "HOSAKA_DATA_DIR", "HOSAKA_GAMES_DIR", "HOSAKA_PSX_ROMS", "HOSAKA_PUBLIC_MODE", "HOSAKA_EXTENSIONS_SAFE_MODE"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "operator home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    manager = Manager()
    manager.init()
    manager.trust("reference-extension", allow_storage=True)
    manager.enable("reference-extension", True)
    return manager


def source(manager, content, *, timeout=2, output=65536, identifier="reference-extension"):
    package = manager.packages / identifier
    (package / "main.py").write_text(content)
    manifest = package / "extension.yaml"
    values = yaml.safe_load(manifest.read_text())
    values["limits"] = {"timeout_seconds": timeout, "max_output_bytes": output}
    manifest.write_text(yaml.safe_dump(values))
    manager.trust(identifier, allow_storage=True)


def wait_file(path):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.01)
    pytest.fail(f"Invocation did not create {path.name}")


def test_real_reference_echo_persistence_error_and_private_logs(runtime):
    assert run(runtime, "reference-extension", "echo", {"message": "hello"})["result"]["message"] == "hello"
    assert run(runtime, "reference-extension", "save", {"message": "sensitive-user-text"})["ok"]
    assert run(runtime, "reference-extension", "load", {})["result"]["message"] == "sensitive-user-text"
    failed = run(runtime, "reference-extension", "fail", {})
    assert not failed["ok"] and failed["error"]["code"] == "action_failed"
    assert "Intentional" in failed["result"]["error"]
    assert run(runtime, "reference-extension", "delete", {})["ok"]
    assert run(runtime, "reference-extension", "load", {})["result"]["message"] == ""
    log = runtime.root / "logs/extensions/reference-extension.jsonl"
    assert "sensitive-user-text" not in log.read_text()
    assert log.stat().st_mode & 0o777 == 0o600
    assert all(json.loads(line)["execution_mode"] == "trusted-local" for line in log.read_text().splitlines())
    assert any(json.loads(line)["events"] for line in log.read_text().splitlines())


def test_tui_command_executes_the_same_real_runner(runtime, capsys):
    from hosaka import main_console

    current = runtime.paths.operator.home
    command = """/extensions run reference-extension echo --params '{"message":"TUI bridge proof"}'"""
    assert main_console._dispatch_command(command, current, "llm") == (current, "llm")
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["result"]["message"] == "TUI bridge proof"


@pytest.mark.parametrize("change", ["disabled", "revoked", "safe", "storage", "changed", "public", "root"])
def test_execution_is_gated_without_running_package(runtime, monkeypatch, change):
    if change == "disabled":
        runtime.enable("reference-extension", False)
    elif change == "revoked":
        runtime.revoke("reference-extension")
    elif change == "safe":
        runtime.safe_mode("on")
    elif change == "storage":
        runtime.trust("reference-extension", allow_storage=False)
    elif change == "changed":
        with (runtime.packages / "reference-extension/main.py").open("a") as stream:
            stream.write("\n# changed after approval\n")
    elif change == "public":
        monkeypatch.setenv("HOSAKA_PUBLIC_MODE", "true")
    else:
        monkeypatch.setattr(os, "geteuid", lambda: 0)
    report = run(runtime, "reference-extension", "save", {"message": "must not be saved"})
    assert not report["ok"] and report["error"]["code"] == "not_authorized"
    assert not (runtime.root / "extension-data/reference-extension/example.txt").exists()


def test_invalid_input_stale_view_and_unknown_action_never_spawn(runtime):
    assert run(runtime, "reference-extension", "echo", {"message": 42})["error"]["code"] == "invalid_input"
    assert run(runtime, "reference-extension", "echo", {"message": "x" * 17000})["error"]["code"] == "invalid_input"
    assert run(runtime, "reference-extension", "missing", {})["error"]["code"] == "unknown_action"
    assert run(runtime, "reference-extension", "load", {}, expected_digest="0" * 64)["error"]["code"] == "stale_view"


@pytest.mark.parametrize("program,expected", [
    ("def run(action, params, context):\n raise RuntimeError('do-not-log-this')\n", "extension_exception"),
    ("def run(action, params, context):\n return {'success': 'yes'}\n", "invalid_output"),
    ("import os\ndef run(action, params, context):\n os._exit(7)\n", "process_failed"),
    ("import os\ndef run(action, params, context):\n os._exit(0)\n", "invalid_protocol"),
    ("import os\ndef run(action, params, context):\n os.write(1, b'{\"success\":true}')\n os._exit(7)\n", "process_failed"),
    ("def run(action, params, context):\n return {'success': True, 'message': '\\ud800', 'error': None, 'rows': []}\n", "invalid_protocol"),
    ("def run(action, params, context):\n print('x' * 200000)\n return {}\n", "output_limit"),
    ("import time\ndef run(action, params, context):\n time.sleep(5)\n", "timeout"),
])
def test_real_worker_failures_are_bounded_and_logged(runtime, program, expected):
    source(runtime, program, timeout=1)
    report = run(runtime, "reference-extension", "load", {})
    assert not report["ok"] and report["error"]["code"] == expected
    assert report["duration_ms"] < 3500
    logs = (runtime.root / "logs/extensions/reference-extension.jsonl").read_text()
    assert json.loads(logs.splitlines()[-1])["error_code"] == expected
    assert "do-not-log-this" not in json.dumps(report) + logs


def test_no_provider_or_other_parent_environment_is_inherited(runtime, monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HOSAKA_API_TOKEN", "PICOCLAW_HOME", "UNRELATED_SECRET"):
        monkeypatch.setenv(key, "must-not-reach-worker")
    source(runtime, """import os, json
def run(action, params, context):
 return {'success': True, 'message': json.dumps(dict(os.environ)), 'error': None, 'rows': []}
""")
    report = run(runtime, "reference-extension", "load", {})
    assert report["ok"]
    assert "must-not-reach-worker" not in report["result"]["message"]
    assert json.loads(report["result"]["message"])["HOME"] != str(runtime.paths.operator.home)


def test_invalid_unicode_input_is_reported_without_spawning(runtime):
    assert run(runtime, "reference-extension", "echo", {"message": "\ud800"})["error"]["code"] == "invalid_input"


def test_context_text_size_limit_accepts_64k_and_rejects_one_extra_byte(runtime):
    source(runtime, """def run(action, params, context):
 context.write_data('limit.txt', 'x' * 65536)
 assert len(context.read_data('limit.txt')) == 65536
 try:
  context.write_data('limit.txt', 'x' * 65537)
 except ValueError:
  return {'success': True, 'message': '65536 bytes retained; extra byte rejected', 'error': None, 'rows': []}
 raise AssertionError('oversized text was accepted')
""")
    report = run(runtime, "reference-extension", "load", {})
    assert report["ok"], report
    assert (runtime.root / "extension-data/reference-extension/limit.txt").stat().st_size == 65536


def test_context_file_count_limit_is_exactly_128(runtime):
    source(runtime, """def run(action, params, context):
 for index in range(128):
  context.write_data(f'value-{index}.txt', 'one')
 try:
  context.write_data('value-128.txt', 'extra')
 except ValueError:
  return {'success': True, 'message': '128 files retained; extra file rejected', 'error': None, 'rows': []}
 raise AssertionError('extra file was accepted')
""", timeout=5)
    report = run(runtime, "reference-extension", "load", {})
    assert report["ok"], report
    assert len(list((runtime.root / "extension-data/reference-extension").iterdir())) == 128


def test_log_rotation_preserves_one_bounded_previous_file(runtime):
    directory = runtime.root / "logs/extensions"
    directory.mkdir()
    path = directory / "reference-extension.jsonl"
    path.write_bytes(b"x" * 262144)
    path.chmod(0o600)
    report = {"invocation_id": str(uuid4()), "action": "echo", "ok": True, "duration_ms": 1, "error": None}
    _record(runtime, "reference-extension", report, [])
    assert path.with_suffix(".previous.jsonl").stat().st_size == 262144
    assert path.stat().st_size <= 262144
    assert json.loads(path.read_text())["invocation_id"] == report["invocation_id"]


def test_environment_safe_mode_cannot_be_overridden_by_persisted_off(runtime, monkeypatch):
    monkeypatch.setenv("HOSAKA_EXTENSIONS_SAFE_MODE", "1")
    state = runtime.safe_mode("off")
    assert state == {"safe_mode": True, "saved_safe_mode": False, "environment_override": True}
    assert run(runtime, "reference-extension", "load", {})["error"]["code"] == "not_authorized"


@pytest.mark.parametrize("operation", ["disable", "remove", "revoke", "safe", "event", "cancel"])
def test_live_disable_removal_revoke_safe_mode_and_caller_cancel(runtime, operation):
    source(runtime, """import time
def run(action, params, context):
 context.write_data('started', 'yes')
 time.sleep(20)
 return {'success': True, 'message': 'too late', 'error': None, 'rows': []}
""", timeout=30)
    cancellation = threading.Event()
    invocation = str(uuid4())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, runtime, "reference-extension", "load", {}, cancellation=cancellation, invocation_id=invocation)
        wait_file(runtime.root / "extension-data/reference-extension/started")
        if operation == "disable":
            runtime.enable("reference-extension", False)
        elif operation == "remove":
            runtime.remove("reference-extension")
        elif operation == "revoke":
            runtime.revoke("reference-extension")
        elif operation == "safe":
            runtime.safe_mode("on")
        elif operation == "event":
            cancellation.set()
        else:
            cancel(runtime, "reference-extension", invocation)
        report = future.result(timeout=5)
    assert report["error"]["code"] == "cancelled"
    assert list((runtime.root / "state/extension-jobs").glob("*.active")) == []


def test_busy_extension_is_rejected_without_blocking_another_call(runtime):
    source(runtime, """import time
def run(action, params, context):
 context.write_data('started', 'yes')
 time.sleep(20)
""", timeout=30)
    cancellation = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, runtime, "reference-extension", "load", {}, cancellation=cancellation)
        wait_file(runtime.root / "extension-data/reference-extension/started")
        try:
            assert run(runtime, "reference-extension", "load", {})["error"]["code"] == "busy"
        finally:
            cancellation.set()
            assert future.result(timeout=5)["error"]["code"] == "cancelled"


def test_disable_still_cancels_a_running_package_after_its_manifest_breaks(runtime):
    source(runtime, """import time
def run(action, params, context):
 context.write_data('started', 'yes')
 time.sleep(20)
""", timeout=30)
    cancellation = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, runtime, "reference-extension", "load", {}, cancellation=cancellation)
        wait_file(runtime.root / "extension-data/reference-extension/started")
        try:
            (runtime.packages / "reference-extension/extension.yaml").write_text("invalid: [")
            assert runtime.enable("reference-extension", False)["enabled"] is False
            assert future.result(timeout=3)["error"]["code"] == "cancelled"
        finally:
            cancellation.set()
            future.result(timeout=5)


def test_global_two_worker_limit_is_measured_across_extensions(runtime):
    program = """import time
def run(action, params, context):
 context.write_data('started', 'yes')
 time.sleep(20)
"""
    identifiers = ["reference-extension", "second-worker", "third-worker"]
    for identifier in identifiers:
        if identifier != "reference-extension":
            runtime.create(identifier)
            runtime.enable(identifier, True)
        source(runtime, program, timeout=30, identifier=identifier)
    events = [threading.Event(), threading.Event()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run, runtime, identifier, "load", {}, cancellation=event)
                for identifier, event in zip(identifiers, events)]
        try:
            for identifier in identifiers[:2]:
                wait_file(runtime.root / f"extension-data/{identifier}/started")
            assert run(runtime, identifiers[2], "load", {})["error"]["code"] == "busy"
        finally:
            for event in events:
                event.set()
            for job in jobs:
                assert job.result(timeout=5)["error"]["code"] == "cancelled"


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "link"])
def test_context_rejects_escaping_storage_names_and_symlinks(runtime, tmp_path, name):
    data = runtime.root / "extension-data/reference-extension"
    data.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "untouched"
    outside.write_text("keep")
    (data / "link").symlink_to(outside)
    source(runtime, f"""def run(action, params, context):
 context.write_data({name!r}, 'bad')
 return {{'success': True, 'message': 'bad', 'error': None, 'rows': []}}
""")
    assert run(runtime, "reference-extension", "load", {})["error"]["code"] == "extension_exception"
    assert outside.read_text() == "keep"


def test_real_child_process_group_is_cleaned_after_success(runtime):
    source(runtime, """import subprocess, sys
def run(action, params, context):
 child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
 context.write_data('child.pid', str(child.pid))
 return {'success': True, 'message': 'done', 'error': None, 'rows': []}
""")
    report = run(runtime, "reference-extension", "load", {})
    assert report["ok"]
    pid = int((runtime.root / "extension-data/reference-extension/child.pid").read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        status = Path(f"/proc/{pid}/stat")
        if status.exists() and status.read_text().split()[2] == "Z":
            return  # Dead and awaiting the host's reaper, not a running descendant.
        time.sleep(0.02)
    os.kill(pid, signal.SIGKILL)
    pytest.fail("Worker descendant survived process-group cleanup")
