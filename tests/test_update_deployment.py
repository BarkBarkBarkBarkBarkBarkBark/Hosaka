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
    assert "for runtime_dir in identity manager skills context examples;" in installer
    assert "for runtime_dir in docs identity manager skills context examples;" in deploy
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


def test_source_update_uses_dirty_checkout_and_refreshes_field_terminal(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "install.sh").write_text("#!/bin/sh\necho INSTALL\n")
    result = shell(
        'update_deck() { echo DECK; }; git() { printf "?? work\\n"; }; cmd_update',
        dict(os.environ, HOSAKA_SOURCE_INSTALL="1", HOSAKA_SOURCE_GUI="0", HOSAKA_REPO=str(repo)),
    )
    assert result.returncode == 0, result.stderr
    assert "INSTALL" in result.stdout
    assert "DECK" in result.stdout
    assert "local changes" in result.stdout


def test_source_update_pulls_a_clean_checkout(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "install.sh").write_text("#!/bin/sh\necho INSTALL\n")
    result = shell(
        'update_deck() { echo DECK; }; '
        'git() { if [[ "$3" == "status" ]]; then return 0; fi; '
        'if [[ "$3" == "pull" ]]; then echo PULLED; return 0; fi; }; cmd_update',
        dict(os.environ, HOSAKA_SOURCE_INSTALL="1", HOSAKA_SOURCE_GUI="0", HOSAKA_REPO=str(repo)),
    )
    assert result.returncode == 0, result.stderr
    assert "PULLED" in result.stdout
    assert "INSTALL" in result.stdout
    assert "DECK" in result.stdout


def test_field_terminal_update_keeps_operator_extensions(tmp_path):
    repo = tmp_path / "repo"
    field = tmp_path / "field"
    home = tmp_path / "home"
    (repo / "hosaka").mkdir(parents=True)
    (repo / "hosaka" / "marker.py").write_text("EXTENSION_RUNTIME = True\n")
    (repo / "examples" / "extensions" / "reference-extension").mkdir(parents=True)
    (repo / "examples" / "extensions" / "reference-extension" / "extension.yaml").write_text("id: reference-extension\n")
    (repo / "requirements-hosaka.txt").write_text("PyYAML>=6.0,<7.0\n")
    (repo / "frontend" / "src").mkdir(parents=True)
    (repo / "frontend" / "src" / "App.tsx").write_text("export {}\n")
    (repo / "frontend" / "index.html").write_text("<html></html>\n")
    (repo / "frontend" / "public" / "locales").mkdir(parents=True)
    (repo / "frontend" / "public" / "library").mkdir(parents=True)
    (repo / "frontend" / "public" / "locales" / "en.json").write_text("{}\n")
    (repo / "frontend" / "public" / "library" / "note.md").write_text("note\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "api.md").write_text("# api\n")
    (field / "frontend" / "public").mkdir(parents=True)
    (home / ".hosaka" / "extensions" / "halloween-citations").mkdir(parents=True)
    (home / ".hosaka" / "extension-data" / "halloween-citations").mkdir(parents=True)
    (home / ".hosaka" / "extensions" / "halloween-citations" / "secret.txt").write_text("do-not-ship\n")
    (home / ".hosaka" / "extension-data" / "halloween-citations" / "citations.sqlite3").write_text("db\n")
    script = ROOT / "scripts" / "update-field-terminal.sh"
    result = subprocess.run(
        ["bash", str(script)],
        env=dict(os.environ, HOME=str(home), HOSAKA_REPO=str(repo), HOSAKA_FIELD_TERMINAL=str(field),
                 HOSAKA_HOSTED_DEPLOY="0"),
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    overlay = field / "runtime-overlay"
    assert (overlay / "hosaka" / "marker.py").read_text() == "EXTENSION_RUNTIME = True\n"
    assert (overlay / "examples" / "extensions" / "reference-extension" / "extension.yaml").is_file()
    assert (field / "frontend" / "src" / "App.tsx").is_file()
    assert "do-not-ship" not in result.stdout
    assert not (overlay / "extension-data").exists()
    assert not list(overlay.rglob("secret.txt"))
    assert not list(overlay.rglob("citations.sqlite3"))


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


def test_one_gigabyte_deck_skips_the_ui_build():
    result = shell('prepare_native_update; printf "SKIP=%s\\n" "$HOSAKA_SKIP_UI_BUILD"',
                   dict(os.environ, HOSAKA_MEM_TOTAL_KB="948000"))
    assert result.returncode == 0, result.stderr
    assert "SKIP=1" in result.stdout
    assert "no Docker image" in result.stdout


def test_deploy_obeys_skip_ui_build(tmp_path):
    repo = tmp_path / "repo"
    deploy = tmp_path / "opt"
    (repo / "hosaka").mkdir(parents=True)
    (repo / "hosaka" / "marker.py").write_text("runtime\n")
    (repo / "requirements-hosaka.txt").write_text("py\n")
    (repo / "README.md").write_text("readme\n")
    (deploy / ".venv" / "bin").mkdir(parents=True)
    python = deploy / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    result = shell(
        'sudo() { "$@"; }; rsync() { echo "RSYNC $*"; }; cmp() { return 0; }; '
        'refresh_appliance_launchers() { echo REFRESH; }; systemctl() { return 1; }; '
        'pgrep() { return 1; }; cmd_build() { echo BUILT; }; cmd_deploy',
        dict(os.environ, HOSAKA_REPO=str(repo), HOSAKA_DEPLOY=str(deploy), HOSAKA_SKIP_UI_BUILD="1"),
    )
    assert result.returncode == 0, result.stderr
    assert "BUILT" not in result.stdout
    assert "REFRESH" in result.stdout
    assert "RSYNC" in result.stdout


def test_deck_update_copies_native_tree_without_docker_or_extension_data(tmp_path):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    log = tmp_path / "commands"
    tools = tmp_path / "bin"
    (repo / "frontend").mkdir(parents=True)
    (repo / "hosaka").mkdir()
    (home / ".hosaka" / "extensions" / "halloween-citations").mkdir(parents=True)
    (home / ".hosaka" / "extension-data" / "halloween-citations").mkdir(parents=True)
    (home / ".hosaka" / "extensions" / "halloween-citations" / "main.py").write_text("package\n")
    (home / ".hosaka" / "extension-data" / "halloween-citations" / "citations.sqlite3").write_text("db\n")
    tools.mkdir()
    for name, body in {
        "npm": 'echo "NPM $*" >>"$TEST_LOG"',
        "rsync": 'echo "RSYNC $*" >>"$TEST_LOG"',
        "ssh": 'echo "SSH $*" >>"$TEST_LOG"',
        "docker": 'echo "DOCKER $*" >>"$TEST_LOG"; exit 99',
    }.items():
        binary = tools / name
        binary.write_text("#!/bin/sh\n" + body + "\n")
        binary.chmod(0o755)
    script = ROOT / "scripts" / "update-deck.sh"
    result = subprocess.run(
        ["bash", str(script)],
        env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"], HOME=str(home),
                 HOSAKA_REPO=str(repo), HOSAKA_DECK_HOST="deck.example", HOSAKA_DECK_REPO="/home/operator/Hosaka",
                 HOSAKA_MEM_TOTAL_KB="8000000", TEST_LOG=str(log)),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    recorded = log.read_text()
    assert "NPM run build" in recorded
    assert "deck.example:/home/operator/Hosaka/" in recorded
    assert "deck.example:.hosaka/extensions/" in recorded
    assert "citations.sqlite3" not in recorded
    assert "deck.example:.hosaka/extension-data" not in recorded
    assert "--exclude extension-data/" in recorded
    assert "DOCKER" not in recorded
    assert "HOSAKA_SKIP_UI_BUILD=1" in recorded


def test_one_gigabyte_machine_refuses_to_build_the_deck_locally(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    npm = tools / "npm"
    npm.write_text("#!/bin/sh\necho BUILT >\"$TEST_LOG\"\n")
    npm.chmod(0o755)
    log = tmp_path / "built"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "update-deck.sh")],
        env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"], HOSAKA_REPO=str(tmp_path),
                 HOSAKA_MEM_TOTAL_KB="948000", TEST_LOG=str(log)),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode != 0
    assert "1GB" in result.stderr
    assert not log.exists()


def test_low_memory_worker_keeps_existing_ui(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "commands"
    mocks = {
        "id": "echo 0",
        "flock": "exit 0",
        "install": "exit 0",
        "chown": "exit 0",
        "pgrep": "exit 1",
        "getent": f'echo "operator:x:1000:1000:Operator:{tmp_path}:/bin/bash"',
        "curl": 'echo \'{"ui_built":true,"sha":"old"}\'',
        "seq": "echo 1",
        "sleep": "exit 0",
        "runuser": "echo abc123",
        "systemctl": 'echo "$*" >>"$TEST_LOG"; if [ "$1" = is-active ]; then exit 0; fi',
        "node": "exit 0",
    }
    for name, body in mocks.items():
        binary = tools / name
        binary.write_text("#!/bin/sh\n" + body + "\n")
        binary.chmod(0o755)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "hosaka").write_text('#!/bin/sh\necho "SKIP=$HOSAKA_SKIP_UI_BUILD" >>"$TEST_LOG"\n')
    state = tmp_path / "state"
    state.mkdir()
    (state / "mode").write_text("device\n")
    config = tmp_path / "config" / "hosaka"
    config.mkdir(parents=True)
    (config / "display-mode").write_text("tui\n")
    worker = tmp_path / "worker"
    worker.write_text((ROOT / "scripts/hosaka-update-worker.sh").read_text().replace(
        "/run/lock/hosaka-update.lock", str(tmp_path / "update.lock")))
    result = subprocess.run(
        ["bash", str(worker)], text=True, capture_output=True, timeout=10,
        env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"], HOSAKA_REPO=str(repo),
                 HOSAKA_STATE_DIR=str(state), HOSAKA_OPERATOR="operator", TEST_LOG=str(log),
                 XDG_CONFIG_HOME=str(tmp_path / "config"), HOSAKA_MEM_TOTAL_KB="948000"),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SKIP=1" in log.read_text()
    assert "Kept the existing terminal UI" in result.stdout

