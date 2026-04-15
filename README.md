# Hosaka Field Terminal

A terminal-first appliance shell for cyberdeck and Raspberry Pi operation.
Hosaka boots directly into a guided setup flow, persists state across reboots,
serves a parallel LAN setup GUI, and drops the operator into a branded
**No Wrong Way** console once onboarding is complete.

Designed for headless Debian/Linux. No desktop environment required.

---

## Quick Start (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-hosaka.txt
python -m hosaka
```

State defaults to `/var/lib/hosaka/state.json` — override with `HOSAKA_STATE_PATH`.

---

## Red Carpet Setup (Recommended)

One command does everything — installs Hosaka, installs OpenClaw (Ollama +
default LLM), enables the systemd service, and starts onboarding:

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
./scripts/setup_hosaka.sh
```

Optional flags:

```bash
OPENCLAW_MODEL=mistral ./scripts/setup_hosaka.sh     # use a different model
INSTALL_TAILSCALE=1 ./scripts/setup_hosaka.sh         # also install Tailscale
HOSAKA_BOOT_MODE=headless ./scripts/setup_hosaka.sh   # web-only setup
SKIP_MODEL_PULL=1 ./scripts/setup_hosaka.sh           # skip LLM download
```

When it finishes you'll see the web setup URL and can press Enter to start
onboarding immediately. The `chat` command works as soon as the model is pulled.

---

## Appliance Install (Raspberry Pi / Debian)

```bash
./scripts/install_hosaka.sh
sudo systemctl start hosaka-field-terminal.service
```

Optional install flags:

```bash
INSTALL_TAILSCALE=1 ./scripts/install_hosaka.sh   # install Tailscale
INSTALL_CADDY=1     ./scripts/install_hosaka.sh   # install Caddy
PYTHON_BIN=python3.11 ./scripts/install_hosaka.sh # use specific Python
```

The installer rsyncs the project to `/opt/hosaka-field-terminal`, creates a
venv, installs requirements, copies systemd units, and enables the console
service by default.

### Installing OpenClaw separately

If you used `install_hosaka.sh` instead of the red carpet setup, install
OpenClaw (Ollama + model) separately:

```bash
./scripts/install_openclaw.sh
```

Or from inside the Hosaka console: `/openclaw install`

| Variable | Default | Description |
|---|---|---|
| `OPENCLAW_MODEL` | `llama3` | Model to pull |
| `OPENCLAW_PORT` | `11434` | Ollama API port |
| `SKIP_MODEL_PULL` | `0` | Set to `1` to skip download |

---

## Configuration Reference

All behavior is configurable through environment variables.
Set them in your shell, in the systemd unit's `Environment=` lines,
or in an `/etc/default/hosaka` file sourced by the unit.

| Variable | Default | Description |
|---|---|---|
| `HOSAKA_STATE_PATH` | `/var/lib/hosaka/state.json` | Path to the persistent setup state file |
| `HOSAKA_WEB_HOST` | `0.0.0.0` | Bind address for the LAN setup web server |
| `HOSAKA_WEB_PORT` | `8421` | Port for the LAN setup web server |
| `HOSAKA_BOOT_MODE` | `console` | `console` (TTY + web) or `headless` (web only) |
| `HOSAKA_REPO_ROOT` | *(auto-detected)* | Git repo root for the update script |
| `PYTHON_BIN` | `python3` | Python binary used by `install_hosaka.sh` |
| `INSTALL_TAILSCALE` | `0` | Set to `1` to install Tailscale during setup |
| `INSTALL_CADDY` | `0` | Set to `1` to install Caddy during setup |

---

## State File

Persisted at `HOSAKA_STATE_PATH` (default `/var/lib/hosaka/state.json`).
Human-readable JSON, created automatically on first boot.

| Field | Type | Default | Description |
|---|---|---|---|
| `setup_completed` | `bool` | `false` | Whether first-boot onboarding has finished |
| `current_step` | `str` | `"welcome_and_branding"` | Active onboarding step name |
| `hostname` | `str` | `""` | Configured device hostname |
| `local_ip` | `str` | `""` | Detected LAN IP address |
| `tailscale_status` | `str` | `"unknown"` | `unknown` / `not-installed` / `installed` / `connected` |
| `backend_endpoint` | `str` | `""` | Optional backend URL |
| `workspace_root` | `str` | `"/opt/hosaka/workspace"` | Working directory for operator data |
| `theme` | `str` | `"dark"` | UI theme (`dark`, `amber`, `blue`) |
| `openclaw_enabled` | `bool` | `true` | Whether OpenClaw integration is active |
| `openclaw_path` | `str` | `"/opt/openclaw"` | Path to OpenClaw installation |
| `openclaw_ready` | `bool` | `false` | Whether OpenClaw passed its readiness check |
| `timestamps` | `dict` | `{"created": …, "updated": …}` | ISO 8601 UTC timestamps |
| `last_error` | `str` | `""` | Last recorded error message |

---

## Boot Modes

### Console mode (default)

```bash
sudo systemctl enable hosaka-field-terminal.service
```

Takes over `/dev/tty1`. Keyboard input goes directly into the TUI setup and
then the main console. The LAN web server runs in parallel.

### Headless mode

```bash
sudo systemctl enable hosaka-field-terminal-headless.service
```

No TTY. All setup happens through the web GUI at `http://<device-ip>:8421`.
Output goes to the systemd journal.

Only one mode should be enabled at a time.

---

## Setup Flow

First boot walks through 10 onboarding steps, resumable across reboots.
Both the TUI and the LAN web GUI drive the same orchestrator and state file.

| # | Step | What it does |
|---|---|---|
| 1 | `welcome_and_branding` | Splash screen, confirm start |
| 2 | `detect_network_status` | Auto-detect LAN IP and Tailscale |
| 3 | `choose_or_confirm_hostname` | Set or accept device hostname |
| 4 | `configure_or_confirm_tailscale` | Tailscale auth / skip |
| 5 | `configure_backend_endpoint_optional` | Optional backend URL |
| 6 | `configure_workspace_root` | Operator data directory |
| 7 | `configure_theme` | `dark` / `amber` / `blue` |
| 8 | `configure_openclaw` | Enable + path, or skip |
| 9 | `confirm_setup_summary` | Review before committing |
| 10 | `finalize_and_enter_main_console` | Mark complete, enter console |

During any setup step you can type `help` for contextual guidance or `update`
to pull the latest code inline.

---

## Command Reference

After setup, the operator lands at the `hosaka>` prompt.
All slash commands, builtins, and raw shell commands are available.

| Command | Description |
|---|---|
| `/help` | Show the No Wrong Way command guide with all available commands |
| `/status` | Print system and setup status |
| `/setup` | Info about the onboarding orchestrator and web UI |
| `/network` | Network info — use setup flow or web page for full details |
| `/theme` | Theme info — use setup flow or web GUI to change theme |
| `/manifest` | Open the built-in operator manual in a paginated reader |
| `update` | Pull latest code via `scripts/update_hosaka.sh` and restart services |
| `read <file>` | Paginated file reader with numbered lines (`read manifest` for the field guide) |
| `code` | Drop to an interactive sub-shell (`$SHELL`). `exit` or Ctrl-D to return |
| `chat` | Enter LLM conversation mode (OpenClaw → OpenAI → offline) |
| `chat <prompt>` | One-shot LLM query, print response, stay in console |
| `/openclaw status` | Check if OpenClaw (Ollama) is online, show endpoint and model |
| `/openclaw doctor` | Full diagnostic — install, version, running, models, API |
| `/openclaw install` | Run `scripts/install_openclaw.sh` from inside the console |
| `pwd` | Print the current working directory |
| `cd <path>` | Change working directory (supports `~`, relative, and absolute paths) |
| `/exit` | Exit the Hosaka console |
| *(anything else)* | Passed to the system shell; on failure, suggests known commands |

### Reader controls

| Key | Action |
|---|---|
| **Enter** | Next page |
| **q** | Quit reader |

### Unknown command behavior

If a command isn't recognized or fails, Hosaka:

1. Explains what happened
2. Lists suggested commands
3. Hints at `read manifest`

No dead ends. **No Wrong Way.**

---

## LAN Setup Web GUI

The built-in FastAPI server runs on `HOSAKA_WEB_HOST:HOSAKA_WEB_PORT`
(default `0.0.0.0:8421`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Setup home — current step, progress, links |
| GET | `/network` | Network status (LAN IP, Tailscale) |
| GET | `/identity` | Hostname edit form |
| POST | `/identity` | Save hostname |
| GET | `/backend` | Backend endpoint edit form |
| POST | `/backend` | Save backend endpoint |
| GET | `/workspace` | Workspace root edit form |
| POST | `/workspace` | Save workspace root |
| GET | `/theme` | Theme picker |
| POST | `/theme` | Save theme |
| GET | `/openclaw` | OpenClaw enable/disable + path |
| POST | `/openclaw` | Save OpenClaw config |
| GET | `/progress` | Full state as JSON |
| POST | `/next` | Advance to next step |
| POST | `/back` | Go to previous step |
| GET | `/complete` | Finalize setup |

---

## Updating

From the device:

```bash
./scripts/update_hosaka.sh            # current branch
./scripts/update_hosaka.sh main       # specific branch
```

The script fetches, pulls, rsyncs to `/opt/hosaka-field-terminal`, and
restarts whichever systemd service is enabled.

From inside the console, type `update` at the `hosaka>` prompt.

---

## Docker Development (no Pi required)

Spin up a headless Hosaka + Ollama environment in Docker.
Works on macOS, Linux, or any machine with Docker.

```bash
./docker/dev.sh               # start background services (headless + Ollama)
./docker/dev.sh pull-model     # download the LLM into Ollama
./docker/dev.sh tui            # ★ full interactive TUI — your main dev loop
./docker/dev.sh test           # run the test suite
./docker/dev.sh shell          # bash shell inside the container
./docker/dev.sh status         # health check
./docker/dev.sh logs           # tail logs
./docker/dev.sh stop           # shut down
./docker/dev.sh nuke           # stop + delete all data
```

The **`tui`** command gives you the exact same experience as booting a real
Raspberry Pi — full setup flow, main console, `chat`, `code`, everything.
Source code is live-mounted so you edit locally and restart to pick up changes.

### Export a shippable image

```bash
./docker/dev.sh export            # → hosaka-field-terminal.tar.gz
```

Transfer to any Docker-capable device (Pi, server, VM):

```bash
scp hosaka-field-terminal.tar.gz pi@<device-ip>:~/
ssh pi@<device-ip>
docker load < hosaka-field-terminal.tar.gz
docker run -d -p 8421:8421 --name hosaka hosaka:ship
```

---

## Debugging

```bash
# follow live logs
sudo journalctl -u hosaka-field-terminal.service -f

# inspect state
cat /var/lib/hosaka/state.json

# check web API
curl http://127.0.0.1:8421/progress

# manual run (stop the service first to free the port)
sudo systemctl stop hosaka-field-terminal.service
HOSAKA_WEB_PORT=8422 python -m hosaka
```

---

## Future Features

### `code` — drop to raw terminal

`code` at the `hosaka>` prompt spawns `$SHELL` (or `/bin/bash`) in the
current working directory. `exit` or Ctrl-D returns to the Hosaka console.

### `chat` — LLM conversation mode

`chat` enters a conversational loop — every line is sent to the LLM and the
response streams back token-by-token. `/back` or Ctrl-C returns to console.
`/clear` resets conversation history.

`chat <prompt>` sends a one-shot query without entering the loop.

LLM routing: **OpenClaw (Ollama, local)** → **OpenAI API** → **offline assist**.
The router probes in order and cascades automatically.

### `/openclaw` commands

| Command | Description |
|---|---|
| `/openclaw status` | Quick health check — is it up? |
| `/openclaw doctor` | Full diagnostic report |
| `/openclaw install` | Run the installer from inside the console |

---

## OpenClaw Integration

Onboarding includes an OpenClaw configuration step.
When `openclaw_ready=true`, the main console can route to OpenClaw as the
default operator shell.

See `docs/openclaw_console_plan.md` for the full roadmap.

---

## Project Layout

```
hosaka/
  __main__.py        # entry point
  main_console.py    # post-setup REPL with slash commands
  boot/              # systemd → launcher → orchestrator → console
  config/            # SetupState dataclass + JSON persistence
  setup/             # orchestrator + step catalog
  tui/               # interactive terminal setup flow
  web/               # FastAPI LAN setup GUI
  network/           # LAN IP + Tailscale detection
  offline/           # rule-based intent classifier
  ops/               # update script runner
  llm/               # LLM router, OpenClaw adapter, OpenAI adapter, chat REPL
scripts/
  setup_hosaka.sh    # red carpet one-shot bootstrap
  install_hosaka.sh  # appliance installer
  install_openclaw.sh # Ollama + model installer
  update_hosaka.sh   # git pull + redeploy + service restart
docker/
  Dockerfile         # Debian Bookworm headless image
  compose.yml        # Hosaka + Ollama sidecar
  dev.sh             # CLI wrapper for all dev commands
systemd/
  hosaka-field-terminal.service           # console mode
  hosaka-field-terminal-headless.service  # headless mode
tests/
docs/
  no_wrong_way_manifest.md    # built-in operator manual
  openclaw_console_plan.md    # OpenClaw integration roadmap
  llm_integration_plan.md     # chat/code LLM architecture
requirements-hosaka.txt
```

---

## Requirements

- Python 3.10+
- systemd (for appliance boot)
- No desktop environment needed
- See `requirements-hosaka.txt` for Python dependencies
