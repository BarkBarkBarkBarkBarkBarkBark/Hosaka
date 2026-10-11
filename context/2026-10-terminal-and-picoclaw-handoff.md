# Hosaka terminal-first handoff

Updated: 2026-10-10.

This is a snapshot of the recent simplification and agent integration, not a
replacement for the [README](../README.md). Read this before changing the
terminal, GUI menu, games launcher, or console LLM routing.

## Product direction

Hosaka is now a minimal, terminal-first interface with a small menu. The Python
TUI is the canonical console. The graphical interface embeds that same console,
rather than maintaining a second desktop/chat implementation.

The LLM must run inside the **PicoClaw agent harness**, with native tools and
real operating-system context. A direct model completion is not an acceptable
substitute for console agent work.

## Recent changes

### Minimal TUI and menu

- The active React build is a terminal and a single **Menu** button, with
  Wi-Fi, Bluetooth, Games, and Flash controls.
- The terminal uses xterm and a local `/ws/tui` PTY bridge to launch
  `python -m hosaka tui`. Menu interactions do not restart the TUI or discard
  scrollback.
- Electron is a thin native host for this interface. The former desktop,
  panels, arcade, and webview bridges are retained under
  [archive/desktop-frontend](../archive/desktop-frontend), outside the active build.
- `/ws/tui` is restricted to loopback clients and origins, disabled in public
  mode, and can be disabled with `HOSAKA_TUI_ENABLED=0`.
- Linux Wi-Fi uses NetworkManager; Bluetooth uses BlueZ. Unsupported operations
  fail explicitly. macOS network/Bluetooth configuration uses system settings.
- GUI is the fresh graphical-install default; `hosaka display tui` selects
  plain TUI boot. Existing saved choices and Pi login settings must be preserved
  by updates.

Main entry points:
[TerminalGui.tsx](../frontend/src/TerminalGui.tsx),
[TuiTerminal.tsx](../frontend/src/components/TuiTerminal.tsx),
[terminal-gui.css](../frontend/src/styles/terminal-gui.css),
[tui_ws.py](../hosaka/web/tui_ws.py),
[kiosk/main.js](../kiosk/main.js), and
[scripts/hosaka](../scripts/hosaka).

### Console LLM chat

- `/llm` selects AI input mode; `/llm <message>`, plain text in that mode,
  `/ask`, and `/chat` all go through the console PicoClaw adapter.
- The previous console path preferred direct OpenAI-compatible chat and supplied
  Hosaka tool schemas. That bypassed PicoClaw even though the prompt said text
  went to it. This has been replaced with `picoclaw agent`.
- PicoClaw owns the native tool loop, workspace instructions, installed skills,
  and persistent conversation state. The console does not attach direct
  OpenAI tool schemas to this path.
- Each turn supplies Hosaka identity, hostname, actual OS/release/architecture,
  Python executable, and operator working directory. Exec commands should
  explicitly `cd` to that directory; native file tools may default to the
  PicoClaw workspace.
- `/select llm` still selects the underlying provider/model, now **inside**
  PicoClaw. `PICOCLAW_MODEL` explicitly overrides this with an existing
  PicoClaw alias.
- A private temporary config overlay retains the original workspace and tool
  policy. PicoClaw config v3 credentials go in the temporary `.security.yml`;
  older config versions use model-entry credentials. Temporary files are
  cleaned up after the request; the original configuration is not rewritten.
- Configuration lookup honors `PICOCLAW_CONFIG_PATH`, then
  `PICOCLAW_HOME/config.json`, then `~/.picoclaw/config.json`.
- The `hosaka:tui` alias is mapped to an explicit opaque PicoClaw session key.
  In PicoClaw 0.2.x, ordinary CLI aliases can otherwise collapse into the
  shared main session. `/clear` inside `/chat` starts a fresh native session;
  `/session` reports the active alias.
- Provider/config/binary errors are shown at the console. There is **no direct
  OpenAI or offline fallback** for console chat. Timeouts and Ctrl-C return to
  the prompt.
- Presentation streams words after the CLI completes; it is not live model-token
  streaming. The gateway is not required for this CLI path.
- Games use the existing PicoClaw games skill/native launcher. Book actions can
  call the existing Python dispatch helpers through native exec; those helper
  names are not registered PicoClaw tool names.

Main entry points:
[chat.py](../hosaka/llm/chat.py),
[picoclaw_adapter.py](../hosaka/llm/picoclaw_adapter.py),
[identity.py](../hosaka/identity.py),
[llm_cli.py](../hosaka/llm_cli.py), and
[PicoClaw backend notes](../docs/picoclaw_cli_backend.md).

Scope distinction: [router.py](../hosaka/llm/router.py) still supports direct
OpenAI/offline routing for other callers. Voice and legacy web endpoints are
separate surfaces; do not assume they were converted by this console change.
The ordinary PicoClaw config/default-model diagnostic may describe its saved
model, not the console's temporary model overlay.

### Native PlayStation launcher

- The terminal `/play`, shell `hosaka play`, Games menu, and agent launcher
  share the native PlayStation 1 implementation.
- List the installed catalog rather than guessing ROM directories. Fuzzy
  matches support convenience, but ambiguous titles return choices instead
  of guessing. `--json` provides machine-readable results.
- RetroPie core/config discovery and explicit ROM/core/RetroArch overrides
  support device-specific installations. Games, cores, and BIOS are not bundled.
- Stop only the verified emulator process launched by Hosaka; never interrupt
  an unrelated RetroArch process.
- Missing libraries, cores, graphical sessions, and failed launches must be
  reported as errors, not simulated success.

Main entry points:
[play.py](../hosaka/play.py),
[games.py](../hosaka/games.py),
[games_api.py](../hosaka/web/games_api.py), and
[hosaka-games skill](../skills/hosaka-games/SKILL.md).

### Flash overlay

- `/flash` displays **BUSTED** by default. `/flash your text` accepts up to
  80 characters and displays uppercase text.
- The GUI overlay alternates blue/red every 250 ms, with black text and a white
  outline. The text remains steady; no return hint is displayed.
- Tap anywhere, Escape, Enter, or Space dismisses it without restarting the
  terminal. The menu text field and **Show flash** use the same overlay.
- Reduced-motion mode uses static blue. Plain terminals report that the GUI
  is required. Keep the photosensitivity warning in user-facing documentation.

Implementation is shared between
[TerminalGui.tsx](../frontend/src/TerminalGui.tsx),
[TuiTerminal.tsx](../frontend/src/components/TuiTerminal.tsx), and
[main_console.py](../hosaka/main_console.py).

## Verified Mac state on 2026-10-10

- Installed PicoClaw: **0.2.8**, git `6e1fab80`.
- Console selection: **OpenAI gpt-4.1**, executed inside PicoClaw.
- The saved PicoClaw default was Ollama `qwen2.5:0.5b` at
  `http://100.78.174.79:11434/v1`; that endpoint was unreachable from the Mac.
  No local Ollama listener was available either. Do not treat this as a
  PicoClaw installation failure.
- Live native exec returned `Darwin` and the repository's actual directory.
  A persisted isolated session log confirmed an `exec` tool call and its real
  output, rather than relying only on the model's claim.
- The browser terminal was reloaded, then `/llm` successfully performed the
  same read-only OS/directory inspection.
- Chat and voice-bridge regression suites passed: **115 tests**.
- The combined chat, voice bridge, terminal GUI, native play, Games menu, and
  main-console suites passed before publication: **216 tests**.
- The minimal frontend passed `npm run build:check` (TypeScript and Vite).
- Existing TUI processes need restart/reconnect to import changed Python code.

These are machine-specific observations, not portable defaults. Never copy API
keys, private config files, session transcripts, ROMs, or BIOS into the repo.

## Validation and development

From the repository root, using the existing environment:

```bash
PYTHONPATH=.:packages/social_cognition/src .hosakavenv/bin/python -m pytest -q \
  tests/test_hosaka_chat.py tests/test_voice_social_bridge.py \
  tests/test_terminal_gui.py tests/test_play.py tests/test_games_menu.py \
  tests/test_hosaka_main_console.py
cd frontend
npm run build:check
```

The extra Python path exposes the in-repo social-cognition package for the
voice bridge tests. Use the project's actual interpreter/environment on other
machines; `.hosakavenv` is not a universal prerequisite.

For a live read-only check:

```text
/llm Use exec to run uname -s and pwd in the console working directory. Report the actual output only. Do not change files.
```

Useful historical commits:

- `c490a697`: terminal GUI simplification, menu/flash, boot/update behavior,
  and initial PSX integration.
- `662fef59`: GUI autostart without resetting Pi login on updates.
- `bc240503`: native PlayStation catalog and RetroArch launcher.

## Preserve in future work

Keep the active UI small, the Python console canonical, the agent inside
PicoClaw, OS inspection grounded in tool results, and failures explicit. Do not
restore archived desktop complexity, bypass the harness to make a failed chat
look successful, widen native tool permissions, or reset user boot/provider
choices as a side effect of updating.
