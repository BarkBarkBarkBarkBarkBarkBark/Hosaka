"""OpenClaw chat runner — send messages and stream responses.

Responsibilities:
  - Send user message into active session via chat.send
  - Attach idempotencyKey for side-effecting sends
  - Stream assistant output incrementally via events
  - Support abort/interrupt via chat.abort / sessions.abort
  - Map tool events and run states for terminal display
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Generator, TYPE_CHECKING

from hosaka.llm.gateway.protocol import make_idempotency_key, make_req

if TYPE_CHECKING:
    from hosaka.llm.gateway.client import OpenClawGatewayClient
    from hosaka.llm.gateway.session import OpenClawSessionManager

log = logging.getLogger("hosaka.gateway.runner")

# Event names we care about for streaming
_CHAT_TOKEN_EVENTS = {"chat.token", "chat.delta"}
_CHAT_MESSAGE_EVENTS = {"chat.message", "chat.inject"}
_CHAT_DONE_EVENTS = {"chat.done", "chat.end", "chat.complete"}
_SESSION_TOKEN_EVENTS = {"session.message"}
_SESSION_TOOL_EVENTS = {"session.tool"}
_TERMINAL_EVENTS = (
    _CHAT_TOKEN_EVENTS
    | _CHAT_MESSAGE_EVENTS
    | _CHAT_DONE_EVENTS
    | _SESSION_TOKEN_EVENTS
    | _SESSION_TOOL_EVENTS
)


class ChatRunState:
    """Tracks the state of a single chat run."""

    def __init__(self, idempotency_key: str, session_key: str):
        self.idempotency_key = idempotency_key
        self.session_key = session_key
        self.active = True
        self.collected_text: list[str] = []
        self.tool_calls: list[dict] = []
        self._queue: queue.Queue[dict | None] = queue.Queue()
        self._done = threading.Event()

    def push_event(self, frame: dict) -> None:
        """Push a gateway event frame into this run's queue."""
        self._queue.put(frame)

    def mark_done(self) -> None:
        """Signal that the run has completed."""
        self.active = False
        self._done.set()
        self._queue.put(None)  # sentinel

    def events(self, timeout: float = 120.0) -> Generator[dict, None, None]:
        """Yield event frames until the run completes."""
        while self.active:
            try:
                frame = self._queue.get(timeout=timeout)
            except queue.Empty:
                break
            if frame is None:
                break
            yield frame


class OpenClawChatRunner:
    """Sends messages and streams responses from the gateway."""

    def __init__(
        self,
        client: OpenClawGatewayClient,
        session_mgr: OpenClawSessionManager,
    ):
        self._client = client
        self._session = session_mgr
        self._active_run: ChatRunState | None = None
        self._event_handler_registered = False

    def _ensure_event_handler(self) -> None:
        """Register the event router on the gateway client (once)."""
        if self._event_handler_registered:
            return
        self._client.on_event(self._on_event)
        self._event_handler_registered = True

    def _on_event(self, frame: dict) -> None:
        """Route gateway events to the active chat run."""
        run = self._active_run
        if run is None or not run.active:
            return

        event = frame.get("event", "")

        if event in _TERMINAL_EVENTS:
            run.push_event(frame)

        # Detect run completion
        if event in _CHAT_DONE_EVENTS:
            run.mark_done()

    # ── send + stream ────────────────────────────────────────────────────

    def send_streaming(self, message: str) -> Generator[str, None, None]:
        """Send a user message and yield streamed assistant tokens.

        This is the primary interface for the terminal chat REPL.
        Blocks until the assistant response is complete.
        """
        self._ensure_event_handler()
        session_key = self._session.session_key
        idempotency_key = make_idempotency_key()

        run = ChatRunState(idempotency_key, session_key)
        self._active_run = run

        # Send via chat.send (the execution path official clients use)
        params: dict = {
            "message": message,
            "sessionKey": session_key,
            "idempotencyKey": idempotency_key,
        }

        try:
            res = self._client.request("chat.send", params, timeout=10.0)
        except Exception as exc:
            run.mark_done()
            self._active_run = None
            yield f"[gateway error: {exc}]"
            return

        # chat.send may return immediately (async execution) or with content
        payload = res.get("payload", {})
        if res.get("ok") is False:
            error = res.get("error", {})
            run.mark_done()
            self._active_run = None
            yield f"[gateway error: {error.get('message', 'unknown')}]"
            return

        # If the response contains text directly, yield it
        direct_text = payload.get("text") or payload.get("content", "")
        if direct_text:
            run.collected_text.append(direct_text)
            yield direct_text

        # Stream events from the run queue
        got_streamed = False
        for frame in run.events(timeout=120.0):
            event = frame.get("event", "")
            event_payload = frame.get("payload", {})

            if event in _CHAT_TOKEN_EVENTS:
                token = event_payload.get("token") or event_payload.get("delta", "")
                if token:
                    got_streamed = True
                    run.collected_text.append(token)
                    yield token

            elif event in _SESSION_TOKEN_EVENTS:
                # session.message may carry full assistant messages
                role = event_payload.get("role", "")
                text = event_payload.get("text") or event_payload.get("content", "")
                if role == "assistant" and text and not got_streamed:
                    run.collected_text.append(text)
                    yield text
                    got_streamed = True

            elif event in _SESSION_TOOL_EVENTS:
                tool_name = event_payload.get("name") or event_payload.get("tool", "")
                tool_state = event_payload.get("state", "")
                if tool_name and tool_state == "running":
                    run.tool_calls.append(event_payload)
                    yield f"\n[tool: {tool_name}] "
                elif tool_name and tool_state == "complete":
                    yield f"[done]\n"

            elif event in _CHAT_MESSAGE_EVENTS:
                text = event_payload.get("text") or event_payload.get("content", "")
                role = event_payload.get("role", "")
                if text and role == "assistant" and not got_streamed:
                    run.collected_text.append(text)
                    yield text
                    got_streamed = True

            elif event in _CHAT_DONE_EVENTS:
                break

        self._active_run = None

    def send_sync(self, message: str) -> str:
        """Send a message and return the complete response text."""
        chunks = list(self.send_streaming(message))
        return "".join(chunks)

    # ── abort ────────────────────────────────────────────────────────────

    def abort(self) -> None:
        """Abort the active chat run."""
        run = self._active_run
        if run is None:
            return

        session_key = run.session_key
        run.mark_done()
        self._active_run = None

        # Try both abort methods
        try:
            self._client.request("chat.abort", {"sessionKey": session_key}, timeout=5.0)
        except Exception:
            try:
                self._client.request("sessions.abort", {"sessionKey": session_key}, timeout=5.0)
            except Exception:
                pass
