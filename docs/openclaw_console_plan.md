# Hosaka + OpenClaw Console Plan

## Goal
Deliver a terminal-first appliance UX that feels nearly identical to OpenClaw's TUI while preserving Hosaka boot/onboarding and system integration.

## Phase 1: Stable handoff (immediate)
1. Keep Hosaka first-boot orchestrator for machine setup (network, hostname, theme, workspace).
2. Add explicit OpenClaw setup step in onboarding:
   - enable/disable OpenClaw
   - install path
   - readiness check
3. After setup completion, default main console command routes to OpenClaw launcher when `openclaw_ready=true`.

## Phase 2: Embedded OpenClaw shell
1. Create `hosaka/openclaw/adapter.py` with:
   - binary discovery (`openclaw`, `openclaw-tui`, module run fallback)
   - env wiring (workspace, endpoint, theme)
   - health check + version probe
2. Add `/openclaw` slash commands:
   - `/openclaw status`
   - `/openclaw setup`
   - `/openclaw doctor`
   - `/openclaw launch`
3. Fallback behavior:
   - if OpenClaw missing, present guided install instructions and keep Hosaka shell usable.

## Phase 3: UX convergence
1. Replace Hosaka temporary console renderer with OpenClaw-native event loop when available.
2. Keep Hosaka orchestration/status panel as a top frame or startup prelude.
3. Preserve appliance constraints:
   - no desktop requirement
   - resume state after reboot
   - LAN web setup remains optional side-channel

## Operational constraints
- Never block boot on OpenClaw install failures.
- Keep headless mode and console mode as separate services.
- Keep config/state in human-readable files under `/var/lib/hosaka`.

## Acceptance criteria
- First boot can complete entirely from tty keyboard.
- OpenClaw can be enabled/configured during onboarding.
- Post-setup console enters OpenClaw by default when ready.
- If OpenClaw is unavailable, Hosaka fallback console remains functional.
