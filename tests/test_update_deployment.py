from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/hosaka"


def shell(code, env=None):
    return subprocess.run(["bash", "-c", 'source "$1"; ' + code, "bash", str(CLI)],
                          env=env, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("display,expected", [(":0", "GUI"), ("", "TUI")])
def test_plain_hosaka_chooses_terminal_gui_when_graphical(display, expected):
    result = shell('uname() { echo Linux; }; cmd_gui() { echo GUI; }; cmd_tui() { echo TUI; }; main',
                   dict(os.environ, DISPLAY=display))
    assert result.returncode == 0
    assert result.stdout.strip() == expected


def test_pi_update_starts_independent_job_without_building():
    result = shell('uname() { echo Linux; }; start_update_job() { printf "JOB %s\\n" "$*"; }; '
                   'cmd_deploy() { echo SHOULD_NOT_DEPLOY; }; cmd_update --check --branch main')
    assert result.returncode == 0
    assert result.stdout.strip() == "JOB --check --branch main"

def test_job_is_memory_limited_and_not_tied_to_shell(tmp_path):
    library = tmp_path / "hosaka"
    library.write_text(CLI.read_text().replace("/run/systemd/system", str(tmp_path)))
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; systemctl() { return 1; }; '
         'getent() { echo "operator:x:1000:1000:Operator:/home/operator:/bin/bash"; }; '
         'sudo() { printf "SUDO %s\\n" "$*"; }; start_update_job --check',
         "bash", str(library)],
        env=dict(os.environ, HOSAKA_REPO=str(ROOT), HOSAKA_OPERATOR="operator"),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "systemd-run --unit=hosaka-update" in result.stdout
    assert "--property=MemoryMax=650M" in result.stdout
    assert "--property=OOMScoreAdjust=700" in result.stdout
    assert "--setenv=HOSAKA_OPERATOR=operator" in result.stdout
    assert "hosaka-update-worker.sh --check" in result.stdout
    assert "--scope" not in result.stdout
    assert "--wait" not in result.stdout


def test_update_runs_freshly_pulled_deploy_code(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "scripts/hosaka").write_text('#!/bin/bash\nprintf "NEW_DEPLOY %s\\n" "$*"\n')
    result = shell(
        'git() { case "$3" in status) return 0;; rev-parse) echo main;; esac; }; '
        'cmd_deploy() { echo STALE_DEPLOY; }; cmd_update --foreground --check',
        dict(os.environ, HOSAKA_REPO=str(repo)))
    assert result.returncode == 0, result.stderr
    assert "NEW_DEPLOY deploy --check" in result.stdout
    assert "STALE_DEPLOY" not in result.stdout


def test_source_update_rejects_untracked_work(tmp_path):
    (tmp_path / ".git").mkdir()
    result = shell('git() { echo "?? personal.txt"; }; cmd_update --foreground',
                   dict(os.environ, HOSAKA_REPO=str(tmp_path)))
    assert result.returncode != 0
    assert "local changes" in result.stderr


def test_deploy_fails_for_missing_runtime_directory(tmp_path):
    result = shell('cmd_build() { echo SHOULD_NOT_BUILD; }; cmd_deploy',
                   dict(os.environ, HOSAKA_DEPLOY=str(tmp_path / "missing")))
    assert result.returncode != 0
    assert "install Hosaka" in result.stderr
    assert "SHOULD_NOT_BUILD" not in result.stdout


def test_first_deploy_migrates_gui_then_preserves_explicit_tui(tmp_path):
    config = tmp_path / "config"
    (config / "hosaka").mkdir(parents=True)
    (config / "hosaka/display-mode").write_text("tui\n")
    result = shell(
        'getent() { printf "operator:x:1000:1000:Operator:%s:/bin/bash\\n" "$TEST_HOME"; }; '
        'sudo() { case "$1" in tee|touch) "$@";; *) return 0;; esac; }; '
        'refresh_appliance_launchers; cmd_display tui; refresh_appliance_launchers; cmd_display show',
        dict(os.environ, TEST_HOME=str(tmp_path), XDG_CONFIG_HOME=str(config)))
    assert result.returncode == 0, result.stderr
    assert "migrated graphical boot" in result.stdout
    assert result.stdout.strip().endswith("tui")
    assert (config / "hosaka/terminal-gui-default-v1").exists()


@pytest.mark.parametrize("deploy_exit,health_exit,stamp", [(0, 0, "abc123"), (7, 0, "abc123"), (0, 1, "abc123"), (0, 0, "wrong")])
def test_update_worker_restores_services_on_success_and_failure(tmp_path, deploy_exit, health_exit, stamp):
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "commands"
    mocks = {
        "id": 'echo 0',
        "flock": 'exit 0',
        "install": 'exit 0',
        "chown": 'exit 0',
        "pgrep": 'exit 1',
        "curl": f'case "$*" in *build-stamp.json*) echo \'{{"sha":"{stamp}"}}\';; esac\nexit {health_exit}',
        "seq": 'echo 1',
        "sleep": 'exit 0',
        "runuser": 'echo abc123',
        "systemctl": 'echo "$*" >>"$TEST_LOG"; if [ "$1" = is-active ]; then exit 0; fi',
    }
    for name, body in mocks.items():
        script = tools / name
        script.write_text("#!/bin/sh\n" + body + "\n")
        script.chmod(0o755)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/hosaka").write_text(f'#!/bin/sh\necho "DEPLOY $*" >>"$TEST_LOG"\nexit {deploy_exit}\n')
    state = tmp_path / "state"
    state.mkdir()
    (state / "mode").write_text("console\n")
    worker = tmp_path / "worker"
    worker.write_text((ROOT / "scripts/hosaka-update-worker.sh").read_text().replace(
        "/run/lock/hosaka-update.lock", str(tmp_path / "update.lock")))
    result = subprocess.run(["bash", str(worker)], text=True, capture_output=True, timeout=10,
                            env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                                     HOSAKA_REPO=str(repo), HOSAKA_STATE_DIR=str(state),
                                     HOSAKA_OPERATOR="operator", TEST_LOG=str(log)))
    success = deploy_exit == 0 and health_exit == 0 and stamp == "abc123"
    assert (result.returncode == 0) == success, result.stderr
    assert (state / "mode").read_text().strip() == "console"
    commands = log.read_text()
    assert "stop hosaka-webserver.service" in commands
    assert "start hosaka-webserver.service" in commands
    assert "restart getty@tty1.service" in commands
    assert ("UPDATE COMPLETE" if success else "UPDATE FAILED") in result.stdout + result.stderr
