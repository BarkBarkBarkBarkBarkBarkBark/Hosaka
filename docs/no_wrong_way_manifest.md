# NO WRONG WAY // HOSAKA FIELD TERMINAL MANIFEST

> You can't really break this experience by experimenting.
> If a command fails, Hosaka should redirect, not punish.

## What this system is
Hosaka Field Terminal is a console-first appliance shell for cyberdeck operation.
It is designed to feel like a dedicated product, not a generic Linux desktop.

### Core pillars
1. Terminal-first operator identity.
2. Guided onboarding with resumable state.
3. Local-network setup path for cross-device configuration.
4. Offline-resilient behavior with deterministic fallback help.
5. "No Wrong Way" interaction model.

## How to navigate
At the `hosaka>` prompt, you can:
- run slash commands (`/help`, `/status`, `/manifest`, etc.)
- run shell commands (`ls`, `ip a`, `uptime`, etc.)
- read files with `read <file>`

Examples:
- `read manifest`
- `read README.md`
- `read /var/lib/hosaka/state.json`
- `/status`
- `/network`

## Recommended first actions
1. `read /var/lib/hosaka/state.json`
2. `/status`
3. `/network`
4. `read README.md`

## Picoclaw agent
Picoclaw is the brains of operation — a lightweight local agent binary.
Everything typed at the `hosaka>` prompt goes straight to Picoclaw.

Flow:
- Picoclaw must be installed and onboarded before first boot (`picoclaw onboard`)
- The console routes all free-form input through the Picoclaw subprocess adapter
- `/picoclaw status` and `/picoclaw doctor` for diagnostics

## Failure behavior
When a command fails or is unknown, the system should:
1. explain what happened
2. suggest next best commands
3. keep user in control

No dead ends. No wrong way.

## Reader mode
Use `read <file>` to open any text file.
Reader controls:
- `Enter` = next page
- `q` = exit reader early

## Operator motto
**NO WRONG WAY**
