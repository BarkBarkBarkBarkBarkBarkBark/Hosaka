from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentResult:
    intent: str
    guidance: str


RULES: dict[str, IntentResult] = {
    "wifi": IntentResult("network_help", "Open Network Status and verify LAN or Wi-Fi connectivity."),
    "network": IntentResult("network_help", "Open Network Status and confirm local IP assignment."),
    "tailscale": IntentResult("tailscale_help", "Use the Tailscale setup step and authenticate the device."),
    "url": IntentResult("gui_url_help", "Use the LAN setup URL shown in the terminal to continue from another device."),
    "skip": IntentResult("skip_step", "You can skip optional steps and continue with defaults."),
    "preview": IntentResult("preview", "Run /preview in the main console after setup completes."),
}


def classify_intent(user_text: str) -> IntentResult:
    text = user_text.lower().strip()
    for keyword, result in RULES.items():
        if keyword in text:
            return result
    return IntentResult("general_help", "Use /help for commands, or continue through guided setup steps.")
