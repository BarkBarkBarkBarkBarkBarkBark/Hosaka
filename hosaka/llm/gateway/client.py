"""OpenClaw Gateway WebSocket client.

Responsibilities:
  - Open/close WebSocket to local gateway
  - Wait for connect.challenge, send connect request
  - Handle req/res/event framing
  - Request/response correlation by id
  - Feature discovery from hello-ok
  - Token/password auth with device-token persistence
  - Reconnect with bounded exponential backoff
  - Graceful shutdown
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from enum import Enum
from typing import Any, Callable

from hosaka.llm.gateway.device import (
    get_device_id,
    get_device_token,
    save_device_token,
)
from hosaka.llm.gateway.protocol import (
    CLIENT_ID,
    CLIENT_MODE,
    CLIENT_PLATFORM,
    CLIENT_USER_AGENT,
    CLIENT_VERSION,
    DEFAULT_GATEWAY_HOST,
    DEFAULT_GATEWAY_PORT,
    DEFAULT_GATEWAY_URL,
    HANDSHAKE_TIMEOUT,
    OPERATOR_SCOPES,
    PROTOCOL_VERSION,
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_ATTEMPTS,
    RECONNECT_MAX_DELAY,
    REQUEST_TIMEOUT,
    get_error,
    is_event,
    is_ok,
    is_response,
    make_id,
    make_req,
)

log = logging.getLogger("hosaka.gateway")


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    PAIRING_REQUIRED = "pairing-required"
    READY = "ready"
    STREAMING = "streaming"
    ERROR = "error"


class GatewayError(Exception):
    """Raised for gateway-level errors."""

    def __init__(self, message: str, code: str = "", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class PairingRequiredError(GatewayError):
    """Raised when device pairing approval is needed."""
    pass


class AuthError(GatewayError):
    """Raised for auth failures."""
    pass


EventCallback = Callable[[dict], None]


class OpenClawGatewayClient:
    """Synchronous WebSocket client for the OpenClaw Gateway."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        password: str | None = None,
    ):
        self._url = url or os.getenv("OPENCLAW_GATEWAY_URL", DEFAULT_GATEWAY_URL)
        self._token = token or os.getenv("OPENCLAW_GATEWAY_TOKEN")
        self._password = password or os.getenv("OPENCLAW_GATEWAY_PASSWORD")
        self._ws: Any = None
        self._state = ConnectionState.DISCONNECTED
        self._hello_payload: dict = {}
        self._features: dict = {}
        self._policy: dict = {}
        self._lock = threading.Lock()
        self._event_callbacks: list[EventCallback] = []
        self._pending_responses: dict[str, threading.Event] = {}
        self._response_store: dict[str, dict] = {}
        self._listener_thread: threading.Thread | None = None
        self._shutdown = threading.Event()

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state == ConnectionState.READY

    @property
    def features(self) -> dict:
        return self._features

    @property
    def policy(self) -> dict:
        return self._policy

    def on_event(self, callback: EventCallback) -> None:
        """Register a callback for gateway events."""
        self._event_callbacks.append(callback)

    # ── connection ───────────────────────────────────────────────────────

    def connect(self) -> dict:
        """Connect to gateway, perform handshake. Returns hello-ok payload.

        Raises GatewayError, AuthError, PairingRequiredError on failure.
        """
        from websockets.sync.client import connect

        self._shutdown.clear()
        self._state = ConnectionState.CONNECTING

        try:
            self._ws = connect(self._url, close_timeout=5)
        except Exception as exc:
            self._state = ConnectionState.ERROR
            raise GatewayError(f"WebSocket connect failed: {exc}") from exc

        self._state = ConnectionState.AUTHENTICATING

        # Step 1: wait for connect.challenge
        challenge_nonce = None
        try:
            raw = self._ws.recv(timeout=HANDSHAKE_TIMEOUT)
            first_frame = json.loads(raw)

            if is_event(first_frame, "connect.challenge"):
                challenge_nonce = first_frame.get("payload", {}).get("nonce")
            elif is_ok(first_frame):
                # Gateway skipped challenge (rare, some localhost configs)
                self._handle_hello_ok(first_frame.get("payload", {}))
                self._start_listener()
                return self._hello_payload
            else:
                log.warning("Unexpected first frame: %s", first_frame.get("type"))
        except Exception as exc:
            self._state = ConnectionState.ERROR
            self._close_ws()
            raise GatewayError(f"Handshake failed waiting for challenge: {exc}") from exc

        # Step 2: send connect request
        connect_params = self._build_connect_params(challenge_nonce)
        connect_req = make_req("connect", connect_params)

        try:
            self._ws.send(json.dumps(connect_req))
        except Exception as exc:
            self._state = ConnectionState.ERROR
            self._close_ws()
            raise GatewayError(f"Failed to send connect: {exc}") from exc

        # Step 3: wait for hello-ok response
        try:
            raw = self._ws.recv(timeout=HANDSHAKE_TIMEOUT)
            res = json.loads(raw)
        except Exception as exc:
            self._state = ConnectionState.ERROR
            self._close_ws()
            raise GatewayError(f"Handshake failed waiting for hello-ok: {exc}") from exc

        if not is_response(res, connect_req["id"]):
            self._state = ConnectionState.ERROR
            self._close_ws()
            raise GatewayError(f"Unexpected response to connect: {json.dumps(res)[:200]}")

        if is_ok(res):
            self._handle_hello_ok(res.get("payload", {}))
            self._start_listener()
            return self._hello_payload

        # Auth/pairing failure
        error = get_error(res)
        error_msg = error.get("message", "Unknown auth error")
        error_code = error.get("code", "")
        details = error.get("details", {})

        self._close_ws()

        if "pairing" in error_msg.lower() or "PAIRING" in error_code:
            self._state = ConnectionState.PAIRING_REQUIRED
            raise PairingRequiredError(
                f"Device pairing required: {error_msg}\n"
                "Run these commands to approve:\n"
                "  openclaw devices list\n"
                "  openclaw devices approve <requestId>",
                code=error_code,
                details=details,
            )

        rec = details.get("recommendedNextStep", "")
        if details.get("canRetryWithDeviceToken") and get_device_token():
            # Retry once with device token
            self._token = None
            return self.connect()

        self._state = ConnectionState.ERROR
        hint = ""
        if rec == "update_auth_credentials":
            hint = "\nFix: check OPENCLAW_GATEWAY_TOKEN in your .env"
        elif rec == "update_auth_configuration":
            hint = "\nFix: check gateway auth config with 'openclaw config get gateway.auth'"
        raise AuthError(f"Auth failed: {error_msg}{hint}", code=error_code, details=details)

    def _build_connect_params(self, challenge_nonce: str | None = None) -> dict:
        """Build the connect request params."""
        device_id = get_device_id()

        params: dict[str, Any] = {
            "minProtocol": PROTOCOL_VERSION,
            "maxProtocol": PROTOCOL_VERSION,
            "client": {
                "id": CLIENT_ID,
                "version": CLIENT_VERSION,
                "platform": CLIENT_PLATFORM,
                "mode": CLIENT_MODE,
            },
            "role": "operator",
            "scopes": list(OPERATOR_SCOPES),
            "caps": [],
            "commands": [],
            "permissions": {},
            "locale": "en-US",
            "userAgent": CLIENT_USER_AGENT,
            "device": {
                "id": device_id,
            },
        }

        # Auth: token > password > device token
        if self._token:
            params["auth"] = {"token": self._token}
        elif self._password:
            params["auth"] = {"password": self._password}
        else:
            dt = get_device_token()
            if dt:
                params["auth"] = {"deviceToken": dt}

        return params

    def _handle_hello_ok(self, payload: dict) -> None:
        """Process the hello-ok payload."""
        self._hello_payload = payload
        self._policy = payload.get("policy", {})
        self._features = payload.get("features", {})
        self._state = ConnectionState.READY

        # Persist device token if issued
        auth = payload.get("auth", {})
        dt = auth.get("deviceToken")
        if dt:
            role = auth.get("role", "operator")
            scopes = auth.get("scopes", [])
            save_device_token(dt, role, scopes)
            log.info("Device token saved (role=%s)", role)

    # ── listener thread ──────────────────────────────────────────────────

    def _start_listener(self) -> None:
        """Start background thread to receive events."""
        self._listener_thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="gw-listener"
        )
        self._listener_thread.start()

    def _listen_loop(self) -> None:
        """Background loop receiving frames from the gateway."""
        while not self._shutdown.is_set():
            try:
                raw = self._ws.recv(timeout=2.0)
            except TimeoutError:
                continue
            except Exception:
                if not self._shutdown.is_set():
                    self._state = ConnectionState.ERROR
                break

            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue

            frame_type = frame.get("type")

            if frame_type == "res":
                req_id = frame.get("id")
                if req_id and req_id in self._pending_responses:
                    self._response_store[req_id] = frame
                    self._pending_responses[req_id].set()
            elif frame_type == "event":
                for cb in self._event_callbacks:
                    try:
                        cb(frame)
                    except Exception:
                        pass

    # ── RPC ──────────────────────────────────────────────────────────────

    def request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> dict:
        """Send an RPC request and wait for the correlated response.

        Returns the full response frame.
        Raises GatewayError on timeout or transport failure.
        """
        if not self._ws or self._state not in (
            ConnectionState.READY,
            ConnectionState.STREAMING,
        ):
            raise GatewayError(f"Not connected (state={self._state})")

        req = make_req(method, params)
        req_id = req["id"]
        done = threading.Event()

        self._pending_responses[req_id] = done

        try:
            with self._lock:
                self._ws.send(json.dumps(req))
        except Exception as exc:
            self._pending_responses.pop(req_id, None)
            raise GatewayError(f"Send failed: {exc}") from exc

        if not done.wait(timeout=timeout):
            self._pending_responses.pop(req_id, None)
            raise GatewayError(f"Request {method} timed out after {timeout}s")

        self._pending_responses.pop(req_id, None)
        return self._response_store.pop(req_id)

    def request_ok(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> dict:
        """Send RPC and return payload if ok, else raise GatewayError."""
        res = self.request(method, params, timeout)
        if is_ok(res):
            return res.get("payload", {})
        error = get_error(res)
        raise GatewayError(
            error.get("message", f"{method} failed"),
            code=error.get("code", ""),
            details=error.get("details", {}),
        )

    # ── reconnect ────────────────────────────────────────────────────────

    def reconnect(self, max_attempts: int = RECONNECT_MAX_ATTEMPTS) -> dict:
        """Reconnect with bounded exponential backoff.

        Returns hello-ok payload on success.
        Raises GatewayError after exhausting attempts.
        """
        self.disconnect()
        delay = RECONNECT_BASE_DELAY

        for attempt in range(1, max_attempts + 1):
            log.info("Reconnect attempt %d/%d (delay=%.1fs)", attempt, max_attempts, delay)
            try:
                return self.connect()
            except GatewayError as exc:
                if isinstance(exc, (PairingRequiredError, AuthError)):
                    raise  # Don't retry auth/pairing errors
                if attempt == max_attempts:
                    raise GatewayError(
                        f"Reconnect failed after {max_attempts} attempts: {exc}"
                    ) from exc
            time.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

        raise GatewayError("Reconnect exhausted")  # unreachable

    # ── health ───────────────────────────────────────────────────────────

    def health(self) -> dict:
        """Call gateway health RPC."""
        return self.request_ok("health")

    def status(self) -> dict:
        """Call gateway status RPC."""
        return self.request_ok("status")

    # ── shutdown ─────────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """Gracefully close the connection."""
        self._shutdown.set()
        self._close_ws()
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=3)
        self._listener_thread = None
        self._state = ConnectionState.DISCONNECTED

    def _close_ws(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ── static availability check ────────────────────────────────────────

    @staticmethod
    def is_gateway_reachable(
        host: str = DEFAULT_GATEWAY_HOST,
        port: int = DEFAULT_GATEWAY_PORT,
    ) -> bool:
        """TCP probe to check if gateway is accepting connections."""
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False
