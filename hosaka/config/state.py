from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hosaka.setup.steps import SETUP_STEPS

DEFAULT_STATE_PATH = Path("/var/lib/hosaka/state.json")


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
    timestamps: dict[str, str] = field(default_factory=lambda: {"created": _utc_now(), "updated": _utc_now()})
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StateStore:
    def __init__(self, state_path: Path = DEFAULT_STATE_PATH):
        self.state_path = state_path

    def load(self) -> SetupState:
        if not self.state_path.exists():
            state = SetupState()
            self.save(state)
            return state

        with self.state_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        state = SetupState(**payload)
        return state

    def save(self, state: SetupState) -> None:
        state.timestamps["updated"] = _utc_now()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, indent=2)
