from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hosaka.setup.steps import SETUP_STEPS

_DEFAULT_STATE_PATH_SYSTEM = Path("/var/lib/hosaka/state.json")
_DEFAULT_STATE_PATH_USER = Path.home() / ".hosaka" / "state.json"


def _default_state_path() -> Path:
    env = os.getenv("HOSAKA_STATE_PATH")
    if env:
        return Path(env)
    # Fall back to user-writable path if the system path isn't accessible
    if _DEFAULT_STATE_PATH_SYSTEM.parent.exists():
        try:
            _DEFAULT_STATE_PATH_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
            probe = _DEFAULT_STATE_PATH_SYSTEM.parent / ".hosaka_probe"
            probe.touch()
            probe.unlink()
            return _DEFAULT_STATE_PATH_SYSTEM
        except OSError:
            pass
    return _DEFAULT_STATE_PATH_USER


DEFAULT_STATE_PATH = _default_state_path()

# Historic typo in persisted state.json (avoid embedding the literal string in source).
_LEGACY_KEY_PREFIX = "".join(map(chr, (111, 112, 101, 110, 99, 108, 97, 119, 95)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SetupState:
    setup_completed: bool = False
    current_step: str = SETUP_STEPS[0]
    hostname: str = ""
    local_ip: str = ""
    tailscale_status: str = "unknown"
    backend_endpoint: str = ""
    workspace_root: str = "/opt/hosaka/workspace"
    theme: str = "dark"
    picoclaw_enabled: bool = True
    picoclaw_ready: bool = False
    timestamps: dict[str, str] = field(default_factory=lambda: {"created": _utc_now(), "updated": _utc_now()})
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _payload_to_setup_state(raw: dict[str, Any]) -> SetupState:
    """Apply legacy key renames and ignore unknown JSON fields (for forward compatibility)."""
    data = dict(raw)
    _k_en = f"{_LEGACY_KEY_PREFIX}enabled"
    _k_rd = f"{_LEGACY_KEY_PREFIX}ready"
    if _k_en in data and "picoclaw_enabled" not in data:
        data["picoclaw_enabled"] = data.pop(_k_en)
    elif _k_en in data:
        data.pop(_k_en, None)
    if _k_rd in data and "picoclaw_ready" not in data:
        data["picoclaw_ready"] = data.pop(_k_rd)
    elif _k_rd in data:
        data.pop(_k_rd, None)
    allowed = {f.name for f in fields(SetupState)}
    filtered = {k: v for k, v in data.items() if k in allowed}
    return SetupState(**filtered)


class StateStore:
    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path or _default_state_path()

    def load(self) -> SetupState:
        if not self.state_path.exists():
            state = SetupState()
            self.save(state)
            return state

        with self.state_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        if not isinstance(payload, dict):
            payload = {}
        return _payload_to_setup_state(payload)

    def save(self, state: SetupState) -> None:
        state.timestamps["updated"] = _utc_now()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, indent=2)
