import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("boot,display", [("kiosk", "gui"), ("kiosk", "tui"), ("headless", "gui")])
def test_appliance_installer_wires_runtime_without_host_changes(tmp_path, boot, display):
    tools = tmp_path / "bin"
    tools.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "commands"
    mocks = {
        "sudo": 'printf "sudo %s\\n" "$*" >>"$TEST_LOG"\n'
                'case "$1" in tee) cat >/dev/null;; esac\nexit 0',
        "getent": 'printf "operator:x:1000:1000:Operator:%s:/bin/bash\\n" "$HOME"',
        "node": 'printf 22',
        "npm": 'printf "npm %s\\n" "$*" >>"$TEST_LOG"',
        "cp": 'printf "cp %s\\n" "$*" >>"$TEST_LOG"',
        "picoclaw": 'echo "picoclaw 0.3.1"',
    }
    for name, body in mocks.items():
        path = tools / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "HOME": str(home),
        "TEST_LOG": str(log),
        "HOSAKA_BOOT_MODE": boot,
        "HOSAKA_DISPLAY_MODE": display,
        "INSTALL_TAILSCALE": "0",
        "INSTALL_CADDY": "0",
        "INSTALL_DOCKER": "0",
        "INSTALL_RETROARCH": "1",
    }
    env.pop("SUDO_USER", None)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/install_hosaka.sh")],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text()
    assert "--preserve-env=OPENAI_API_KEY,HOSAKA_LOCAL_FIRST" in commands
    assert "bootstrap_picoclaw_runtime.py --appliance-user" in commands
    assert "npm ci --prefer-offline --loglevel error" in commands
    assert "npm run build" in commands
    assert "apt-get install -y retroarch" in commands
    if boot == "kiosk":
        assert "xserver-xorg xserver-xorg-legacy xinit openbox" in commands
        assert "dotfiles/xinitrc" in commands
    if boot == "kiosk" and display == "gui":
        assert "npm install --no-fund --no-audit --loglevel error" in commands
