"""OpenClaw Gateway adapter — public API.

Usage:
    from hosaka.llm.gateway import GatewayAdapter

    adapter = GatewayAdapter()
    adapter.connect()
    for token in adapter.chat_stream("hello"):
        print(token, end="")
    adapter.disconnect()
"""

from __future__ import annotations

import logging
import os

from hosaka.llm.gateway.client import (
    AuthError,
    ConnectionState,
    GatewayError,
    OpenClawGatewayClient,
    PairingRequiredError,
)
from hosaka.llm.gateway.runner import OpenClawChatRunner
from hosaka.llm.gateway.session import OpenClawSessionManager

log = logging.getLogger("hosaka.gateway")

__all__ = [
    "GatewayAdapter",
    "GatewayError",
    "AuthError",
    "PairingRequiredError",
    "ConnectionState",
]


class GatewayAdapter:
    """High-level adapter between Hosaka terminal and OpenClaw Gateway.

    Wraps client + session + runner into one interface the terminal can use.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        password: str | None = None,
        session_key: str | None = None,
        agent_id: str | None = None,
    ):
        self._client = OpenClawGatewayClient(url=url, token=token, password=password)
        self._session = OpenClawSessionManager(
            self._client, session_key=session_key, agent_id=agent_id,
        )
        self._runner = OpenClawChatRunner(self._client, self._session)

    @property
    def state(self) -> ConnectionState:
        return self._client.state

    @property
    def is_ready(self) -> bool:
        return self._client.is_ready

    @property
    def session_key(self) -> str:
        return self._session.session_key

    # ── lifecycle ────────────────────────────────────────────────────────

    def connect(self) -> dict:
        """Connect to gateway, resolve session, subscribe to events.

        Returns hello-ok payload.
        """
        hello = self._client.connect()
        self._session.resolve_or_create()
        self._session.subscribe()
        return hello

    def disconnect(self) -> None:
        """Graceful shutdown."""
        try:
            self._session.unsubscribe()
        except Exception:
            pass
        self._client.disconnect()

    def reconnect(self) -> dict:
        """Reconnect with backoff, re-resolve session, re-subscribe."""
        hello = self._client.reconnect()
        self._session.resolve_or_create()
        self._session.resubscribe()
        return hello

    # ── chat ─────────────────────────────────────────────────────────────

    def chat_stream(self, message: str):
        """Send a message and yield streamed assistant tokens."""
        yield from self._runner.send_streaming(message)

    def chat_sync(self, message: str) -> str:
        """Send a message and return the complete response."""
        return self._runner.send_sync(message)

    def abort(self) -> None:
        """Abort the active chat run."""
        self._runner.abort()

    # ── session ──────────────────────────────────────────────────────────

    def load_history(self, limit: int = 50) -> list[dict]:
        """Load chat history for the active session."""
        return self._session.load_history(limit)

    def reset_session(self) -> None:
        """Reset (clear) the active session."""
        self._session.reset_session()

    def switch_session(self, new_key: str) -> str:
        """Switch to a different session."""
        return self._session.switch_session(new_key)

    # ── health ───────────────────────────────────────────────────────────

    def health(self) -> dict:
        return self._client.health()

    # ── static ───────────────────────────────────────────────────────────

    @staticmethod
    def is_available() -> bool:
        """Return True if websockets is importable and gateway is reachable."""
        try:
            import websockets  # noqa: F401
        except ImportError:
            return False
        url = (
            os.getenv("OPENCLAW_GATEWAY_URL")
            or os.getenv("PICOCLAW_GATEWAY_URL")
        )
        return OpenClawGatewayClient.is_gateway_reachable(url=url)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
