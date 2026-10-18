from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/hosaka"


def test_runtime_identity_and_docs_are_included_in_install_and_updates():
    installer = (ROOT / "scripts/install_hosaka.sh").read_text()
    deploy = CLI.read_text().split("cmd_deploy()", 1)[1].split("\ncmd_", 1)[0]
    assert "for runtime_dir in identity manager skills context;" in installer
    assert "for runtime_dir in docs identity manager skills context;" in deploy
    assert '"$REPO_ROOT/$runtime_dir/" "$DEPLOY_ROOT/$runtime_dir/"' in deploy


def test_appliance_install_and_deploy_prepare_shared_llm_settings():
    for name in ("scripts/install_hosaka.sh", "scripts/install_hosaka_lean.sh", "scripts/hosaka"):
        assert "--appliance-user" in (ROOT / name).read_text()
    unit = (ROOT / "systemd/hosaka-webserver.service").read_text()
    assert "ExecStartPre=-" in unit


@pytest.mark.parametrize("command", ["cmd_chat", "cmd_message"])
def test_ssh_chat_routes_through_hosaka_configuration(command, tmp_path):
    python = tmp_path / "python"
    python.write_text('#!/bin/sh\nprintf "ARG=%s\\n" "$@"\n')
    python.chmod(0o755)
    result = shell(
        '_ensure_picoclaw() { :; }; _hosaka_python() { echo "$TEST_PYTHON"; }; '
        f'{command} --session selected hello',
        dict(os.environ, TEST_PYTHON=str(python)),
    )
    assert result.returncode == 0, result.stderr
    args = [line.removeprefix("ARG=") for line in result.stdout.splitlines() if line.startswith("ARG=")]
    assert args[:5] == ["-m", "hosaka", command.removeprefix("cmd_"), "--session", "selected"]
    assert args[-1] == "hello"


def shell(code, env=None):
    return subprocess.run(["bash", "-c", 'source "$1"; ' + code, "bash", str(CLI)],
                          env=env, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("platform,display,ssh,source,source_gui,expected", [
    ("Linux", ":0", "", "0", "0", "GUI"),
    ("Linux", "", "", "0", "0", "TUI"),
    ("Linux", ":0", "remote", "0", "0", "TUI"),
    ("Linux", "", "", "1", "1", "TUI"),
    ("Linux", ":0", "", "1", "0", "TUI"),
    ("Darwin", "", "", "1", "1", "GUI"),
    ("Darwin", "", "remote", "1", "1", "TUI"),
])
def test_default_hosaka_preserves_menu_host_locally_and_bare_tui_over_ssh(platform, display, ssh, source, source_gui, expected):
    result = shell('uname() { echo "$TEST_PLATFORM"; }; cmd_gui() { echo GUI; }; cmd_tui() { echo TUI; }; main',
                   dict(os.environ, TEST_PLATFORM=platform, DISPLAY=display, WAYLAND_DISPLAY="",
                        SSH_CONNECTION=ssh, SSH_TTY="", HOSAKA_SOURCE_INSTALL=source, HOSAKA_SOURCE_GUI=source_gui))
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


@pytest.mark.parametrize("preference", ["tui", "gui", None])
def test_deploy_preserves_display_choice_and_defaults_only_fresh_devices(tmp_path, preference):
    config = tmp_path / "config"
    (config / "hosaka").mkdir(parents=True)
    if preference is not None:
        (config / "hosaka/display-mode").write_text(preference + "\n")
    result = shell(
        'getent() { printf "operator:x:1000:1000:Operator:%s:/bin/bash\\n" "$TEST_HOME"; }; '
        'sudo() { case "$1" in tee|touch) "$@";; *) return 0;; esac; }; '
        'refresh_appliance_launchers; refresh_appliance_launchers; cmd_display show',
        dict(os.environ, TEST_HOME=str(tmp_path), XDG_CONFIG_HOME=str(config)))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith(preference or "gui")
    assert (config / "hosaka/display-mode").read_text() == (preference or "gui") + "\n"
    assert not (config / "hosaka/terminal-gui-default-v1").exists()


def test_deploy_refreshes_session_dispatcher_with_a_preserved_original_backup(tmp_path):
    config = tmp_path / "config"
    (config / "hosaka").mkdir(parents=True)
    (config / "hosaka/display-mode").write_text("gui\n")
    (tmp_path / ".xinitrc").write_text("original session script\n")
    result = shell(
        'getent() { printf "deck:x:1000:1000:Deck:%s:/bin/bash\\n" "$TEST_HOME"; }; '
        'sudo() { case "$1" in cp) "$@";; install) '
        'if [[ "${@: -1}" == "$TEST_HOME/.xinitrc" ]]; then '
        'cp "$REPO_ROOT/dotfiles/xinitrc" "$TEST_HOME/.xinitrc"; fi;; *) return 0;; esac; }; '
        'refresh_appliance_launchers; refresh_appliance_launchers',
        dict(os.environ, TEST_HOME=str(tmp_path), XDG_CONFIG_HOME=str(config)))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".xinitrc").read_text() == (ROOT / "dotfiles/xinitrc").read_text()
    assert (tmp_path / ".xinitrc.pre-hosaka").read_text() == "original session script\n"


@pytest.mark.parametrize("initial_mode,display", [("console", "gui"), ("console", "tui"), ("device", "gui"), ("build", "gui")])
@pytest.mark.parametrize("deploy_exit,health_exit,stamp,ui_built,host_running", [
    (0, 0, "abc123", True, True),
    (7, 0, "abc123", True, True),
    (0, 1, "abc123", True, True),
    (0, 0, "wrong", True, True),
    (0, 0, "abc123", False, True),
    (0, 0, "abc123", True, False),
])
def test_update_worker_restores_services_on_success_and_failure(tmp_path, deploy_exit, health_exit, stamp, ui_built, host_running, initial_mode, display):
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "commands"
    mocks = {
        "id": 'echo 0',
        "flock": 'exit 0',
        "install": 'exit 0',
        "chown": 'exit 0',
        "pgrep": 'case "$*" in "-x Xorg") exit 0;; *kiosk/node_modules/electron/dist/electron*) exit "$TEST_HOST_EXIT";; esac\nexit 1',
        "getent": f'echo "operator:x:1000:1000:Operator:{tmp_path}:/bin/bash"',
        "curl": f'case "$*" in *build-stamp.json*) echo \'{{"sha":"{stamp}"}}\';; *) echo \'{{"ui_built":{str(ui_built).lower()}}}\';; esac\nexit {health_exit}',
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
    (state / "mode").write_text(initial_mode + "\n")
    config = tmp_path / "config"
    (config / "hosaka").mkdir(parents=True)
    preference = config / "hosaka/display-mode"
    preference.write_text(display + "\n")
    worker = tmp_path / "worker"
    worker.write_text((ROOT / "scripts/hosaka-update-worker.sh").read_text().replace(
        "/run/lock/hosaka-update.lock", str(tmp_path / "update.lock")))
    result = subprocess.run(["bash", str(worker)], text=True, capture_output=True, timeout=10,
                            env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                                     HOSAKA_REPO=str(repo), HOSAKA_STATE_DIR=str(state),
                                     HOSAKA_OPERATOR="operator", TEST_LOG=str(log),
                                     XDG_CONFIG_HOME=str(config), TEST_HOST_EXIT="0" if host_running else "1"))
    needs_host = initial_mode == "console" and display == "gui"
    success = deploy_exit == 0 and health_exit == 0 and stamp == "abc123" and ui_built and (not needs_host or host_running)
    assert (result.returncode == 0) == success, result.stderr
    assert (state / "mode").read_text().strip() == initial_mode
    assert preference.read_text() == display + "\n"
    commands = log.read_text()
    assert "stop hosaka-webserver.service" in commands
    assert "start hosaka-webserver.service" in commands
    assert ("start hosaka-kiosk.service" in commands) == needs_host
    assert "getty@tty1" not in commands
    assert ("UPDATE COMPLETE" if success else "UPDATE FAILED") in result.stdout + result.stderr
