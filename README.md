# CyberDeck

This repository now contains two deliverables:

1. **CyberDeck marketing site** (existing Next.js 16 app).
2. **Hosaka Field Terminal appliance slice** (new Python + systemd first-boot experience).

The Hosaka work is additive and does **not** remove or alter the existing website stack.

---

## 1) Existing Web Platform (unchanged)

- Framework: Next.js 16 (App Router)
- Language: TypeScript
- Styling: Tailwind CSS

Run locally:

```bash
npm install
npm run dev
```

---

## 2) Hosaka Field Terminal Appliance

A terminal-first appliance shell intended for a headless Debian/Linux box that:

- auto-starts on boot (systemd)
- runs a guided first-boot setup in terminal
- serves a lightweight LAN setup GUI in parallel
- persists setup progress and resumes after reboot
- launches a branded main console after setup

### New repository layout

```text
hosaka/
  boot/          # boot launcher and web startup
  tui/           # terminal setup flow
  setup/         # orchestrator + shared setup steps
  web/           # FastAPI setup pages
  network/       # local/tailscale discovery helpers
  offline/       # offline intent classifier (rules)
  config/        # persisted setup state model/store
scripts/
  install_hosaka.sh
systemd/
  hosaka-field-terminal.service
tests/
  test_hosaka_orchestrator.py
  test_hosaka_offline.py
requirements-hosaka.txt
```

### Why this is streamlined

To reduce redundancy and keep behavior consistent between TUI and web:

- setup step names are centralized in `hosaka/setup/steps.py`
- both terminal and web read/write the same state file fields
- one orchestrator (`hosaka/setup/orchestrator.py`) drives flow state/progress

### Quick start (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-hosaka.txt
python -m hosaka
```

Default setup state path in dev: `/var/lib/hosaka/state.json` (override with `HOSAKA_STATE_PATH`).

### Appliance install (target Debian box)

```bash
./scripts/install_hosaka.sh
sudo systemctl daemon-reload
sudo systemctl start hosaka-field-terminal.service
sudo systemctl status hosaka-field-terminal.service
```

`hosaka-field-terminal.service` is now **console-first** (keyboard input on tty1).  
Use `hosaka-field-terminal-headless.service` only for web-only/headless operation.

Optional install flags:

- `INSTALL_TAILSCALE=1 ./scripts/install_hosaka.sh`
- `INSTALL_CADDY=1 ./scripts/install_hosaka.sh`

### Updating Hosaka on device

Use the updater script to pull latest code and propagate it to `/opt/hosaka-field-terminal`:

```bash
./scripts/update_hosaka.sh
```

Optional: pass a branch name:

```bash
./scripts/update_hosaka.sh work
```

### Boot behavior

On boot, systemd runs `python -m hosaka`, which:

1. starts the local FastAPI setup server (`0.0.0.0:8421` by default)
2. opens the branded terminal setup flow when `setup_completed=false`
3. advertises the LAN setup URL in terminal
4. resumes setup from persisted `current_step`
5. enters the main Hosaka console after completion

### LAN setup GUI pages

- `/` setup home
- `/network` network status
- `/identity` hostname
- `/backend` backend endpoint
- `/workspace` workspace root
- `/theme` theme
- `/openclaw` openclaw setup
- `/progress` JSON progress payload
- `/complete` finalize setup

### OpenClaw integration

- Onboarding includes an OpenClaw configuration step (path + enable/disable).
- See implementation roadmap: `docs/openclaw_console_plan.md`.

### Main console operator UX

- Motto: **No Wrong Way**.
- Unknown/failed commands trigger playful redirect guidance and suggested commands.
- Built-in reader command: `read <file>` with pager controls (`Enter` next page, `q` exit).
- Built-in manual: `read manifest` (loads `docs/no_wrong_way_manifest.md`).
- Supports common shell navigation in-console (`cd`, `pwd`) and runs shell commands from the active working directory.

### Debugging

```bash
sudo journalctl -u hosaka-field-terminal.service -f
cat /var/lib/hosaka/state.json
curl http://127.0.0.1:8421/progress
sudo -u root /opt/hosaka-field-terminal/.venv/bin/python -m hosaka
```

If you manually run Hosaka while the service is already running, port `8421` may already be occupied.
In that case, stop the service first or run with a different port:

```bash
sudo systemctl stop hosaka-field-terminal.service
HOSAKA_WEB_PORT=8422 sudo -u root /opt/hosaka-field-terminal/.venv/bin/python -m hosaka
```

If you change the systemd unit manually, run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart hosaka-field-terminal.service
```

### Assumptions

- systemd available
- python3.10+ available
- no desktop environment required
- headless-friendly deployment
