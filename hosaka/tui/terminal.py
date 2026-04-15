from __future__ import annotations

from hosaka.ops.updater import run_update
from hosaka.offline.assist import classify_intent
from hosaka.setup.orchestrator import SetupOrchestrator
from hosaka.setup.steps import SETUP_STEPS

STEP_PROMPTS: dict[str, str] = {
    "welcome_and_branding": "Press enter to continue.",
    "detect_network_status": "Press enter to refresh network status.",
    "choose_or_confirm_hostname": "Enter hostname [hosaka-field-terminal]: ",
    "configure_or_confirm_tailscale": "Enter tailscale mode [skip/connect]: ",
    "configure_backend_endpoint_optional": "Backend endpoint (optional): ",
    "configure_workspace_root": "Workspace root [/opt/hosaka/workspace]: ",
    "configure_theme": "Theme [dark/amber/blue]: ",
    "configure_openclaw": "OpenClaw setup [install/skip/path]: ",
    "confirm_setup_summary": "Type 'confirm' to finalize setup or 'back': ",
    "finalize_and_enter_main_console": "Setup complete. Press enter for main console.",
}


def _banner() -> None:
    print("\n==============================")
    print("HOSAKA FIELD TERMINAL")
    print("Initializing operator console...")
    print("==============================\n")


def _render_progress(orchestrator: SetupOrchestrator) -> None:
    summary = orchestrator.summary()
    print(
        f"Onboarding progress: step {summary['step_index']}/{summary['total_steps']} "
        f"({summary['progress_percent']}%)"
    )


def run_setup_flow(orchestrator: SetupOrchestrator, web_url: str) -> None:
    _banner()
    print(
        "Setup is incomplete. Hosaka can guide you here in the terminal, "
        "or continue in browser on your local network."
    )
    print(f"Setup GUI available at: {web_url}")

    while not orchestrator.state.setup_completed:
        orchestrator.update_runtime_network()
        _render_progress(orchestrator)
        current_step = orchestrator.state.current_step
        prompt = STEP_PROMPTS.get(current_step, "Press enter to continue.")
        try:
            print(f"\n{current_step}")
            answer = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("Input stream unavailable; setup can continue from LAN web UI.")
            break

        if answer.startswith("help"):
            intent = classify_intent(answer)
            print(f"{intent.intent}: {intent.guidance}")
            continue
        if answer.lower() == "update":
            print("Starting Hosaka update... this may restart services.")
            ok, output = run_update()
            if output:
                print(output)
            print("Update complete." if ok else "Update encountered an issue.")
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
        elif current_step == "configure_openclaw":
            if answer.lower() == "skip":
                orchestrator.set_field("openclaw_enabled", False)
                orchestrator.set_field("openclaw_ready", False)
            elif answer.lower() in {"install", "yes", "y", ""}:
                print("\nInstalling OpenClaw (Ollama + default model)...")
                print("This may take a few minutes on first run.\n")
                try:
                    from hosaka.llm.openclaw import run_install_script, doctor

                    ok, output = run_install_script()
                    if output:
                        print(output)
                    if ok:
                        info = doctor()
                        if info["api_reachable"] and info["default_model_available"]:
                            print("\nOpenClaw is ready!")
                            orchestrator.set_field("openclaw_enabled", True)
                            orchestrator.set_field("openclaw_path", "/opt/openclaw")
                            orchestrator.set_field("openclaw_ready", True)
                        else:
                            print("\nOpenClaw installed but not fully verified.")
                            print("You can run /openclaw doctor after setup to troubleshoot.")
                            orchestrator.set_field("openclaw_enabled", True)
                            orchestrator.set_field("openclaw_ready", False)
                    else:
                        print("\nOpenClaw install encountered an issue.")
                        print("You can retry with /openclaw install after setup.")
                        orchestrator.set_field("openclaw_enabled", True)
                        orchestrator.set_field("openclaw_ready", False)
                except Exception as exc:  # noqa: BLE001
                    print(f"\nInstall error: {exc}")
                    print("You can retry with /openclaw install after setup.")
                    orchestrator.set_field("openclaw_enabled", True)
                    orchestrator.set_field("openclaw_ready", False)
            else:
                orchestrator.set_field("openclaw_enabled", True)
                orchestrator.set_field("openclaw_path", answer)
                orchestrator.set_field("openclaw_ready", True)
        elif current_step == "confirm_setup_summary":
            if answer.lower() == "back":
                orchestrator.previous_step()
                continue
            if answer.lower() != "confirm":
                print("Type 'confirm' to complete setup.")
                continue
            orchestrator.finalize()
            break

        if current_step != SETUP_STEPS[-1]:
            orchestrator.next_step()

    print("Setup complete.")
