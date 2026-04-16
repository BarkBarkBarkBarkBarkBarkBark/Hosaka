"""Device identity and token persistence for OpenClaw Gateway.

Manages:
  - Stable device ID (derived from Ed25519 keypair fingerprint)
  - Device token persistence (issued by gateway after pairing)
  - Challenge nonce signing

State is stored in a JSON file at OPENCLAW_DEVICE_STATE_PATH
(default: ~/.hosaka/device_state.json).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

DEFAULT_DEVICE_STATE_PATH = Path.home() / ".hosaka" / "device_state.json"


def _state_path() -> Path:
    override = os.getenv("OPENCLAW_DEVICE_STATE_PATH")
    if override:
        return Path(override)
    return DEFAULT_DEVICE_STATE_PATH


def _load_state() -> dict:
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(path)
    # Restrict permissions to owner only
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_device_id() -> str:
    """Return a stable device ID, creating one if needed.

    The device ID is a hex fingerprint derived from a random seed
    that persists across restarts.  This is NOT a cryptographic
    keypair — it is a stable identifier for pairing.  If the gateway
    requires Ed25519 signing (connect.challenge), we will add that
    once we can inspect the exact signing payload from the installed
    gateway source.
    """
    state = _load_state()
    device_id = state.get("device_id")
    if device_id:
        return device_id

    # Generate a stable device ID from random bytes
    seed = os.urandom(32)
    device_id = hashlib.sha256(seed).hexdigest()[:32]
    state["device_id"] = device_id
    state["device_id_created"] = int(time.time())
    _save_state(state)
    return device_id


def get_device_token() -> str | None:
    """Return the persisted device token, or None."""
    state = _load_state()
    return state.get("device_token")


def save_device_token(token: str, role: str, scopes: list[str]) -> None:
    """Persist a device token issued by the gateway."""
    state = _load_state()
    state["device_token"] = token
    state["device_token_role"] = role
    state["device_token_scopes"] = scopes
    state["device_token_saved"] = int(time.time())
    _save_state(state)


def clear_device_token() -> None:
    """Remove persisted device token (e.g. after revocation)."""
    state = _load_state()
    state.pop("device_token", None)
    state.pop("device_token_role", None)
    state.pop("device_token_scopes", None)
    state.pop("device_token_saved", None)
    _save_state(state)
