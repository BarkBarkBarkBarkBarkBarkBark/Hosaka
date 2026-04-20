# 06.03 · the operator CLI

`hosaka` is a small bash command installed at `/usr/local/bin/hosaka`
on the Pi by the installer. It's the **on-device** counterpart to
`hosakactl` (which runs on your laptop).

```bash
hosaka -h
```

---

## one-line summary of every command

| Command | What it does |
|---|---|
| `hosaka status` | what's running, RAM/CPU snapshot, current mode, urls |
| `hosaka mode` | print the current mode |
| `hosaka mode console [--persist] [--full]` | switch to kiosk mode |
| `hosaka mode device [--persist] [--full]` | switch to TTY dashboard mode |
| `hosaka mode kiosk` | alias for `mode console` (legacy) |
| `hosaka mode build` | alias for `mode device` (legacy) |
| `hosaka dashboard` | print the device dashboard once and exit |
| `hosaka build [--check]` | `cd frontend && npm run build` (with optional `tsc` gate) |
| `hosaka deploy [--check]` | build + rsync into `$HOSAKA_DEPLOY` + restart webserver |
| `hosaka logs [web\|pico\|<unit>]` | tail journalctl for the named unit |
| `hosaka reboot` | safe sync + reboot |

`HOSAKA_DEPLOY` defaults to `/opt/hosaka-field-terminal`.

---

## the two modes, briefly

(See [04 · boot modes](04-boot-modes.md) for the long version.)

### `console` mode (default)

- Xorg + openbox + Chromium kiosk on `:8421`
- picoclaw gateway running
- TTY dashboard off
- the touchscreen kiosk is your interface

### `device` mode

- Kiosk **off**
- picoclaw gateway **off** (frees ~600 MiB RAM)
- TTY dashboard runs on tty1
- web server still serving on `:8421`
- the right mode for `npm run build`, big SSH sessions, OOM-sensitive ops

```bash
hosaka mode device --persist          # survives reboot
# … do your work …
hosaka mode console --persist         # back to kiosk
```

`--full` also stops the webserver (rare; use only for kernel-level work).

---

## the build / deploy workflow

A typical SSH-and-deploy session:

```bash
ssh operator@hosaka.local
hosaka mode device                     # frees RAM
cd ~/Hosaka
git pull
hosaka deploy                          # build + rsync + restart
hosaka mode console                    # back to the kiosk
```

`hosaka build [--check]` does just the build. Add `--check` to gate
on `tsc` (off by default to halve the build's RAM peak).

`hosaka deploy [--check]` does build + rsync + `systemctl restart
hosaka-webserver.service`. The check is the same `tsc` gate.

---

## tailing logs

```bash
hosaka logs              # webserver (default)
hosaka logs web          # alias
hosaka logs pico         # picoclaw-gateway
hosaka logs hosaka-mode  # any unit name
```

Equivalent to `journalctl -u <unit> -f`.

---

## restartability matrix

The whitelisted units (also restartable from `hosakactl`):

| unit | what it does |
|---|---|
| `hosaka-webserver.service` | the FastAPI app on `:8421` |
| `picoclaw-gateway.service` | the agent runtime |
| `hosaka-mode.service` | runs once at boot, sets mode |
| `hosaka-device-dashboard.service` | the TTY dashboard in device mode |

```bash
sudo systemctl restart hosaka-webserver.service
```

Or, from your laptop:

```bash
hosakactl restart hosaka-webserver.service
```

---

## hosaka vs hosakactl

A common confusion. Here's the table:

| Client | Runs on | Best for |
|---|---|---|
| `hosaka` | the Pi (over SSH) | mode toggles, deploys, OOM-sensitive ops |
| `hosakactl` | your Mac / laptop | day-to-day status, wifi, restarts, scripting |

Both eventually call the same `/api/v1/*` endpoints. `hosaka` also
does direct systemd/build operations that don't go through the API.

---

> _continue: [04 · boot modes](04-boot-modes.md)_
