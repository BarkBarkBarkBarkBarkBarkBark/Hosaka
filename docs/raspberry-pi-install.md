# Raspberry Pi appliance install

This is the codified flow for the Hosaka appliance Pi — what the deployment
hardening packet calls "the known-good architecture." It tracks what worked
on the `S3raspberrypi` field device and explains the choices baked into
`scripts/install_hosaka.sh`, `scripts/install_hosaka_display.sh`, and the
hardened `hosaka` CLI surface.

If you only read one section, read [Picoclaw v2 secrets](#picoclaw-v2-secrets).
That single mistake (writing an OpenAI key into `config.json` instead of
`.security.yml`) is what kept knocking the appliance offline.

---

## Known-good architecture

```
┌──────────────────────────────── boot ─────────────────────────────────┐
│  systemd  →  getty@tty1 (autologin operator)  →  .bash_profile        │
│                                                          │            │
│                                                          ▼            │
│                                                   hosaka-startx       │
│                                                          │            │
│                                                          ▼            │
│                                          startx → ~/.xinitrc          │
│                                                          │            │
│                  ┌───────────────────────────────────────┤            │
│                  ▼                  ▼                    ▼            │
│            openbox-session     xterm (opt.)        hosaka-wall        │
│                                                          │            │
│                                                          ▼            │
│                                                  Chromium kiosk       │
│                                                          │            │
│                                                          ▼            │
│                                              http://127.0.0.1:8421    │
│                                                  (FastAPI + SPA)      │
│                                                          │            │
│                                                          ▼            │
│                                            picoclaw-gateway.service   │
│                                                          │            │
│                                                          ▼            │
│                                            picoclaw (OpenAI / Ollama) │
└───────────────────────────────────────────────────────────────────────┘
```

Health-check matrix (`hosaka doctor` and the test harness both rely on this):

| layer       | command                                           | expected            |
|-------------|---------------------------------------------------|---------------------|
| backend     | `curl -s http://127.0.0.1:8421/api/health`        | `picoclaw_bin:true, picoclaw_gateway:true, openai_key:true` |
| frontend    | `curl -I http://127.0.0.1:5173`                   | `HTTP 200` (dev only — appliance serves SPA from backend) |
| picoclaw    | `picoclaw agent -m "Say exactly: hosaka online"`  | response contains `hosaka online` |
| display X   | `xdpyinfo -display :0`                            | exit 0              |
| display GUI | `pgrep -a "chromium\|Xorg\|openbox"`              | all three present   |

---

## Install profiles

The installer is split into two scripts so the headless and display stacks
stay independent — a headless install never pulls in xinit/openbox/chromium,
and a display install can run on top of a healthy headless deploy.

### `headless`

SSH/TUI only. Installs Python runtime, picoclaw, hosaka CLI, backend
webserver. Does **not** install xinit, openbox, or autostart Chromium.

```bash
HOSAKA_BOOT_MODE=headless HOSAKA_DIRECTORY="$HOME/code/Hosaka" \
  ./scripts/install_hosaka.sh
```

### `display-manual`

Installs xinit / xserver-xorg / openbox / xterm / x11-utils / dbus-x11 /
unclutter / chromium and the `hosaka-wall` + `hosaka-startx` supervisors —
but does **not** wire the GUI into boot. Run `hosaka wall start` by hand.

```bash
./scripts/install_hosaka_display.sh --profile display-manual
```

### `display-kiosk`

Appliance mode. Boots straight into the Hosaka GUI. On top of
`display-manual`, this writes:

- `~/.xinitrc`                                — session anchor (never `exec xterm`)
- `~/.local/bin/hosaka-wall`                  — Chromium supervisor
- `~/.local/bin/hosaka-startx`                — robust startx wrapper
- `/etc/X11/Xwrapper.config`                  — `allowed_users=anybody`
- `/etc/hosaka/env`                           — runtime env for systemd
- `/etc/systemd/system/getty@tty1.service.d/autologin.conf` (when `--enable-tty1-autologin`)

```bash
sudo HOSAKA_DIRECTORY="$HOME/code/Hosaka" \
  ./scripts/install_hosaka_display.sh \
    --profile display-kiosk \
    --renderer chromium \
    --enable-tty1-autologin
```

---

## Soft-coded paths

Hard rule from the hardening packet: **no `/home/<user>` paths are ever
baked into a checked-in file.** Everything is resolved from one of:

| variable           | precedence | meaning                                              |
|--------------------|------------|------------------------------------------------------|
| `HOSAKA_DIRECTORY` | 1 (highest)| Operator-facing alias for the repo root              |
| `HOSAKA_REPO`      | 2          | Legacy alias, still honored                          |
| `/etc/hosaka/repo_root` | 3     | Persisted by `scripts/install_hosaka.sh`             |
| script-relative    | 4          | Used when running the CLI from a working tree        |

All four must resolve to an **absolute path** or the `hosaka` CLI bails
with a clear repair hint:

```
HOSAKA_REPO must be absolute (got: home/fsc/code/Hosaka)
Repair:  export HOSAKA_DIRECTORY="$HOME/code/Hosaka"
         hosaka paths    # confirm the new value
```

That validation is what prevents the `home/fsc/code/Hosaka` typo (missing
leading slash) from ever silently corrupting a deploy.

---

## Picoclaw v2 secrets

Picoclaw v2 enforces a strict split between **structure** and **secrets**:

| file                          | what it holds                              | format |
|-------------------------------|--------------------------------------------|--------|
| `~/.picoclaw/config.json`     | model_list, routing, agents.defaults, tools | JSON   |
| `~/.picoclaw/.security.yml`   | provider credentials, 0600                  | YAML   |

Effective resolution order is:

1. environment variables (e.g. `OPENAI_API_KEY`)
2. `.security.yml` (overlay)
3. `config.json` (legacy / structural)

`.security.yml` is an **overlay**, not a standalone config. It only carries
sensitive fields, and it relies on the model entries declared in
`config.json`.

### What goes where

`config.json` (credential-free):

```json
{
  "agents": { "defaults": { "model_name": "gpt-4.1-mini" } },
  "model_list": [
    {
      "model_name": "gpt-4.1-mini",
      "model": "openai/gpt-4.1-mini",
      "api_base": "https://api.openai.com/v1"
    }
  ]
}
```

`.security.yml` (0600):

```yaml
model_list:
  gpt-4.1-mini:
    api_keys:
      - sk-...
```

Putting `api_key` into `config.json` makes Picoclaw v2 refuse the whole
file with:

```
config.json contains unknown field(s): model_list[0].api_key
```

…which is what kept knocking the Hosaka frontend offline on the field
device. The Hosaka TUI (`hosaka/main_console.py:_check_api_key`) and
`scripts/configure-picoclaw.sh` both strip legacy `api_key` fields out of
`config.json` and write the credential to `.security.yml` instead.

---

## X / Chromium kiosk boot

Three things made the wall stable on the Pi:

1. **`Xwrapper.config` widened to `allowed_users=anybody`.** Without this,
   `hosaka-startx` (which is autologin-launched, not a real console user)
   gets rejected with `Xorg.wrap: only console users are allowed to run the
   X server`. Only written by the `display-kiosk` profile.
2. **`exec tail -f /dev/null` as the X session anchor.** Previous setups
   used `exec xterm` — closing the shell killed the wall. The current
   `dotfiles/xinitrc` backgrounds openbox, xterm, and `hosaka-wall` and
   anchors the session with a `tail -f /dev/null` keepalive.
3. **`hosaka-wall` verifies backend + X *before* launching Chromium.** It
   also respawns Chromium when it crashes, without touching the X server
   underneath. Logs at `~/.local/state/hosaka-wall.log`.

### Shell escape

The kernel always gives you Ctrl+Alt+F2 → real getty, Ctrl+Alt+F1 → back
to GUI. That path is independent of the X session and survives any wall
failure.

---

## Tailscale / remote inference

The appliance ships with Tailscale enabled by default
(`INSTALL_TAILSCALE=1` in `scripts/install_hosaka.sh`). The roadmap
documented in `docs/deployment_updates.yaml:tailscale_remote_inference_plan`
is to add a provider switch:

- `openai` — direct to OpenAI (current default)
- `ollama_local` — local Ollama instance on the device
- `ollama_tailscale` — Jetson Ollama over Tailscale (`HOSAKA_OLLAMA_BASE_URL`)
- `openai_compatible_custom` — any OpenAI-compatible endpoint

`PICOCLAW_MODEL` is the active model alias; provider routing lives in
`config.json`'s `model_list`. Credentials per-provider live in
`.security.yml` (`model_list.<model_name>.api_keys`).

---

## Troubleshooting

For machine-readable known failures, see
[`docs/install-troubleshooting.yaml`](install-troubleshooting.yaml).

### `picoclaw_bin: false` in backend health

The systemd webserver did not inherit `PATH` / `PICOCLAW_BIN` from the
SSH shell. Fix: re-run `scripts/install_hosaka.sh` so `/etc/hosaka/env`
is regenerated with the detected `PICOCLAW_BIN`, then
`sudo systemctl restart hosaka-webserver`.

### `config.json contains unknown field(s): model_list[0].api_key`

Legacy migration. Run `hosaka configure picoclaw` or `hosaka picoclaw
doctor` — the script strips the field and writes the credential to
`.security.yml`. Then `picoclaw status` should be clean.

### Missing X server / `$DISPLAY`

`hosaka display doctor` will walk through DISPLAY, XAUTHORITY,
`xdpyinfo`, the Xorg process, `/tmp/.X0-lock`, `/etc/X11/Xwrapper.config`,
and the DRM cards under `/sys/class/drm`. On a Pi appliance this is
almost always one of: `Xwrapper.config` not widened, autologin not
configured, or HDMI/DSI not connected at boot.

### Electron SIGTRAP on Pi

Known. Stay with `HOSAKA_KIOSK_RENDERER=chromium`. The `hosaka-wall`
supervisor refuses to be a no-op only when chromium is the renderer —
Electron is supported via `kiosk-electron.sh` but never made mandatory.

### Closing xterm kills the GUI

You're on the old `exec xterm` xinitrc. Replace `~/.xinitrc` with
`dotfiles/xinitrc` from this repo (or re-run
`scripts/install_hosaka_display.sh --profile display-kiosk`).

### Relay / wake / sleep

Backend's heartbeat to `picoclaw-gateway.service` is what keeps the
relay from sleeping. If you see picoclaw idle out, check the service:
`hosaka logs picoclaw-gateway`.

---

## Making SD card images

After a known-good install:

```bash
sudo systemctl stop hosaka-webserver picoclaw-gateway
sudo cloud-init clean --logs    # if the image will be re-flashed
# unmount /boot/firmware and / and dd to image
```

Be careful: secrets in `~/.picoclaw/.security.yml` and `~/.hosaka/secrets.json`
are device-bound. Strip them before imaging unless you're shipping a
single-customer device.

---

## Seed USB provisioning

`hosaka seed scan` looks for a `hosaka-seed/` directory under `/media`,
`/mnt`, or `/run/media`. `hosaka seed import <path>` consumes it:

```
hosaka-seed/
  manifest.yaml
  secrets/
    picoclaw.security.yml   → ~/.picoclaw/.security.yml  (chmod 0600)
    hosaka.secrets.json     → ~/.hosaka/secrets.json     (chmod 0600)
  config/
    hosaka.env              → /etc/hosaka/env
```

The importer is idempotent (writes
`~/.local/state/hosaka-seed-imported.json` as a marker) and never prints
secret values.
