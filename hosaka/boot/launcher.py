from __future__ import annotations

import os
import sys
import threading
import time

import uvicorn

from hosaka.main_console import run_main_console
from hosaka.setup.orchestrator import build_default_orchestrator
from hosaka.tui.terminal import run_setup_flow
from hosaka.web.server import app


WEB_HOST = os.getenv("HOSAKA_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("HOSAKA_WEB_PORT", "8421"))


def start_web_server() -> threading.Thread:
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="warning"),
        daemon=True,
    )
    server_thread.start()
    return server_thread


def launch() -> None:
    orchestrator = build_default_orchestrator()
    orchestrator.update_runtime_network()
    web_url = f"http://{orchestrator.state.local_ip}:{WEB_PORT}"
    start_web_server()

    if not sys.stdin.isatty():
        print(f"Hosaka web setup available at: {web_url}")
        while True:
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
