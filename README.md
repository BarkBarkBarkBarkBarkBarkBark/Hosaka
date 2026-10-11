# Hosaka Field Terminal

```
  ██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗
  ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗
  ███████║██║   ██║███████╗███████║█████╔╝ ███████║
  ██╔══██║██║   ██║╚════██║██╔══██║██╔═██╗ ██╔══██║
  ██║  ██║╚██████╔╝███████║██║  ██║██║  ██╗██║  ██║
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

      * \ _ /
       @( )@          A console-first AI field terminal.
      */\|/\*         Signal steady. No wrong way.
     (@)|  /\
      \ | /(_)
       _|_/_
      [_____]
```

An AI-powered appliance shell for cyberdecks and Raspberry Pis.
Type anything — it goes straight to the agent.
Use it enough and the plant blooms. Neglect it and it wilts.

There is no wrong way.

---

## Install in one line

**mac / linux**

```bash
curl -fsSL https://install.hosaka.xyz | sh
```

**windows (PowerShell)**

```powershell
iwr https://install.hosaka.xyz/windows | iex
```

Then:

```bash
hosaka up          # start the local node (web UI on http://127.0.0.1:8421)
hosaka tui         # drop into the console TUI
hosaka open        # open the web UI in your browser
hosaka link HOST   # route this client at a remote hosaka on your tailnet
hosaka help        # see everything
```

Requires [Docker](https://www.docker.com/products/docker-desktop).
See [`install/`](./install/) for the installer internals.

---

## Boot Dev Container

```bash
cd /Users/marco/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka
hosaka down
./docker/dev.sh up
```

## Boot Docker Instance

```bash
./docker/dev.sh up
```

## Terminal-first GUI and boot choice

The Python TUI is the canonical console. The default graphical Hosaka now
hosts that exact `python -m hosaka tui` process in a resizable terminal, with
one **Menu** button for **Wi-Fi**, **Bluetooth**, **Games**, and **Flash**. Opening or
closing the menu does not restart the TUI or discard its scrollback.

In this GUI, `/flash` fills the window with alternating blue/red colors and
**BUSTED** in black, white-outlined text. `/flash your text` replaces **BUSTED**
with your custom text (up to 80 characters, displayed uppercase). No return hint
is shown. Tap anywhere or press Escape, Enter, or Space to dismiss without
restarting the terminal. The background switches every 250 ms (two complete
blue/red cycles per second) while the text stays steady. Reduced-motion
preferences use a static blue background. Flashing colors may affect
photosensitive viewers. Plain terminal sessions explain that the GUI is required.

```bash
hosaka              # terminal + menu in a graphical session; plain TUI over SSH
hosaka tui          # canonical terminal, no Chromium
hosaka gui          # Electron terminal + menu
hosaka display tui  # opt into a plain TUI at next graphical login
hosaka display gui  # terminal + menu at next graphical login (fresh-deck default)
hosaka display show # saved boot display choice
```

For fresh Linux appliances, use `HOSAKA_DISPLAY_MODE=gui` (default) or
`HOSAKA_DISPLAY_MODE=tui` with the installer. The TUI path does not install or
autostart Electron; selecting GUI during installation installs its runtime.
Existing saved display choices are preserved when reinstalling unless explicitly
overridden. A graphical login/session is still required for these display modes.

The GUI's `/ws/tui` endpoint only accepts loopback clients and loopback browser
origins, and is disabled in public mode (`HOSAKA_PUBLIC_MODE=1`) or with
`HOSAKA_TUI_ENABLED=0`. The old web desktop is retired, including `/?desktop=1`;
remote/public hosts cannot expose the native terminal. Use the local screen or
`hosaka tui` over SSH.

Wi-Fi uses the existing NetworkManager API on Linux. Bluetooth uses BlueZ to
scan, pair, trust, and connect devices without a PIN; PIN/passkey pairing and
macOS network/Bluetooth changes currently use system settings. Unsupported
hosts show an explicit error rather than simulated devices.

**Games** lists only the installed PlayStation 1 catalog using
Hosaka's native launcher, launches an exact title through RetroArch,
and provides **Stop game**. It does not offer Pong/Snake or guess ROM folders.
The device-specific `~/bin/play` and `rp-run` scripts are no longer required.
Missing libraries, cores, and failed
launches are shown as errors, never as a fake successful launch. RetroArch
can take focus over Hosaka; closing it reveals the terminal window again.
Super+H also brings Hosaka back.

**Flash** has an optional text field (blank means **BUSTED**) and **Show flash**.
It uses the same overlay as `/flash` without restarting or typing into the TUI.

The Linux installer installs RetroArch by default (`INSTALL_RETROARCH=0` to
skip). It does not bundle games, emulator cores, or BIOS files.

### Native PlayStation launcher

In the Hosaka terminal:

```text
/play                         list the installed PS1 library
/play spyro                   fuzzy-match and launch a title
/play Crash Bandicoot (USA)    use an exact title
/play stop                    stop the emulator launched by Hosaka
```

In a normal shell, use `hosaka play` with the same arguments, or
`python -m hosaka.play`. Add `--json` for a machine-readable result. Ambiguous
names return matching titles rather than guessing or waiting for keyboard
input. The terminal, Games menu, and agent all use this implementation.

On RetroPie, Hosaka automatically uses `~/RetroPie/roms/psx` and the PS1
command in `/opt/retropie/configs/psx/emulators.cfg`, including the existing
core and RetroArch configuration. Commands are parsed as arguments, not
executed through a shell. On other Linux/macOS installations, configure:

```bash
export HOSAKA_PSX_ROMS="$HOME/Games/psx"
export HOSAKA_PSX_CORE="/path/to/pcsx_rearmed_libretro.so"
export HOSAKA_RETROARCH="/path/to/retroarch"          # optional if on PATH
export HOSAKA_RETROARCH_CONFIG="/path/to/config.cfg" # optional
hosaka play list psx
```

Use the appropriate installed libretro core for your OS/architecture. A
graphical session, compatible RetroArch/core, and any BIOS required by that
core must already exist. ROMs/BIOS are local files; Hosaka does not download
or bundle them. The native launcher currently supports PS1 only.

Hosaka records its emulator PID and process identity, stops only that
verified process, and refuses to interrupt a RetroArch game launched outside
Hosaka. Logs and launch state live under `~/.local/state/hosaka/`.
`HOSAKA_PLAY=/path/to/custom-launcher` remains an explicit compatibility
override for a launcher supporting the existing `--json` protocol.
The old standalone `play` command is left untouched; use `hosaka play` or
`/play` for the ecosystem-owned launcher.

## Electron host

The **Electron kiosk host** at [`kiosk/`](./kiosk/) wraps the terminal GUI
in a native Chromium window. The retired desktop, arcade, app-store/webview
bridges, browser voice UI, and associated frontend code are preserved under
[`archive/desktop-frontend/`](./archive/desktop-frontend/) outside the active build.
Shared Python terminal, LLM, voice, and application-launch tools are retained.

```bash
cd kiosk
npm install      # first time only
npm run dev      # vite + electron together, HMR, windowed
```

On the edge device, `hosaka-kiosk.service` runs the same Electron host
fullscreen at boot, pointed at the local FastAPI on `127.0.0.1:8421`.
See [`kiosk/README.md`](./kiosk/README.md) for details.

### Local repo dev without Docker

If you're working from this checkout, you can now start the app locally
without Docker and without waiting for any hosted deploy loop:

```bash
./scripts/install-local-cli.sh
```

That installs a repo-local `hosaka` command into `~/.local/bin` by default,
which avoids old or relocated virtualenv path issues. If needed, it can still
fall back to an active environment `bin/` directory.

If you want to replace `/usr/local/bin/hosaka` system-wide instead:

```bash
./scripts/install-local-cli.sh --global
```

If an older `hosaka` is already on your machine, run `hash -r` after install,
or open a fresh shell, so your shell stops caching the old command path.

```bash
hosaka dev
```

That starts the canonical local Hosaka host: Vite plus the Electron kiosk
wrapper on `http://localhost:5173`.

If that port is already busy, plain `hosaka dev` now just reuses the existing
session. If you want a clean restart instead:

```bash
hosaka dev -fresh
```

- `hosaka dev` reuses a session only when both backend and frontend answer HTTP.
  An occupied port on a suspended or stalled process is reported explicitly;
  use `hosaka dev -fresh` to restart the pair.
- `hosaka gui` opens the terminal-first GUI, not the legacy desktop test route.
- `hosaka dev -fresh` stops the current listener on that port, then relaunches Hosaka.

If you ever want to cleanly stop the local dev host and window without changing
ports:

```bash
hosaka down
```

If you specifically want browser-only fallback mode:

```bash
hosaka dev --web
```

Use that only for quick UI debugging when the kiosk wrapper is getting in the
way. Electron-first is now the default dev path.

### App framework direction

Hosaka defaults to the terminal-plus-menu GUI on new cyberdecks. The desktop
frontend is archived, not an opt-in route. Host applications remain available
through `hosaka launch` and the Linux desktop rather than a second Hosaka shell.
Older app-framework documents describe the retired UI, not the current menu.

---

## Documentation

Full reference site (auto-built from this commit on every push to `main`):

**→ https://barkbarkbarkbarkbarkbarkbark.github.io/Hosaka/**

What lives there:

- **API reference** — the live `/api/v1/*` OpenAPI spec, rendered via Swagger UI.
- **`hosakactl`** — the single-file laptop client that talks to that API.
- **Modes** — what `console` / `device` actually do under the hood.
- **Wifi setup** — every way to add a network (kiosk button, `/device` page,
  `hosakactl wifi add`, TTY hotkey).
- **Claims audit** — what the codebase actually does vs. what older docs claim.

Build it locally:

```bash
pip install -r docs/requirements.txt
python scripts/dump_openapi.py docs/openapi.json
mkdocs serve              # http://127.0.0.1:8000
```

Implementation notes for the next phase live here too:

- [`docs/local_bridge_gateway.md`](./docs/local_bridge_gateway.md) — local bridge,
  managed Fly gateway, required keys, and Docker initialization checks.
- [`docs/doctor.md`](./docs/doctor.md) — the new `hosaka doctor` diagnostic
  surface, designed to evolve cleanly into an MCP-friendly health/report tool.
- [`docs/http_surface.md`](./docs/http_surface.md) — the allowlisted outbound
  HTTP GET/POST surface that ships with the Hosaka console.

## Agent Contract

Hosaka now ships its agent behavior as repo-owned canon instead of relying on
hand-edited files in `~/.picoclaw`.

Canonical source files:

- `identity/AGENT.md` - Hosaka's identity, communication style, task/skill role
- `identity/SOUL.md` - deeper lore / tone
- `identity/USER.md` - operator-facing defaults
- `manager/charter.yaml` - task policy, scoring, prioritization, daily loop
- `manager/bootstrap_tasks.md` - runtime task template
- `skills/index.yaml` - built-in Hosaka skill catalog
- `skills/hosaka-task-manager/SKILL.md` - task-system workflow
- `skills/hosaka-skill-lifecycle/SKILL.md` - skill search / install / authoring workflow

These are materialized into the PicoClaw runtime with:

```bash
python scripts/bootstrap_picoclaw_runtime.py --home "$HOME"
```

That generator writes:

- `~/.picoclaw/workspace/AGENT.md`
- `~/.picoclaw/workspace/SOUL.md`
- `~/.picoclaw/workspace/USER.md`
- `~/.picoclaw/workspace/manager/charter.yaml`
- `~/.picoclaw/workspace/memory/TASKS.md`
- `~/.picoclaw/workspace/skills/catalog/index.yaml`
- `~/.picoclaw/workspace/skills/hosaka-task-manager/SKILL.md`
- `~/.picoclaw/workspace/skills/hosaka-skill-lifecycle/SKILL.md`

Because the generator runs from repo-owned sources, Hosaka's identity,
task-management role, and built-in skill behavior survive appliance installs,
Docker image builds, and future deployments.

## Remote configuration from your laptop

After `install_hosaka_lean.sh` runs on the Pi it generates
`/etc/hosaka/api-token` (group-readable by the operator). Drop the
single-file client on your laptop:

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl && chmod +x /usr/local/bin/hosakactl

hosakactl link http://hosaka.local:8421       # prompts for token
hosakactl status                              # full snapshot
hosakactl mode device --persist -y            # SSH-friendly
hosakactl wifi add "Cafe Free WiFi"           # prompts for password
hosakactl test                                # smoke-test all endpoints
```

Stdlib only, no install. Works on Mac, Linux, and the Pi itself.

---

## Install

### 1. Install Picoclaw

```bash
cd /tmp
curl -L https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz \
  -o picoclaw.tar.gz
tar -xzf picoclaw.tar.gz && chmod +x picoclaw && sudo mv picoclaw /usr/local/bin/
picoclaw onboard
```

Then generate Hosaka's runtime contract into the PicoClaw workspace:

```bash
python scripts/bootstrap_picoclaw_runtime.py --home "$HOME"
```

### 2. Configure your LLM backend

Hosted Docker users (the common case) can skip manual config — Hosaka
prompts you automatically:

- **Inline shell prompt**: type anything in the terminal on first launch
  and the shell asks:
  ```
    no llm backend configured.
    configure one now? [Y/n]
  ```
  Walks you through provider, model, base URL (for local/Ollama), and
  API key (input is masked — never logged or sent as chat context).

- **Settings drawer**: click the ⚙ gear icon anytime → **LLM Backend**
  section. Supports OpenAI and any OpenAI-compatible endpoint (Ollama,
  LM Studio, etc.). Your API key is stored on the server in
  `/var/lib/hosaka/llm.json` and applied to the running process
  immediately — no restart required.

- **Environment variables** (appliance / advanced):
  ```bash
  export OPENAI_API_KEY=ollama
  export OPENAI_MODEL=qwen2.5:0.5b
  export OPENAI_BASE_URL=http://100.78.174.79:11434/v1
  ```

Any of these approaches works — mix and match.

For the Jetson-hosted Ollama path, smoke test the OpenAI-compatible API with:

```bash
curl --silent --show-error --max-time 10 http://100.78.174.79:11434/v1/models
curl --silent --show-error --max-time 30 http://100.78.174.79:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:0.5b","messages":[{"role":"user","content":"Reply with exactly: Jetson chat API works."}],"stream":false}'
```

> **Privacy**: the API key is stored on-device only. It is never sent
> to Hosaka's servers, never logged, and never included in chat context.

### 3. Clone and run

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
python -m venv .hosakavenv && source .hosakavenv/bin/activate
pip install -r requirements-hosaka.txt
python scripts/bootstrap_picoclaw_runtime.py --home "$HOME"
picoclaw gateway &
python -m hosaka
```

### 4. Appliance install (Raspberry Pi)

```bash
./scripts/setup_hosaka.sh
```

One command. Installs everything, runs `picoclaw onboard` if needed,
regenerates Hosaka's PicoClaw runtime files from repo-owned canon, enables
systemd services, and starts onboarding.

After install you'll have a `hosaka` command on the path — see "Operator CLI"
below for the build/kiosk mode toggle and one-shot deploys.

---

## Operator CLI

Once installed, the Pi exposes a `hosaka` command for day-to-day operations:

```bash
hosaka status                  # what's running, RAM/CPU snapshot, current mode
hosaka mode build [--persist]  # stop kiosk, free RAM/CPU for SSH workflows
hosaka mode kiosk [--persist]  # restore the touchscreen kiosk
hosaka build [--check]         # cd frontend && npm run build (--check runs tsc gate)
hosaka deploy [--check]        # build + rsync into /opt + restart webserver
hosaka update                 # pull GitHub + build + deploy in an independent Pi job
hosaka update logs            # follow progress (Ctrl-C only stops the log viewer)
hosaka update status          # last job result: UPDATE COMPLETE / UPDATE FAILED
hosaka logs [web|pico|<unit>]  # tail journalctl
hosaka reboot                  # safe sync + reboot
hosaka issue <verb>            # GitHub-backed dev tracking (see docs/issue-tracking.md)
```

### Why "build mode"?

The Pi 3B has **906 MiB RAM**. With Chromium kiosk + uvicorn + picoclaw +
the Cursor remote server all loaded, there is no headroom left for
`npm run build` and the OOM killer takes the build (or, worse, the SSH
session). `hosaka mode build` shuts down the kiosk and the picoclaw gateway
to free ~700 MiB before you build. `--persist` writes a marker to
`/boot/firmware/hosaka-build-mode` so the Pi stays in build mode across
reboots until you flip back with `hosaka mode kiosk --persist`.

### One-command Raspberry Pi updates

```bash
hosaka update
```

On a systemd Pi this starts a separate root-owned, journaled job, so closing
the terminal or losing SSH does not cancel deployment. Git and npm run as the
operator, not root. The job pauses the kiosk/web/agent/voice services, keeps the
desktop and SSH up, limits build memory to 650 MB, pulls the current branch
from `origin` with `--ff-only`, executes the freshly pulled deployment code,
rebuilds assets, refreshes Python requirements when changed, and updates the
installed CLI/kiosk launchers and graphical autostart files. It restores
services and the screen on success or failure without restarting the graphical
login or tty1, verifies web-server health,
and checks that the served frontend build stamp matches the deployed commit.
Failures appear in `hosaka update status`; no successful deployment is claimed
after a failed build. A sudo password may be requested when starting the job.

The first deployment migrates saved graphical boot from the old plain-TUI
default to **terminal + menu**. Subsequent deployments preserve explicit
`hosaka display tui|gui` choices. An intentionally selected device/build mode
is preserved; use `hosaka mode console` to return to the graphical screen.
The `/update` TUI command uses this same workflow and reports that a job was
started, not that a background deployment already finished.

**One-time bootstrap from an older installed CLI:**

```bash
cd ~/Hosaka
git pull --ff-only origin main
bash scripts/hosaka update
```

After that, the installed `hosaka update` is sufficient. The bootstrap is
necessary because the older CLI continues executing its old deployment
functions after pulling newer scripts. The checkout must be clean, including
untracked files; updates stop rather than overwriting local work. Only changes
committed and pushed to GitHub can reach the Pi.

`hosaka update local` deploys the working tree without pulling. `--check`
adds the TypeScript gate; `--branch BRANCH` selects another branch.
`--foreground` is available for a stable local shell, but does not provide
disconnect protection or the worker's automatic pause/restore sequence.

### Why is the build so much lighter now?

The terminal-only build transforms **44 modules instead of 237** and ships
roughly **463 KB** of JS/CSS before compression. The 3.7 MB Automerge bundle,
arcade, old panels, webview/app-store bridges, and browser audio dependencies
are no longer part of the build. This is an asset-size measurement, not a
claim about peak build RAM on every Pi.

`npm run build` remains Vite-only; `npm run build:check` adds the TypeScript
gate. Sourcemaps stay off by default (`HOSAKA_SOURCEMAP=1` to re-enable).

---

## Docker (no Pi required)

```bash
./docker/dev.sh               # start services
./docker/dev.sh tui            # full interactive terminal
./docker/dev.sh test           # run tests
./docker/dev.sh stop           # shut down
```

The Docker build copies `identity/`, `manager/`, and `skills/` into the image
and runs `scripts/bootstrap_picoclaw_runtime.py --home /root --seed-config`,
so the desktop/client container ships the same Hosaka identity, manager
charter, task template, and built-in skill catalog as the appliance.

---

## What you get

```
hosaka:/home/operator > /commands

  ── Chat & AI ──
    /chat              Interactive AI session
    /ask <text>        One-shot question

  ── System ──
    /status            Uptime, IP, model, services
    /doctor            Diagnose config
    /restart all       Restart services
    /update            Pull + redeploy

  ── Network ──
    /net               IP, Wi-Fi, Tailscale
    /ping /dns /scan   Network tools

  ── Tools ──
    /draw <subject>    AI-generated ASCII art
    /plant             Check on your alien plant
    /orb               The orb sees you
    /code              Drop to shell

  ── Reference ──
    /help              Quick start
    /lore              ...
    /about             System info
```

Everything else you type goes to the AI agent. Prefix `!` for shell commands.

---

## The plant

An alien organism lives in your terminal. It grows when you use Hosaka
and wilts when you don't.

```
  dead        wilted       dry        stable      growing      bloom       colony

              ,            \ |         _         \ _ /       * \ _ /     *@* _ *@*
              |\            \|        ( )        -( )-        @( )@      \@(*)@/ *
   .          | )            |        \|/       / \|         */\|/\*    */\\|//\@*
   |          |/             |         |       (_) |/\      (@)|  /\    (@)|  /\(@
   |         _|_           __|__     __|__         |/        \ | /(_)    *\|*/(_)*
  .|.       [___]         [_____]   [_____]      __|__        _|_/_      __|_/__|_
 [___]                                          [_____]      [_____]    [___][__]
```

State persists to `~/.hosaka/plant.json`. Every command feeds it.
Hours of inactivity drain it. Reach colony state and it records a birth.


---

## Voice mode

Hosaka is now voice-first. The `◎ voice` tab opens a full-screen orb
that acts as the primary control surface. On 5-inch and similar small
screens the orb fills the display; tap **▲ transcript** to slide up a
drawer with the conversation history, mode selector, and camera controls.

### Two-lane architecture

Voice runs two lanes simultaneously:

| Lane | Path | What it does |
|------|------|-------------|
| **Realtime** | Browser WebRTC → OpenAI Realtime API | Instant voice-to-voice. The model's "conscience" — personality, small talk, quick answers. |
| **Agent** | Browser → Whisper STT → PicoClaw → reply | Real machine work: shell, git, file ops, repo inspection. Runs in the background. Hosaka acknowledges immediately, chimes when the result lands. |

Switch between lanes with the **local agent / openai realtime** toggle
in the drawer. Public deployments stay locked to the Realtime demo lane;
local builds expose both.

### Interaction

- **Agent lane (hold to talk):** hold the orb → speak → release.
  The UI immediately echoes "heard you. working on it." while PicoClaw
  works. A two-tone chime signals completion and the reply appears.
- **Realtime lane (tap to toggle):** tap the orb once to open the
  WebRTC session; tap again to close. The model speaks back through
  your browser's audio output.

### Tools the Realtime session can call

| Tool | What it does |
|------|-------------|
| `todo_add` | Appends to `~/.hosaka/voice_todos.jsonl`, mirrored into the Todo panel |
| `set_mode` | Switches console/device mode |
| `get_status` | Host · uptime · free RAM · CPU temperature |
| `see` | Grabs a camera frame, runs vision, speaks the caption |
| `ask_agent` | Hands the prompt to PicoClaw for real agentic tool use |

When you say "run `ls -la`" or "what's the biggest file in my home
directory", the Realtime model calls `ask_agent` which routes to
PicoClaw — the same code path as the Agent lane.

### Audio format

The browser records `audio/webm;codecs=opus`. Hosaka strips the codec
parameter before sending to OpenAI Whisper, which only accepts bare
MIME types. The filename extension is inferred from the content-type so
Whisper can sniff the container format.

### Env knobs

| Variable | Default | Note |
|---|---|---|
| `OPENAI_API_KEY` | — | Reused from the LLM config; never sent to the browser |
| `HOSAKA_VOICE_MODEL` | `gpt-realtime` | Realtime model SKU |
| `HOSAKA_VOICE_VOICE` | `marin` | Realtime voice preset |
| `HOSAKA_VOICE_TRANSCRIBE_MODEL` | `whisper-1` | STT model for the Agent lane |
| `HOSAKA_VOICE_CAMERA` | `/dev/video0` | V4L2 device for the `see()` tool |
| `HOSAKA_VOICE_VISION_MODEL` | `gpt-4o-mini` | Vision model for `see()` |
| `HOSAKA_PUBLIC_MODE` | unset | `1` locks the voice panel to Realtime demo only |
| `HOSAKA_API_TARGET` | `http://127.0.0.1:8421` | Vite-dev proxy target for `/api` and `/ws` |

Minimum local `.env` for Realtime → PicoClaw control:

```dotenv
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"
HOSAKA_VOICE_MODEL="gpt-realtime"
HOSAKA_VOICE_VOICE="marin"
PICOCLAW_SESSION="hosaka:main"
```

`HOSAKA_VOICE_MODEL`, `HOSAKA_VOICE_VOICE`, and `PICOCLAW_SESSION` may be
omitted if the defaults above are acceptable. `OPENAI_API_KEY` is the only
hard requirement for Realtime token minting.

### Small-screen / kiosk layout

At ≤ 720 px the orb expands to fill the panel (≈ 72 vw). The transcript,
mode selector, and camera controls live in a slide-up drawer triggered
by the **▲ transcript** button at the bottom of the orb stage. This is
the intended layout for a 5-inch HDMI display running the Electron kiosk.

### Headless daemon

```bash
hosaka voice                      # foreground mic/speaker daemon
sudo systemctl enable --now hosaka-voice   # or as a systemd unit
```

The daemon uses the same tool surface as the browser panel, including
`ask_agent` → PicoClaw. Wake word default is `hey_jarvis` (bundled
openwakeword model); custom `hey hosaka` requires training — see
[openwakeword docs](https://github.com/dscripka/openWakeWord#training-new-models).

### Install voice deps

```bash
./scripts/install_voice_deps.sh   # portaudio, alsa, v4l, ffmpeg, sounddevice, …
export OPENAI_API_KEY=sk-…
```

### Architecture notes (future self)

The natural next step is feeding PicoClaw's `spoken` reply into the
Realtime session's audio output so the agent lane can *talk back*
without a second round-trip to the Realtime API. The structured
`{ spoken, thought, did_work }` payload from `run_agent_voice_turn()`
is already designed for this. See [`docs/voice.md`](./docs/voice.md)
for full status, known gaps, and roadmap.



## Configuration

### LLM backend

Set via the **⚙ Settings drawer → LLM Backend** in the web UI, or via
the **inline terminal prompt** on first keystroke, or via env vars:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | unset | Required for OpenAI; placeholder accepted by Ollama |
| `OPENAI_MODEL` | `gpt-4.1` | Main model for an unconfigured install |
| `OPENAI_BASE_URL` | `https://api.openai.com` | OpenAI endpoint; can be changed for Ollama, LM Studio, etc. |

Persisted config lives in `/var/lib/hosaka/llm.json` (or
`~/.hosaka/llm.json` for non-root installs) and is applied on startup.
PATCH `/api/llm-key` applies it to the running process without restart.

`/select llm <number>` saves the provider/model for future sessions, including
GUI refreshes. Every TUI startup reloads that choice over stale inherited
backend settings. Choice `0` is OpenAI GPT-4.1. Existing saved choices are
preserved; `HOSAKA_LOCAL_FIRST=1` explicitly opts into the Ollama defaults
instead of GPT-4.1 when no configuration has been saved.

Hosaka can persist a live local Ollama selection by probing the configured
hosts' `/api/tags` endpoints:

```bash
curl -X POST http://localhost:8421/api/ollama/discover
```

It probes `127.0.0.1` and `100.78.174.79` by default, preserving the current
model when available. Set `HOSAKA_OLLAMA_DISCOVERY_URLS` to a comma-separated
list of known LAN/Tailscale Ollama URLs; Hosaka only probes those hosts and
does not scan a network. The persisted discovery configuration is refreshed on
each web-server start, so it can move to a reachable local server offline.

### Offline Ollama protocol

When Wi-Fi has no internet but your Ollama machine and Hosaka are on the same
router or hotspot, type exactly this:

```bash
hosaka scan llm
```

It scans the active private `/24` LAN for Ollama's port `11434`, then prints
every responding server and its installed models. To connect to the first one
and keep it through reboots, type:

```bash
hosaka scan llm --use
```

In the Hosaka console, `/scan` lists nearby network devices, `/scan llm` finds
model servers, and `/scan llm use` saves the first result. No internet, cloud
account, or remembered IP address is needed.

To see the model currently selected by Hosaka:

```bash
hosaka llm
```

`hosaka llm list` means the same thing.

In the terminal, `/help` includes a numbered provider/model selector:

```text
/select llm
0 openai gpt-4.1
1 openai gpt-4.1-mini
2 openai gpt-4o-mini
3 ollama qwen3:4b — http://127.0.0.1:11434/v1

/select llm 0
```

The OpenAI entries start with this small fixed list and include additional
models from saved OpenAI profiles. The fixed entries are not a guarantee of
API-account access. Ollama entries come from saved selections and installed
models reported by known servers; the Qwen entry above is an example, not a
bundled model. Unavailable saved Ollama choices are labelled, and cannot be
selected until their server and model are available.

Run `/select llm` before choosing a number. Numbers refer to the last displayed
list and remain stable until you list again. Selection switches the running
console immediately and saves the provider, endpoint, and model for future
starts. Saved non-Ollama OpenAI-compatible profiles are also listed without
being treated as Ollama servers. OpenAI uses its saved key or `OPENAI_API_KEY`
from the environment, Hosaka secrets store, or Picoclaw configuration/security
file; if none exists, run `hosaka secrets set OPENAI_API_KEY`
from a real shell. Keys are never printed by the menu.

The menu only checks saved endpoints and `HOSAKA_OLLAMA_DISCOVERY_URLS`, with
a one-second probe per host; it does not scan the LAN. Use `/scan llm` to
discover other hosts. Before an Ollama completion, Hosaka checks that the
selected server reports the selected model via `/api/tags`. If the server
is absent or the model is missing, it reports the problem without sending
a chat request. This is a runtime guard, not a Python `assert` that could be
disabled with optimization.

To switch back to OpenAI (using its saved profile and key):

```bash
hosaka llm openai
```

To return to local Ollama later:

```bash
hosaka llm ollama --use
```

`hosaka llm scan` is the same command as `hosaka scan llm`; add `--use` to
save the first working server.

### System settings

All of the following are editable at runtime in the **⚙ Settings
drawer → System** section, or via PATCH `/api/config`:

| Variable | Default | Description |
|---|---|---|
| `HOSAKA_STATE_PATH` | `~/.hosaka/state.json` | Persistent state |
| `HOSAKA_BOOT_MODE` | `console` | `console` (Python tty shell), `headless` / `web` (API+SPA only), `kiosk` (same + Electron fullscreen; use `./scripts/switch_boot_mode.sh`) |
| `HOSAKA_SOURCEMAP` | unset | Set to `1` to emit sourcemaps from `vite build` (off by default to halve the build's RAM peak on the Pi) |
| `HOSAKA_WEB_PORT` | `8421` | LAN setup web server port |
| `PICOCLAW_SESSION` | `hosaka:main` | Agent session key |
| `PICOCLAW_MODEL` | *(default)* | Override model |
| `HOSAKA_PUBLIC_MODE` | unset | Set to `1` / `true` / `yes` to hide the ⚙ settings drawer from all users. Intended for the **public web deployment** of this repo where strangers should not be able to reconfigure the LLM backend or system settings. When set, `/api/health` returns `settings_enabled: false`; the frontend reads this on mount and never renders the gear button or `SettingsDrawer`. The check is **server-side** — it cannot be bypassed from the browser. Local Docker installs should leave this unset (settings enabled by default). **Do not remove this flag** — it is the deliberate access control boundary between the operator-owned appliance and the public-facing hosted instance. |

---

## Requirements

- Python 3.10+
- Picoclaw v0.2+
- systemd (for appliance boot)
- No desktop environment needed
