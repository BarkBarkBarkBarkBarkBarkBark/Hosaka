"""Shared setup step catalog for terminal and web onboarding."""

from __future__ import annotations

SETUP_STEPS: list[str] = [
    "welcome_and_branding",
    "detect_network_status",
    "choose_or_confirm_hostname",
    "configure_or_confirm_tailscale",
    "configure_backend_endpoint_optional",
    "configure_workspace_root",
    "configure_theme",
    "confirm_setup_summary",
    "finalize_and_enter_main_console",
]
