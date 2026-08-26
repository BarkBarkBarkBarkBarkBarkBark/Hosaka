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

DEFAULT_MODEL = os.getenv("HOSAKA_VOICE_MODEL", "gpt-realtime")
DEFAULT_VOICE = os.getenv("HOSAKA_VOICE_VOICE", "marin")
REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"
PCM16_24K = {"type": "audio/pcm", "rate": 24_000}

_AUDIO_DELTA = frozenset({"response.output_audio.delta", "response.audio.delta"})
_AUDIO_DONE = frozenset({"response.output_audio.done", "response.audio.done"})
_TRANSCRIPT_DELTA = frozenset(
    {"response.output_audio_transcript.delta", "response.audio_transcript.delta"}
)


def _openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")


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


def ga_session_update(
    *,
    model: str,
    voice: str,
    instructions: str,
    tools: list[dict[str, Any]],
    auto_create_response: bool,
) -> dict[str, Any]:
    """GA ``session.update`` body. Beta fields (``modalities``, flat
    ``input_audio_format``, top-level ``voice``) are rejected since 2026-05-12.
    """
    session: dict[str, Any] = {
        "type": "realtime",
        "model": model,
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": dict(PCM16_24K),
                "transcription": {"model": "gpt-4o-mini-transcribe"},
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "medium",
                    "create_response": auto_create_response,
                    "interrupt_response": True,
                },
            },
            "output": {
                "format": dict(PCM16_24K),
                "voice": voice,
            },
        },
        "instructions": instructions,
    }
    if tools:
        session["tools"] = tools
        session["tool_choice"] = "auto"
    return {"type": "session.update", "session": session}


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
        auto_create_response: bool = True,
    ) -> None:
        if not api_key:
            raise RealtimeError("OPENAI_API_KEY not set")
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._tools = tools or []
        self._instructions = instructions
        self._auto_create_response = auto_create_response
        self._ws: ClientConnection | None = None

        # Caller-supplied event hooks. All async, called from the reader task.
        self.on_audio: AudioHandler | None = None
        self.on_user_transcript: TextHandler | None = None
        self.on_user_partial: TextHandler | None = None
        self.on_assistant_transcript: TextHandler | None = None
        self.on_state: StateHandler | None = None
        self.on_tool: ToolHandler | None = None
        self.on_response_done: Callable[[], Awaitable[None]] | None = None
        self.on_trace: Callable[[str, str], None] | None = None
        self._bg: set[asyncio.Task[None]] = set()

    # ── context manager ───────────────────────────────────────────────

    async def __aenter__(self) -> "RealtimeSession":
        url = REALTIME_URL.format(model=self._model)
        headers = [("Authorization", f"Bearer {self._api_key}")]
        websockets = _require_websockets()
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=headers,
                max_size=16 * 1024 * 1024,
                ping_interval=None,
                ping_timeout=None,
            )
            await self._send(
                ga_session_update(
                    model=self._model,
                    voice=self._voice,
                    instructions=self._instructions,
                    tools=self._tools,
                    auto_create_response=self._auto_create_response,
                )
            )
        except RealtimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            await self.__aexit__()
            raise RealtimeError(f"realtime handshake failed: {exc}") from exc
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        for task in list(self._bg):
            task.cancel()
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await asyncio.wait_for(ws.close(), timeout=1.0)
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

    async def speak_verbatim(self, text: str) -> None:
        """Ask Realtime to speak `text` as audio. Used when SocialEngine authorizes."""
        spoken = text.strip()
        if not spoken:
            return
        await self._send(
            {
                "type": "response.create",
                "response": {
                    "output_modalities": ["audio"],
                    "instructions": (
                        "Speak the following text verbatim. "
                        "Do not add commentary or questions.\n\n"
                        f"{spoken}"
                    ),
                },
            }
        )

    # ── receive loop ──────────────────────────────────────────────────

    def _spawn(self, coro: Awaitable[None]) -> None:
        """Run a hook without stalling the WebSocket reader."""
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            return
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    async def _run_hook(self, hook: Callable[..., Awaitable[None]] | None, *args: Any) -> None:
        if hook is None:
            return
        try:
            await hook(*args)
        except Exception:  # noqa: BLE001
            log.exception("realtime hook failed")

    async def _notify_state(self, state: str) -> None:
        self._spawn(self._run_hook(self.on_state, state))

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
        if self.on_trace is not None and etype and "delta" not in etype:
            detail = etype
            if etype == "error":
                err = evt.get("error") or {}
                detail = f"error {err.get('type','')}: {err.get('message','')}"[:160]
            elif etype == "response.function_call_arguments.done":
                detail = f"tool {evt.get('name','')}"
            elif etype == "conversation.item.input_audio_transcription.completed":
                detail = f"you {(evt.get('transcript') or '')[:80]}"
            elif "delta" in etype:
                detail = etype
            try:
                self.on_trace(etype, detail)
            except Exception:  # noqa: BLE001
                pass
        if etype in _AUDIO_DELTA:
            if self.on_audio is not None:
                try:
                    pcm = base64.b64decode(evt.get("delta", ""))
                    await self.on_audio(pcm)
                except Exception:  # noqa: BLE001
                    log.exception("on_audio hook failed")
        elif etype in _TRANSCRIPT_DELTA:
            if self.on_assistant_transcript is not None:
                try:
                    await self.on_assistant_transcript(str(evt.get("delta", "")))
                except Exception:  # noqa: BLE001
                    log.exception("on_assistant_transcript hook failed")
        elif etype == "conversation.item.input_audio_transcription.delta":
            delta = str(evt.get("delta") or evt.get("transcript") or "")
            if delta:
                self._spawn(self._run_hook(self.on_user_partial, delta))
        elif etype == "conversation.item.input_audio_transcription.completed":
            self._spawn(
                self._run_hook(
                    self.on_user_transcript, str(evt.get("transcript", ""))
                )
            )
        elif etype == "input_audio_buffer.speech_started":
            await self._notify_state("listening")
        elif etype == "input_audio_buffer.speech_stopped":
            await self._notify_state("thinking")
        elif etype in _AUDIO_DONE:
            await self._notify_state("idle")
            self._spawn(self._run_hook(self.on_response_done))
        elif etype == "response.function_call_arguments.done":
            call_id = str(evt.get("call_id", ""))
            name = str(evt.get("name", ""))
            raw = evt.get("arguments", "{}")
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                args = {}
            self._spawn(self._run_tool(call_id, name, args))
        elif etype == "error":
            err = evt.get("error", {})
            log.debug(
                "realtime error: %s (%s)",
                err.get("message"),
                err.get("type"),
            )

    async def _run_tool(self, call_id: str, name: str, args: dict[str, Any]) -> None:
        output = f"tool {name}: no dispatcher wired"
        if self.on_tool is not None:
            try:
                output = await self.on_tool(name, args)
            except Exception as exc:  # noqa: BLE001
                log.exception("tool %s crashed", name)
                output = f"{name}: crashed ({exc})"
        try:
            await self._submit_tool_result(call_id, output)
        except Exception:  # noqa: BLE001
            log.exception("tool result submit failed")

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

    session: dict[str, Any] = {
        "type": "realtime",
        "model": model,
        # OpenAI's GA Realtime endpoint only accepts a single modality per
        # session: either ["audio"] or ["text"]. Asking for both returns 400
        # "Invalid modalities". Audio responses still include a text transcript
        # in the event stream, so ["audio"] is what we want for the orb.
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "transcription": {"model": "gpt-4o-mini-transcribe"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600,
                },
            },
            "output": {"voice": voice},
        },
        "instructions": instructions,
    }
    if tools:
        session["tools"] = tools
        session["tool_choice"] = "auto"

    base = _openai_base_url()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{base}/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"session": session},
        )
        if resp.status_code != 404:
            if resp.status_code >= 400:
                # Surface the OpenAI error body so callers can see *why*
                # instead of just "400 Bad Request". The status code and
                # error code are stashed on the exception so the API layer
                # can map them to clean error_code strings for the SPA.
                detail = resp.text.strip()
                code = ""
                try:
                    body = resp.json()
                    err = (body.get("error") or {}) if isinstance(body, dict) else {}
                    msg = err.get("message") or detail
                    code = err.get("code") or err.get("type") or ""
                    detail = f"{msg}" + (f" [{code}]" if code else "")
                except Exception:  # noqa: BLE001
                    pass
                error = RealtimeError(
                    f"openai /v1/realtime/client_secrets {resp.status_code}: {detail[:500]}"
                )
                error.status_code = resp.status_code  # type: ignore[attr-defined]
                error.openai_code = str(code) if code else ""  # type: ignore[attr-defined]
                raise error
            data = resp.json()
            data.setdefault("_hosaka_api_shape", "ga")
            data.setdefault("_hosaka_sdp_url", f"{base}/v1/realtime/calls")
            return data

        # Compatibility with older Realtime beta deployments. Remove after all
        # appliances have moved to the GA /client_secrets + /calls flow.
        legacy_payload: dict[str, Any] = {
            "model": model,
            "voice": voice,
            "modalities": ["audio"],
            "instructions": instructions,
        }
        if tools:
            legacy_payload["tools"] = tools
            legacy_payload["tool_choice"] = "auto"
        resp = await client.post(
            f"{base}/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1",
                "Content-Type": "application/json",
            },
            json=legacy_payload,
        )
        resp.raise_for_status()
        data = resp.json()
        data.setdefault("_hosaka_api_shape", "beta")
        data.setdefault("_hosaka_sdp_url", f"{base}/v1/realtime?model={model}")
        return data


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
