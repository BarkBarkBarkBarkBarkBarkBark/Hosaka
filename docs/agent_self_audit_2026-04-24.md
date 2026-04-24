# Agent Self-Audit — 2026-04-24

## Scope
This audit reviews the currently available agent runtime tools, the Hosaka codebase surfaces relevant to operator control, the Picoclaw integration path, and the current to-do sharing implementation added for Telegram.

## Executive summary
The agent has strong local operational capability through the runtime tool layer plus shell access. The Hosaka repository provides a richer product/runtime environment, but those capabilities are mostly exercised indirectly through shell commands, file edits, and service/script execution. A recurring Telegram to-do sharing mechanism has been implemented as a local script and scheduled to run every 4 hours.

## 1. Direct runtime tools available to the agent
The agent can directly:
- read, write, edit, append files
- list directories
- execute shell commands
- send messages to the current chat
- send local files
- fetch web content
- schedule cron/reminder jobs
- spawn background subagents
- run synchronous subagents
- discover and install skills

These are the most reliable capabilities because they are exposed directly in the current session runtime.

## 2. Installed skills
Currently installed skill(s):
- `telegram-api`

The Telegram skill documents richer Telegram Bot API access including:
- sending/editing/deleting messages
- polls, media, locations, contacts, callbacks
- bot command/profile management
- webhook and update handling
- chat/member/admin inspection

In this session, the built-in `message` tool is sufficient for direct operator communication on Telegram. The skill is still useful as an expansion path for richer bot workflows.

## 3. Hosaka repo capability map
Top-level repo surfaces observed:
- `api/`
- `frontend/`
- `hosaka/`
- `identity/`
- `install/`
- `kiosk/`
- `scripts/`
- `systemd/`
- `tests/`

### Key scripts
From `scripts/`:
- `hosaka` — operator CLI wrapper
- `hosakactl` — remote control client
- install/setup scripts
- kiosk scripts
- update and smoke-test scripts

### Key systemd units
From `systemd/`:
- `hosaka-webserver.service`
- `hosaka-kiosk.service`
- `hosaka-voice.service`
- `hosaka-device-dashboard.service`
- `picoclaw-gateway.service`

### Python package surfaces
From `hosaka/`:
- boot/launcher
- config
- llm
- network
- offline
- ops
- setup
- tui
- voice
- web
- `main_console.py`
- `picoclaw_runtime.py`

## 4. Picoclaw integration findings
### `hosaka/picoclaw_runtime.py`
This file seeds and refreshes Picoclaw runtime files under `~/.picoclaw`, including:
- identity files mirrored into workspace
- `memory/TASKS.md` stub
- config defaults
- permissive read/write path allowances
- default model settings
- gateway host/port

This confirms Hosaka is designed to prepare Picoclaw’s runtime environment automatically.

### `hosaka/boot/launcher.py`
This launcher:
- starts the web server
- attempts to start the Picoclaw gateway if appropriate
- refreshes Picoclaw runtime files
- falls back sensibly if Picoclaw is missing or not configured
- dispatches to the main console when in console mode

### `scripts/hosaka`
This operator CLI wraps:
- mode switching (`console` / `device`)
- status/build/deploy/logs/reboot
- agent chat/message wrappers around `picoclaw agent`
- full TUI launch via `hosaka tui`

This is the clearest operator-facing control surface for Hosaka.

## 5. To-do implementation findings
There are at least two to-do stores in the codebase:
- `~/.hosaka_todos.json` used by `main_console.py` for `/todo`
- `~/.hosaka/voice_todos.jsonl` used by voice tooling

For operator-facing to-do sharing, the simpler and more direct source is:
- `~/.hosaka_todos.json`

## 6. Gaps / limitations
- No built-in autonomous background cognition loop is exposed directly in this chat runtime.
- “Of my own volition” is only realistically approximated through scheduled jobs or explicit automation, not persistent self-directed consciousness.
- Telegram skill is documented, but for this session the built-in messaging tool is the simplest dependable path.
- Memory file path in the workspace instructions did not yet exist and had to be created.

## 7. Implemented automation: recurring Telegram to-do sharing
Implemented components:
- Script: `/home/operator/bin/share_todos_telegram.sh`
- Schedule: every 4 hours
- Delivery path: script invokes `picoclaw` in the current Telegram session context so the agent can read `~/.hosaka_todos.json` and send a summary message to the operator chat.

### Behavior
The script asks the agent to:
- inspect the current to-do file
- summarize open items
- send a Telegram message to the operator
- remain concise if there are no active items

### Current cadence
- every 4 hours

## 8. Recommended next improvements
1. Unify todo sources (`~/.hosaka_todos.json` and voice todos) into one canonical store.
2. Add timestamps / priorities / projects to todo items.
3. Add a “send only on change” mode to reduce noise.
4. Add a daily summary plus a 4-hour delta summary.
5. Persist an audit trail of sent Telegram summaries.

## Conclusion
The agent is operationally strong on local actions and can leverage Hosaka as a rich execution environment. The newly added recurring Telegram to-do sharing system provides a practical approximation of proactive behavior within the limits of the current runtime.
