from __future__ import annotations

import shutil
import socket
import subprocess


def detect_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def detect_tailscale_status() -> str:
    if not shutil.which("tailscale"):
        return "not-installed"
    try:
        result = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, check=True)
        if "Self" in result.stdout:
            return "connected"
        return "installed"
    except subprocess.CalledProcessError:
        return "installed-not-connected"
