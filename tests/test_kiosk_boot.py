from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def kiosk(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    core = tmp_path / "core"
    (core / "kiosk").mkdir(parents=True)
    tools = tmp_path / "tools"
    log = tmp_path / "commands"
    executable(tools / "curl", 'echo "curl $*" >>"$TEST_LOG"\nexit "${TEST_HEALTH_EXIT:-0}"')
    executable(tools / "seq", "echo 1")
    executable(tools / "sleep", "exec /bin/sleep 0.01")
    executable(tools / "npm", 'echo "npm $*" >>"$TEST_LOG"')
    executable(tools / "node", 'echo "node $*" >>"$TEST_LOG"')
    executable(tools / "systemctl", 'echo "systemctl $*" >>"$TEST_LOG"\nexit 1')
    executable(tools / "dbus-update-activation-environment", "exit 0")
    return {
        **os.environ, "HOME": str(home), "HOSAKA_REPO": str(core),
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "TEST_LOG": str(log), "HOSAKA_STATE_DIR": str(tmp_path / "state"),
        "HOSAKA_KIOSK_LOG": str(tmp_path / "kiosk.log"), "HOSAKA_DISPLAY_MODE": "gui",
        "HOSAKA_DESKTOP_BRANDING": str(tmp_path / "no-branding"),
    }


def add_electron(environment: dict[str, str]) -> None:
    kiosk_dir = Path(environment["HOSAKA_REPO"]) / "kiosk"
    executable(kiosk_dir / "node_modules/.bin/electron", 'echo "electron $*" >>"$TEST_LOG"')
    executable(kiosk_dir / "node_modules/electron/dist/electron", "exit 0")


def launch(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(ROOT / "scripts/kiosk-electron.sh")],
                          env=environment, text=True, capture_output=True, timeout=5)


def test_missing_electron_fails_without_installing_during_boot(kiosk):
    result = launch(kiosk)
    assert result.returncode != 0
    assert "electron" in result.stderr.lower()
    commands = Path(kiosk["TEST_LOG"]).read_text() if Path(kiosk["TEST_LOG"]).exists() else ""
    assert "npm " not in commands
    assert "node " not in commands


def test_unhealthy_backend_never_opens_a_broken_terminal_window(kiosk):
    add_electron(kiosk)
    kiosk["TEST_HEALTH_EXIT"] = "7"
    result = launch(kiosk)
    assert result.returncode != 0
    assert "health" in result.stderr.lower()
    commands = Path(kiosk["TEST_LOG"]).read_text()
    assert "electron " not in commands
    assert "--connect-timeout 2" in commands
    assert "--max-time 2" in commands


def test_healthy_start_preserves_live_profile_and_uses_local_terminal_host(kiosk):
    add_electron(kiosk)
    cache = Path(kiosk["HOME"]) / ".config/hosaka-kiosk/Cache"
    cache.mkdir(parents=True)
    (cache / "sentinel").write_text("existing profile")
    result = launch(kiosk)
    assert result.returncode == 0, result.stderr
    assert (cache / "sentinel").read_text() == "existing profile"
    commands = Path(kiosk["TEST_LOG"]).read_text()
    assert "electron . --no-sandbox" in commands
    assert "npm " not in commands


def test_missing_session_launcher_is_an_actionable_failure(kiosk):
    kiosk["HOSAKA_KIOSK_LAUNCHER"] = str(Path(kiosk["HOME"]) / "missing-launcher")
    result = subprocess.run(["bash", str(ROOT / "scripts/hosaka-lxqt-kiosk.sh")],
                            env=kiosk, text=True, capture_output=True, timeout=5)
    assert result.returncode != 0
    assert "launcher missing" in Path(kiosk["HOSAKA_KIOSK_LOG"]).read_text()


def test_session_supervisor_yields_if_systemd_takes_over_between_launches(kiosk):
    tools = Path(kiosk["TEST_LOG"]).parent / "tools"
    active = Path(kiosk["TEST_LOG"]).parent / "service-active"
    executable(tools / "systemctl",
               f'echo "systemctl $*" >>"$TEST_LOG"\ntest -f "{active}"')
    launcher = executable(tools / "terminal-host", f'echo "HOST" >>"$TEST_LOG"\ntouch "{active}"')
    kiosk["HOSAKA_KIOSK_LAUNCHER"] = str(launcher)
    process = subprocess.Popen(["bash", str(ROOT / "scripts/hosaka-lxqt-kiosk.sh")],
                               env=kiosk, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            commands = Path(kiosk["TEST_LOG"]).read_text() if Path(kiosk["TEST_LOG"]).exists() else ""
            if commands.count("systemctl is-active") >= 3:
                break
            time.sleep(0.01)
        assert commands.count("systemctl is-active") >= 3
        assert commands.splitlines().count("HOST") == 1
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.parametrize("selection,expected", [("lxqt", "LXQT"), ("kiosk", "OPENBOX"), ("openbox", "OPENBOX"), ("invalid", None)])
def test_xinitrc_honors_saved_session_without_resetting_it(kiosk, selection, expected):
    state = Path(kiosk["HOSAKA_STATE_DIR"])
    state.mkdir()
    choice = state / "x-session"
    choice.write_text(selection + "\n")
    tools = Path(kiosk["TEST_LOG"]).parent / "tools"
    executable(tools / "startlxqt", 'echo LXQT')
    executable(tools / "openbox-session", 'echo OPENBOX')
    result = subprocess.run(["sh", str(ROOT / "dotfiles/xinitrc")], env=kiosk,
                            capture_output=True, text=True, timeout=5)
    assert choice.read_text() == selection + "\n"
    if expected is None:
        assert result.returncode != 0
        assert "invalid X session" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected
