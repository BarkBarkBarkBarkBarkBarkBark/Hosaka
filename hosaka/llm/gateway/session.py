"""OpenClaw session manager.

Responsibilities:
  - Resolve or create the active session
  - Configurable session key (default: agent:main:main)
  - Fetch normalized history on load and after reconnect
  - Subscribe to session message/tool event streams
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from hosaka.llm.gateway.protocol import DEFAULT_SESSION_KEY, make_idempotency_key

if TYPE_CHECKING:
    from hosaka.llm.gateway.client import OpenClawGatewayClient

log = logging.getLogger("hosaka.gateway.session")


class OpenClawSessionManager:
    """Manages the active chat session on the gateway."""

    def __init__(
        self,
        client: OpenClawGatewayClient,
        session_key: str | None = None,
        agent_id: str | None = None,
    ):
        self._client = client
        self._session_key = (
            session_key
            or os.getenv("OPENCLAW_SESSION_KEY", DEFAULT_SESSION_KEY)
        )
        self._agent_id = agent_id or os.getenv("OPENCLAW_AGENT_ID")
        self._resolved_key: str | None = None
        self._subscribed = False

    @property
    def session_key(self) -> str:
        return self._resolved_key or self._session_key

    @property
    def is_subscribed(self) -> bool:
        return self._subscribed

    # ── session lifecycle ─────────────────────────────────────────────────

    def resolve_or_create(self) -> str:
        """Resolve the session key, creating a session if needed.

        Returns the canonical session key.
        """
        try:
            payload = self._client.request_ok(
                "sessions.resolve",
                {"sessionKey": self._session_key},
            )
            self._resolved_key = payload.get("sessionKey", self._session_key)
            log.info("Session resolved: %s", self._resolved_key)
            return self._resolved_key
        except Exception:
            log.info("sessions.resolve failed, trying sessions.create")

        # Create new session
        params: dict = {"sessionKey": self._session_key}
        if self._agent_id:
            params["agentId"] = self._agent_id

        try:
            payload = self._client.request_ok("sessions.create", params)
            self._resolved_key = payload.get("sessionKey", self._session_key)
            log.info("Session created: %s", self._resolved_key)
            return self._resolved_key
        except Exception as exc:
            log.warning("sessions.create failed: %s", exc)
            # Fall back to raw key
            self._resolved_key = self._session_key
            return self._resolved_key

    def subscribe(self) -> None:
        """Subscribe to session message and tool events."""
        key = self.session_key
        try:
            self._client.request_ok(
                "sessions.messages.subscribe",
                {"sessionKey": key},
            )
            self._subscribed = True
            log.info("Subscribed to session events: %s", key)
        except Exception as exc:
            log.warning("sessions.messages.subscribe failed: %s", exc)
            self._subscribed = False

    def unsubscribe(self) -> None:
        """Unsubscribe from session events."""
        if not self._subscribed:
            return
        key = self.session_key
        try:
            self._client.request_ok(
                "sessions.messages.unsubscribe",
                {"sessionKey": key},
            )
        except Exception:
            pass
        self._subscribed = False

    # ── history ──────────────────────────────────────────────────────────

    def load_history(self, limit: int = 50) -> list[dict]:
        """Fetch chat history for the active session.

        Returns a list of message dicts with at least {role, content}.
        """
        try:
            payload = self._client.request_ok(
                "chat.history",
                {"sessionKey": self.session_key, "limit": limit},
            )
            messages = payload.get("messages", [])
            return messages
        except Exception as exc:
            log.warning("chat.history failed: %s", exc)
            return []

    # ── session state ────────────────────────────────────────────────────

    def get_session(self) -> dict:
        """Get full session row."""
        return self._client.request_ok(
            "sessions.get",
            {"sessionKey": self.session_key},
        )

    def reset_session(self) -> None:
        """Reset the active session (clears conversation)."""
        self._client.request_ok(
            "sessions.reset",
            {"sessionKey": self.session_key},
        )
        log.info("Session reset: %s", self.session_key)

    def switch_session(self, new_key: str) -> str:
        """Switch to a different session key."""
        if self._subscribed:
            self.unsubscribe()
        self._session_key = new_key
        self._resolved_key = None
        resolved = self.resolve_or_create()
        self.subscribe()
        return resolved

    # ── reconnect ────────────────────────────────────────────────────────

    def resubscribe(self) -> None:
        """Re-subscribe after reconnect. Events are not replayed."""
        self._subscribed = False
        self.subscribe()
