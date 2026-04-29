"""Minimal async client for the OpenAI Realtime WebSocket API.

Scope is deliberately narrow — just enough to run a single voice turn
from the headless Python daemon:

* open a session with our tool schema + system instructions,
* stream 24 kHz PCM16 input frames,
* receive 24 kHz PCM16 output frames and the transcript deltas,
* handle ``response.function_call_arguments.done`` by invoking our
  dispatcher and submitting the result back.

We don't implement conversation branching, interruptions, or multi-modal
input here — the daemon drives one linear conversation and the browser
path uses WebRTC directly so doesn't come through this file.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from websockets.asyncio.client import ClientConnection
else:  # pragma: no cover - runtime alias when optional dep is missing
    ClientConnection = Any

log = logging.getLogger("hosaka.voice.realtime")

DEFAULT_MODEL = os.getenv("HOSAKA_VOICE_MODEL", "gpt-4o-realtime-preview")
DEFAULT_VOICE = os.getenv("HOSAKA_VOICE_VOICE", "verse")
REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"


def _require_websockets() -> Any:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RealtimeError(
            "hosaka.voice.realtime_client requires `websockets`. "
            "Install with: pip install -r requirements-voice.txt"
        ) from exc
    return websockets


class RealtimeError(RuntimeError):
    pass


# ── event types we care about ────────────────────────────────────────────

AudioHandler = Callable[[bytes], Awaitable[None]]
TextHandler = Callable[[str], Awaitable[None]]
ToolHandler = Callable[[str, dict[str, Any]], Awaitable[str]]
StateHandler = Callable[[str], Awaitable[None]]


class RealtimeSession:
    """One live connection to the Realtime API.

    Use as an async context manager::

        async with RealtimeSession(api_key, tools=TOOL_SCHEMAS) as rt:
            rt.on_audio = handle_pcm_out
            rt.on_tool  = run_tool
            await rt.run(mic_stream)
    """

    def __init__(
        self,
        api_key: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        instructions: str = "",
        voice: str = DEFAULT_VOICE,
        model: str = DEFAULT_MODEL,
    ) -> None:
        if not api_key:
            raise RealtimeError("OPENAI_API_KEY not set")
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._tools = tools or []
        self._instructions = instructions
        self._ws: ClientConnection | None = None

        # Caller-supplied event hooks. All async, called from the reader task.
        self.on_audio: AudioHandler | None = None
        self.on_user_transcript: TextHandler | None = None
        self.on_assistant_transcript: TextHandler | None = None
        self.on_state: StateHandler | None = None
        self.on_tool: ToolHandler | None = None

    # ── context manager ───────────────────────────────────────────────

    async def __aenter__(self) -> "RealtimeSession":
        url = REALTIME_URL.format(model=self._model)
        headers = [
            ("Authorization", f"Bearer {self._api_key}"),
            ("OpenAI-Beta", "realtime=v1"),
        ]
        websockets = _require_websockets()
        self._ws = await websockets.connect(
            url,
            additional_headers=headers,
            max_size=16 * 1024 * 1024,
        )
        await self._send(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "voice": self._voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 600,
                    },
                    "tools": self._tools,
                    "tool_choice": "auto",
                    "instructions": self._instructions,
                },
            }
        )
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    # ── send helpers ──────────────────────────────────────────────────

    async def _send(self, event: dict[str, Any]) -> None:
        if self._ws is None:
            raise RealtimeError("session not open")
        await self._ws.send(json.dumps(event))

    async def send_pcm16(self, frame: bytes) -> None:
        """Append a chunk of 24 kHz mono PCM16 to the input buffer."""
        if not frame:
            return
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(frame).decode("ascii"),
            }
        )

    async def commit_input(self) -> None:
        """Force the server to cut the turn here (useful when VAD is off)."""
        await self._send({"type": "input_audio_buffer.commit"})

    async def request_response(self) -> None:
        await self._send({"type": "response.create"})

    async def cancel_response(self) -> None:
        await self._send({"type": "response.cancel"})

    # ── receive loop ──────────────────────────────────────────────────

    async def _notify_state(self, state: str) -> None:
        if self.on_state is not None:
            try:
                await self.on_state(state)
            except Exception:  # noqa: BLE001
                log.exception("on_state hook failed")

    async def _submit_tool_result(self, call_id: str, output: str) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                },
            }
        )
        await self.request_response()

    async def _handle_event(self, evt: dict[str, Any]) -> None:
        etype = evt.get("type", "")
        if etype == "response.audio.delta":
            if self.on_audio is not None:
                try:
                    pcm = base64.b64decode(evt.get("delta", ""))
                    await self.on_audio(pcm)
                except Exception:  # noqa: BLE001
                    log.exception("on_audio hook failed")
        elif etype == "response.audio_transcript.delta":
            if self.on_assistant_transcript is not None:
                try:
                    await self.on_assistant_transcript(str(evt.get("delta", "")))
                except Exception:  # noqa: BLE001
                    log.exception("on_assistant_transcript hook failed")
        elif etype == "conversation.item.input_audio_transcription.completed":
            if self.on_user_transcript is not None:
                try:
                    await self.on_user_transcript(str(evt.get("transcript", "")))
                except Exception:  # noqa: BLE001
                    log.exception("on_user_transcript hook failed")
        elif etype == "input_audio_buffer.speech_started":
            await self._notify_state("listening")
        elif etype == "input_audio_buffer.speech_stopped":
            await self._notify_state("thinking")
        elif etype == "response.audio.done":
            await self._notify_state("idle")
        elif etype == "response.function_call_arguments.done":
            call_id = str(evt.get("call_id", ""))
            name = str(evt.get("name", ""))
            raw = evt.get("arguments", "{}")
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                args = {}
            output = f"tool {name}: no dispatcher wired"
            if self.on_tool is not None:
                try:
                    output = await self.on_tool(name, args)
                except Exception as exc:  # noqa: BLE001
                    log.exception("tool %s crashed", name)
                    output = f"{name}: crashed ({exc})"
            await self._submit_tool_result(call_id, output)
        elif etype == "error":
            err = evt.get("error", {})
            log.warning(
                "realtime error: %s (%s)",
                err.get("message"),
                err.get("type"),
            )

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Iterate over decoded server events (after dispatching hooks)."""
        if self._ws is None:
            raise RealtimeError("session not open")
        async for msg in self._ws:
            try:
                evt = json.loads(msg)
            except json.JSONDecodeError:
                continue
            await self._handle_event(evt)
            yield evt

    async def run_until_closed(self) -> None:
        """Consume events until the socket closes. Hooks handle the data."""
        async for _ in self.events():
            pass


# ── ephemeral-token mint (for the browser/WebRTC path) ───────────────────


async def mint_ephemeral_session(
    api_key: str,
    *,
    tools: list[dict[str, Any]] | None = None,
    instructions: str = "",
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Ask OpenAI for a short-lived Realtime session token.

    Returned payload contains ``client_secret.value`` which the browser
    uses as a bearer for the WebRTC ``/v1/realtime`` endpoint. The real
    ``OPENAI_API_KEY`` never leaves this process.
    """
    import httpx

    payload: dict[str, Any] = {
        "model": model,
        "voice": voice,
        "modalities": ["audio", "text"],
        "instructions": instructions,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


# ── test harness ─────────────────────────────────────────────────────────


async def _selftest() -> None:  # pragma: no cover - manual
    import sys
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        print("set OPENAI_API_KEY to run the selftest", file=sys.stderr)
        return
    async with RealtimeSession(key, instructions="Say hello.") as rt:
        async def _pr(text: str) -> None:
            print(text, end="", flush=True)
        rt.on_assistant_transcript = _pr
        await rt.request_response()
        try:
            await asyncio.wait_for(rt.run_until_closed(), timeout=10.0)
        except asyncio.TimeoutError:
            pass
        print()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_selftest())
