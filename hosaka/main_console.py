from __future__ import annotations

import shlex
import subprocess


def run_main_console() -> None:
    print("Hosaka Main Console - type /help")
    while True:
        try:
            raw = input("hosaka> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting Hosaka console.")
            break

        if not raw:
            continue
        if raw == "/help":
            print("/help /status /setup /theme /network /preview /exit")
        elif raw == "/status":
            print("System online. Setup complete.")
        elif raw == "/setup":
            print("Setup is managed by the onboarding orchestrator and web UI.")
        elif raw == "/theme":
            print("Theme command stub. Use setup flow or web GUI to change it.")
        elif raw == "/network":
            print("Use setup step or web network page to inspect network details.")
        elif raw == "/preview":
            print("Preview mode is reserved for future OpenClaw integration.")
        elif raw == "/exit":
            break
        else:
            try:
                proc = subprocess.run(shlex.split(raw), capture_output=True, text=True)
                if proc.stdout:
                    print(proc.stdout)
                if proc.stderr:
                    print(proc.stderr)
            except Exception as exc:  # noqa: BLE001
                print(f"Command failed: {exc}")
