from __future__ import annotations

import shlex
import subprocess

from rich.console import Console

console = Console()


def run_main_console() -> None:
    console.print("[bold cyan]Hosaka Main Console[/bold cyan] - type /help")
    while True:
        try:
            raw = console.input("[bold blue]hosaka> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting Hosaka console.")
            break

        if not raw:
            continue
        if raw == "/help":
            console.print("/help /status /setup /theme /network /preview /exit")
        elif raw == "/status":
            console.print("System online. Setup complete.")
        elif raw == "/setup":
            console.print("Setup is managed by the onboarding orchestrator and web UI.")
        elif raw == "/theme":
            console.print("Theme command stub. Use setup flow or web GUI to change it.")
        elif raw == "/network":
            console.print("Use setup step or web network page to inspect network details.")
        elif raw == "/preview":
            console.print("Preview mode is reserved for future OpenClaw integration.")
        elif raw == "/exit":
            break
        else:
            try:
                proc = subprocess.run(shlex.split(raw), capture_output=True, text=True)
                if proc.stdout:
                    console.print(proc.stdout)
                if proc.stderr:
                    console.print(f"[red]{proc.stderr}[/red]")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Command failed:[/red] {exc}")
