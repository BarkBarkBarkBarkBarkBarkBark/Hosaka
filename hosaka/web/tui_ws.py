"""Local GUI transport for the canonical ``python -m hosaka tui``."""
from __future__ import annotations

import asyncio
import errno
import fcntl
import logging
import os
import pty
import signal
import struct
import subprocess
import sys
import termios
from pathlib import Path
from urllib.parse import urlparse

from anyio import CancelScope
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

router = APIRouter()
log = logging.getLogger("hosaka.web.tui")
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class TerminalMessage(BaseModel):
    type: Literal["input", "resize"]
    data: str = Field("", max_length=16384)
    cols: int = Field(80, ge=20, le=500)
    rows: int = Field(24, ge=5, le=200)


def allowed(ws: WebSocket) -> bool:
    public = os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}
    enabled = os.getenv("HOSAKA_TUI_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
    origin = urlparse(ws.headers.get("origin", ""))
    return (
        not public
        and enabled
        and ws.client is not None
        and ws.client.host in LOOPBACK
        and origin.scheme in {"http", "https"}
        and origin.hostname in LOOPBACK
    )


def resize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


async def ready(fd: int, *, writing: bool = False) -> None:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def wake() -> None:
        if not future.done():
            future.set_result(None)

    add = loop.add_writer if writing else loop.add_reader
    remove = loop.remove_writer if writing else loop.remove_reader
    add(fd, wake)
    try:
        await future
    finally:
        remove(fd)


async def bridge(ws: WebSocket, command: list[str], cols: int, rows: int) -> None:
    master, slave = pty.openpty()
    proc: subprocess.Popen[bytes] | None = None
    tasks: set[asyncio.Task[None]] = set()
    try:
        resize(slave, cols, rows)
        env = dict(
            os.environ, TERM="xterm-256color", COLORTERM="truecolor",
            FORCE_COLOR="1", HOSAKA_TERMINAL_GUI="1",
        )
        env.pop("NO_COLOR", None)
        proc = subprocess.Popen(
            command, stdin=slave, stdout=slave, stderr=slave,
            cwd=Path(__file__).resolve().parents[2], env=env, start_new_session=True,
        )
        os.close(slave)
        slave = -1
        os.set_blocking(master, False)

        async def output() -> None:
            while True:
                await ready(master)
                try:
                    data = os.read(master, 65536)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        return
                    raise
                if not data:
                    return
                await ws.send_bytes(data)

        async def input_() -> None:
            while True:
                message = TerminalMessage.model_validate_json(await ws.receive_text())
                if message.type == "resize":
                    resize(master, message.cols, message.rows)
                else:
                    data = message.data.encode("utf-8")
                    while data:
                        try:
                            data = data[os.write(master, data):]
                        except BlockingIOError:
                            await ready(master, writing=True)

        tasks = {asyncio.create_task(output()), asyncio.create_task(input_())}
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        await ws.close(code=1000, reason="TUI exited")
    except WebSocketDisconnect:
        pass
    except ValidationError:
        await ws.close(code=1008, reason="Invalid terminal message")
    except OSError:
        log.exception("TUI transport failed")
        await ws.close(code=1011, reason="Could not start or communicate with TUI")
    finally:
        with CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.to_thread(proc.wait, timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    await asyncio.to_thread(proc.wait)
            os.close(master)
            if slave != -1:
                os.close(slave)


@router.websocket("/ws/tui")
async def tui_ws(ws: WebSocket) -> None:
    if not allowed(ws):
        await ws.close(code=1008, reason="TUI requires a local, non-public host and origin")
        return
    try:
        size = TerminalMessage.model_validate({
            "type": "resize", "cols": ws.query_params.get("cols", "80"),
            "rows": ws.query_params.get("rows", "24"),
        })
    except ValidationError:
        await ws.close(code=1008, reason="Invalid terminal size")
        return
    await ws.accept()
    # Acquire the controlling TTY after setsid, without preexec_fn in a threaded server.
    launch = (
        "import fcntl,os,sys,termios;"
        "fcntl.ioctl(0,termios.TIOCSCTTY,0);"
        "os.execv(sys.executable,[sys.executable,'-m','hosaka','tui'])"
    )
    await bridge(ws, [sys.executable, "-c", launch], size.cols, size.rows)
