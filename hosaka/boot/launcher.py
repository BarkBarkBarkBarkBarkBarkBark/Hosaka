from __future__ import annotations

import os
import subprocess
import sys
import time

from hosaka.main_console import run_main_console
from hosaka.setup.orchestrator import build_default_orchestrator
from hosaka.tui.terminal import run_setup_flow


WEB_HOST = os.getenv("HOSAKA_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))


def start_web_server() -> subprocess.Popen[str] | None:
    try:
        process = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "uvicorn",
                "hosaka.web.server:app",
                "--host",
                WEB_HOST,
                "--port",
                str(WEB_PORT),
                "--log-level",
                "warning",
            ],
        )
        return process
    except Exception as exc:  # noqa: BLE001
        print(f"Hosaka warning: failed to start web setup server: {exc}")
        return None


def launch() -> None:
    orchestrator = build_default_orchestrator()
    orchestrator.update_runtime_network()
    web_url = f"http://{orchestrator.state.local_ip}:{WEB_PORT}"
    web_process = start_web_server()

    if not sys.stdin.isatty():
        print(f"Hosaka web setup available at: {web_url}")
        while True:
            if web_process and web_process.poll() is not None:
                print("Hosaka warning: web setup process exited; retrying in 5s")
                time.sleep(5)
                web_process = start_web_server()
            time.sleep(60)

    if not orchestrator.state.setup_completed:
        try:
            run_setup_flow(orchestrator=orchestrator, web_url=web_url)
        except Exception as exc:  # noqa: BLE001
            orchestrator.state.last_error = f"Setup flow crashed: {exc}"
            orchestrator.persist()
            raise

    run_main_console()


if __name__ == "__main__":
    launch()
