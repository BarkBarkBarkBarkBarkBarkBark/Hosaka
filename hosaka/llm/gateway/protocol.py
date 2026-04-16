"""Protocol constants and frame helpers for OpenClaw Gateway WS.

Source of truth: https://docs.openclaw.ai/gateway/protocol
Protocol version: 3
Transport: WebSocket, text frames with JSON payloads.
"""

from __future__ import annotations

import uuid

PROTOCOL_VERSION = 3

# Default gateway location
DEFAULT_GATEWAY_URL = "ws://127.0.0.1:18789"
DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 18789

# Client identity
CLIENT_ID = "hosaka-field-terminal"
CLIENT_VERSION = "1.0.0"
CLIENT_PLATFORM = "linux"
CLIENT_MODE = "operator"
CLIENT_USER_AGENT = f"{CLIENT_ID}/{CLIENT_VERSION}"

# Operator scopes
OPERATOR_SCOPES = ["operator.read", "operator.write"]

# Default session key
DEFAULT_SESSION_KEY = "agent:main:main"

# Tick keepalive default (from hello-ok.policy.tickIntervalMs)
DEFAULT_TICK_INTERVAL_MS = 15000

# Timeouts
HANDSHAKE_TIMEOUT = 10.0
REQUEST_TIMEOUT = 120.0
RECONNECT_MAX_ATTEMPTS = 10
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0


def make_id() -> str:
    """Generate a unique request id."""
    return uuid.uuid4().hex[:12]


def make_idempotency_key() -> str:
    """Generate an idempotency key for side-effecting RPCs."""
    return uuid.uuid4().hex


def make_req(method: str, params: dict | None = None) -> dict:
    """Build a gateway request frame."""
    frame: dict = {
        "type": "req",
        "id": make_id(),
        "method": method,
        "params": params or {},
    }
    return frame


def is_response(frame: dict, req_id: str) -> bool:
    """Check if frame is a response to a specific request."""
    return frame.get("type") == "res" and frame.get("id") == req_id


def is_event(frame: dict, event_name: str | None = None) -> bool:
    """Check if frame is an event, optionally matching a specific event name."""
    if frame.get("type") != "event":
        return False
    if event_name is not None:
        return frame.get("event") == event_name
    return True


def is_ok(frame: dict) -> bool:
    """Check if a response frame indicates success."""
    return frame.get("type") == "res" and frame.get("ok") is True


def get_error(frame: dict) -> dict:
    """Extract error details from a failed response frame."""
    return frame.get("error", {})
