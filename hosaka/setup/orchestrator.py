from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from hosaka.config.state import SetupState, StateStore
from hosaka.network.discovery import detect_local_ip, detect_tailscale_status
from hosaka.setup.steps import SETUP_STEPS


class SetupOrchestrator:
    def __init__(self, state_store: StateStore):
        self.state_store = state_store
        self.state = self.state_store.load()

    @property
    def total_steps(self) -> int:
        return len(SETUP_STEPS)

    @property
    def step_index(self) -> int:
        if self.state.current_step not in SETUP_STEPS:
            self.state.current_step = SETUP_STEPS[0]
            self.state.last_error = "Invalid setup step in state; reset to first step."
            self.persist()
        return SETUP_STEPS.index(self.state.current_step)

    def progress_percent(self) -> int:
        return int(((self.step_index + 1) / self.total_steps) * 100)

    def update_runtime_network(self) -> None:
        self.state.local_ip = detect_local_ip()
        self.state.tailscale_status = detect_tailscale_status()
        self.persist()

    def set_field(self, key: str, value: str) -> None:
        if not hasattr(self.state, key):
            raise KeyError(f"Unsupported field: {key}")
        normalized = value.strip() if isinstance(value, str) else value
        defaults = {
            "hostname": "hosaka-field-terminal",
            "workspace_root": "/opt/hosaka/workspace",
            "theme": "dark",
            "tailscale_status": "unknown",
            "picoclaw_ready": False,
        }
        if key in defaults and not normalized:
            normalized = defaults[key]
        setattr(self.state, key, normalized)
        self.persist()

    def next_step(self) -> str:
        idx = self.step_index
        if idx < self.total_steps - 1:
            self.state.current_step = SETUP_STEPS[idx + 1]
        self.persist()
        return self.state.current_step

    def previous_step(self) -> str:
        idx = self.step_index
        if idx > 0:
            self.state.current_step = SETUP_STEPS[idx - 1]
        self.persist()
        return self.state.current_step

    def finalize(self) -> None:
        self.state.setup_completed = True
        self.state.current_step = SETUP_STEPS[-1]
        self.persist()

    def reset(self) -> None:
        self.state = SetupState()
        self.persist()

    def persist(self) -> None:
        self.state_store.save(self.state)

    def summary(self) -> dict:
        summary = asdict(self.state)
        summary["progress_percent"] = self.progress_percent()
        summary["step_index"] = self.step_index + 1
        summary["total_steps"] = self.total_steps
        return summary


def build_default_orchestrator(state_path: Path | None = None) -> SetupOrchestrator:
    store = StateStore(state_path=state_path) if state_path else StateStore()
    return SetupOrchestrator(state_store=store)
