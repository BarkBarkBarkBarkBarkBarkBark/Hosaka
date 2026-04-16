# Hosaka Field Terminal

A terminal-first appliance shell for cyberdeck and Raspberry Pi operation.
Hosaka boots directly into a guided setup flow, persists state across reboots,
serves a parallel LAN setup GUI, and drops the operator into a branded
**No Wrong Way** console once onboarding is complete.

Everything you type at the prompt goes to the **Picoclaw** AI agent. Use `!cmd`
for shell commands, `/help` for builtins.

Designed for headless Debian/Linux. No desktop environment required.

---

## Prerequisites

### Install Picoclaw (required)

Picoclaw is a lightweight agentic framework that runs locally.
Download the binary from [sipeed/picoclaw releases](https://github.com/sipeed/picoclaw/releases):

```bash
cd /tmp
curl -L https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz \
  -o picoclaw_Linux_arm64.tar.gz
tar -xzf picoclaw_Linux_arm64.tar.gz
chmod +x picoclaw
sudo mv picoclaw /usr/local/bin/
```

Then initialise config and set up your model provider:

```bash
picoclaw onboard
```

Verify:

```bash
picoclaw version
picoclaw status
```

---

## Quick Start (dev)

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-hosaka.txt

# Start picoclaw gateway in background
picoclaw gateway &

# Run Hosaka
python -m hosaka
```

State defaults to `~/.hosaka/state.json`, falling back to `/var/lib/hosaka/state.json`
when running as root. Override with `HOSAKA_STATE_PATH`.

---

## Red Carpet Setup (Recommended)

One command does everything — checks Picoclaw, installs Hosaka, enables
systemd services, and starts onboarding:

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
./scripts/setup_hosaka.sh
```

Optional flags:

```bash
INSTALL_TAILSCALE=1 ./scripts/setup_hosaka.sh     # also install Tailscale
HOSAKA_BOOT_MODE=headless ./scripts/setup_hosaka.sh # web-only setup
```

Picoclaw must be installed first (see Prerequisites above). The setup script
will error early if it isn't found.

---

## Appliance Install (Raspberry Pi / Debian)

```bash
./scripts/install_hosaka.sh
sudo systemctl start picoclaw-gateway.service
sudo systemctl start hosaka-field-terminal.service
```

Optional install flags:

```bash
INSTALL_TAILSCALE=1 ./scripts/install_hosaka.sh   # install Tailscale
INSTALL_CADDY=1     ./scripts/install_hosaka.sh   # install Caddy
PYTHON_BIN=python3.11 ./scripts/install_hosaka.sh # use specific Python
```

The installer rsyncs the project to `/opt/hosaka-field-terminal`, creates a
venv, installs requirements, copies systemd units (including `picoclaw-gateway.service`),
and enables both the gateway and console services.

---

## Configuration Reference

All behavior is configurable through environment variables.
Set them in your shell, in the systemd unit's `Environment=` lines,
or in an `/etc/default/hosaka` file sourced by the unit.

| Variable | Default | Description |
|---|---|---|
| `HOSAKA_STATE_PATH` | `~/.hosaka/state.json` | Path to the persistent setup state file |
| `HOSAKA_WEB_HOST` | `0.0.0.0` | Bind address for the LAN setup web server |
| `HOSAKA_WEB_PORT` | `8421` | Port for the LAN setup web server |
| `HOSAKA_BOOT_MODE` | `console` | `console` (TTY + web) or `headless` (web only) |
| `HOSAKA_LOG_FILE` | `/var/log/hosaka/boot.log` | Boot log file path |
| `HOSAKA_LOG_LEVEL` | `INFO` | Python logging level |
| `PICOCLAW_SESSION` | `hosaka:main` | Session key for Picoclaw agent |
| `PICOCLAW_MODEL` | *(picoclaw default)* | Override the model used by the agent |

---

## Boot Modes

### Console mode (default)

```bash
sudo systemctl enable picoclaw-gateway.service
sudo systemctl enable hosaka-field-terminal.service
```

Takes over `/dev/tty1`. Keyboard input goes directly into the console.
The LAN web server runs in parallel. Getty login prompt is suppressed.

### Headless mode

```bash
sudo systemctl enable picoclaw-gateway.service
sudo systemctl enable hosaka-field-terminal-headless.service
```

No TTY. All interaction happens through the web GUI at `http://<device-ip>:8421`.
Output goes to the systemd journal.

Only one mode should be enabled at a time.

---

## Command Reference

After setup, the operator lands at the `hosaka>` prompt.
Everything you type is sent to the Picoclaw agent by default.

| Input | What happens |
|---|---|
| `hello, what files are here?` | Sent to Picoclaw agent |
| `!ls -la` | Shell command (prefix with `!`) |
| `code` | Drop to interactive shell (`exit` to return) |
| `chat` | Enter dedicated chat mode (`/back` to return) |
| `/help` | Show available commands |
| `/status` | System status |
| `/picoclaw status` | Picoclaw health check |
| `/picoclaw doctor` | Full diagnostic |
| `/manifest` | Open the built-in operator manual |
| `update` | Pull latest code and restart services |
| `read <file>` | Paginated file reader |
| `pwd` / `cd <path>` | Navigate directories |
| `/exit` | Exit the console |

---

## LAN Setup Web GUI

The built-in FastAPI server runs on `HOSAKA_WEB_HOST:HOSAKA_WEB_PORT`
(default `0.0.0.0:8421`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Setup home — current step, progress, links |
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

From inside the console, type `update` at the prompt.

---

## Docker Development (no Pi required)

Spin up a headless Hosaka + Picoclaw environment in Docker.
Works on macOS, Linux, or any machine with Docker.

```bash
./docker/dev.sh               # start background services (headless + picoclaw)
./docker/dev.sh tui            # ★ full interactive TUI — your main dev loop
./docker/dev.sh test           # run the test suite
./docker/dev.sh shell          # bash shell inside the container
./docker/dev.sh status         # health check
./docker/dev.sh logs           # tail logs
./docker/dev.sh stop           # shut down
./docker/dev.sh nuke           # stop + delete all data
```

The **`tui`** command gives you the exact same experience as booting a real
Raspberry Pi — full setup flow, main console, agent chat, everything.
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

# boot log (tee'd from tty1)
tail -f /var/log/hosaka/boot.log

# inspect state
cat ~/.hosaka/state.json

# check web API
curl http://127.0.0.1:8421/progress

# picoclaw gateway health
curl http://127.0.0.1:18790/health

# manual run (stop the service first to free tty1)
sudo systemctl stop hosaka-field-terminal.service
python -m hosaka
```

---

## Project Layout

```
hosaka/
  __main__.py        # entry point (logging, tee to boot.log)
  main_console.py    # post-setup REPL — agent-first, !shell, /commands
  boot/              # systemd → launcher → orchestrator → console
  config/            # SetupState dataclass + JSON persistence
  setup/             # orchestrator + step catalog
  tui/               # interactive terminal setup flow
  web/               # FastAPI LAN setup GUI
  network/           # LAN IP + Tailscale detection
  offline/           # rule-based intent classifier (offline fallback)
  ops/               # update script runner
  llm/
    router.py           # Picoclaw → OpenAI → offline fallback
    picoclaw_adapter.py # subprocess adapter for picoclaw agent CLI
    chat.py             # chat REPL and one-shot handler
    openai_adapter.py   # OpenAI API fallback
scripts/
  setup_hosaka.sh    # red carpet one-shot bootstrap
  install_hosaka.sh  # appliance installer
  update_hosaka.sh   # git pull + redeploy + service restart
docker/
  Dockerfile         # Debian Bookworm headless image + picoclaw binary
  compose.yml        # Hosaka + picoclaw gateway
  dev.sh             # CLI wrapper for all dev commands
systemd/
  picoclaw-gateway.service               # picoclaw daemon
  hosaka-field-terminal.service          # console mode (tty1)
  hosaka-field-terminal-headless.service # headless mode
tests/
docs/
  no_wrong_way_manifest.md    # built-in operator manual
  picoclaw_cli_backend.md     # picoclaw CLI cheat sheet
  llm_integration_plan.md     # LLM routing architecture
requirements-hosaka.txt
```

---

## Requirements

- Python 3.10+
- Picoclaw v0.2+ ([install instructions](#install-picoclaw-required))
- systemd (for appliance boot)
- No desktop environment needed
- See `requirements-hosaka.txt` for Python dependencies
