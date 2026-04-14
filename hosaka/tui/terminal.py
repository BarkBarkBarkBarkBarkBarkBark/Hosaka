from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn

from hosaka.offline.assist import classify_intent
from hosaka.setup.orchestrator import SetupOrchestrator
from hosaka.setup.steps import SETUP_STEPS

console = Console()

STEP_PROMPTS: dict[str, str] = {
    "welcome_and_branding": "Press enter to continue.",
    "detect_network_status": "Press enter to refresh network status.",
    "choose_or_confirm_hostname": "Enter hostname [hosaka-field-terminal]: ",
    "configure_or_confirm_tailscale": "Enter tailscale mode [skip/connect]: ",
    "configure_backend_endpoint_optional": "Backend endpoint (optional): ",
    "configure_workspace_root": "Workspace root [/opt/hosaka/workspace]: ",
    "configure_theme": "Theme [dark/amber/blue]: ",
    "confirm_setup_summary": "Type 'confirm' to finalize setup or 'back': ",
    "finalize_and_enter_main_console": "Setup complete. Press enter for main console.",
}


def _banner() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]HOSAKA FIELD TERMINAL[/bold cyan]\nInitializing operator console...",
            border_style="cyan",
        )
    )


def _render_progress(orchestrator: SetupOrchestrator) -> None:
    summary = orchestrator.summary()
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=36),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("{task.percentage:>3.0f}%"),
        transient=True,
    ) as progress:
        progress.add_task("Onboarding", total=summary["total_steps"], completed=summary["step_index"])


def run_setup_flow(orchestrator: SetupOrchestrator, web_url: str) -> None:
    _banner()
    console.print(
        "Setup is incomplete. Hosaka can guide you here in the terminal, "
        "or continue in browser on your local network."
    )
    console.print(f"[bold green]Setup GUI available at: {web_url}[/bold green]")

    while not orchestrator.state.setup_completed:
        orchestrator.update_runtime_network()
        _render_progress(orchestrator)
        current_step = orchestrator.state.current_step
        prompt = STEP_PROMPTS[current_step]
        answer = console.input(f"\n[bold]{current_step}[/bold]\n{prompt}").strip()

        if answer.startswith("help"):
            intent = classify_intent(answer)
            console.print(f"[cyan]{intent.intent}:[/] {intent.guidance}")
            continue

        if current_step == "choose_or_confirm_hostname":
            orchestrator.set_field("hostname", answer or "hosaka-field-terminal")
        elif current_step == "configure_or_confirm_tailscale":
            if answer:
                orchestrator.set_field("tailscale_status", answer)
        elif current_step == "configure_backend_endpoint_optional":
            orchestrator.set_field("backend_endpoint", answer)
        elif current_step == "configure_workspace_root":
            orchestrator.set_field("workspace_root", answer or "/opt/hosaka/workspace")
        elif current_step == "configure_theme":
            orchestrator.set_field("theme", answer or "dark")
        elif current_step == "confirm_setup_summary":
            if answer.lower() == "back":
                orchestrator.previous_step()
                continue
            if answer.lower() != "confirm":
                console.print("Type 'confirm' to complete setup.")
                continue
            orchestrator.finalize()
            break

        if current_step != SETUP_STEPS[-1]:
            orchestrator.next_step()

    console.print("[bold green]Setup complete.[/bold green]")
