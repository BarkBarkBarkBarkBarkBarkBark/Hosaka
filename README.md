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

## The single entrypoint

The canonical way to run Hosaka — on the Pi, on your laptop, anywhere —
is the **Electron kiosk host** at [`kiosk/`](./kiosk/). It wraps the
SPA in a native Chromium window and turns on Electron's `<webview>` tag
so the Web panel renders any URL inline, with no X-Frame-Options grief.

```bash
cd kiosk
npm install      # first time only
npm run dev      # vite + electron together, HMR, windowed
```

On the edge device, `hosaka-kiosk.service` runs the same Electron host
fullscreen at boot, pointed at the local FastAPI on `127.0.0.1:8421`.
See [`kiosk/README.md`](./kiosk/README.md) for details.

---

## Documentation

Full reference site (auto-built from this commit on every push to `main`):

**→ https://&lt;your-gh-user&gt;.github.io/Hosaka/**

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
  export OPENAI_API_KEY=sk-...
  export OPENAI_MODEL=gpt-4o-mini            # optional, default
  export OPENAI_BASE_URL=http://localhost:11434/v1  # for Ollama etc.
  ```

Any of these approaches works — mix and match.

> **Privacy**: the API key is stored on-device only. It is never sent
> to Hosaka's servers, never logged, and never included in chat context.

### 3. Clone and run

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
python -m venv .venv && source .venv/bin/activate
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
hosaka logs [web|pico|<unit>]  # tail journalctl
hosaka reboot                  # safe sync + reboot
```

### Why "build mode"?

The Pi 3B has **906 MiB RAM**. With Chromium kiosk + uvicorn + picoclaw +
the Cursor remote server all loaded, there is no headroom left for
`npm run build` and the OOM killer takes the build (or, worse, the SSH
session). `hosaka mode build` shuts down the kiosk and the picoclaw gateway
to free ~700 MiB before you build. `--persist` writes a marker to
`/boot/firmware/hosaka-build-mode` so the Pi stays in build mode across
reboots until you flip back with `hosaka mode kiosk --persist`.

A typical SSH-then-deploy session looks like:

```bash
ssh operator@hosaka
hosaka mode build
cd ~/Hosaka && git pull
hosaka deploy
hosaka mode kiosk
```

### Why is the build so much lighter now?

We aggressively stripped the frontend in 2026-04 (see
`.cursor/plans/hosaka_lean_&_build_mode_*.plan.md`):

- `tsc -b` is no longer in the default build path — `npm run build` is just
  `vite build` (~250 MB peak vs. ~750 MB before). Use `npm run build:check`
  on a dev machine for the type-safety gate.
- Sourcemaps off by default (`HOSAKA_SOURCEMAP=1` to re-enable).
- All panels are `React.lazy`'d so first paint is just the shell.
- `react-markdown` + `remark-gfm` (~1 MB of `node_modules`, 15 transitive
  deps) replaced with `marked` (~50 KB, zero deps).
- The whole `i18next` + `react-i18next` + http-backend + language-detector
  stack (~2 MB) replaced with a 200-line in-house hook in
  [`frontend/src/i18n.ts`](frontend/src/i18n.ts) that bundles all 6 locales
  via `import.meta.glob`.

Net bundle: **~4.8 MB → ~700 KB**. Build memory peak: **~750 MB → ~250 MB**.

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
| `HOSAKA_VOICE_MODEL` | `gpt-4o-realtime-preview` | Realtime model SKU |
| `HOSAKA_VOICE_VOICE` | `verse` | Realtime voice preset |
| `HOSAKA_VOICE_TRANSCRIBE_MODEL` | `whisper-1` | STT model for the Agent lane |
| `HOSAKA_VOICE_CAMERA` | `/dev/video0` | V4L2 device for the `see()` tool |
| `HOSAKA_VOICE_VISION_MODEL` | `gpt-4o-mini` | Vision model for `see()` |
| `HOSAKA_PUBLIC_MODE` | unset | `1` locks the voice panel to Realtime demo only |

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
| `OPENAI_API_KEY` | — | Required for OpenAI (and most compatible endpoints) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `OPENAI_BASE_URL` | `https://api.openai.com` | Override for Ollama, LM Studio, etc. |

Persisted config lives in `/var/lib/hosaka/llm.json` (or
`~/.hosaka/llm.json` for non-root installs) and is applied on startup.
PATCH `/api/llm-key` applies it to the running process without restart.

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
