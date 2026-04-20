# 06 · the appliance

> _the real one. the one with the screen and the small whirring fan._

The appliance is Hosaka in its original form: a Raspberry Pi running
the full Python TUI plus the React frontend as a kiosk on a
touchscreen, served from `:8421` on your local network.

```
  ██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗
  ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗
  ███████║██║   ██║███████╗███████║█████╔╝ ███████║
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

      pi 3b+ · 906 MiB ram · one operator · one alien plant
```

---

## what's in this chapter

| # | doc | what's in it |
|---|---|---|
| 01 | [install](01-install.md) | flash, ssh, run the installer |
| 02 | [first boot](02-first-boot.md) | what happens, what to verify |
| 03 | [the operator CLI](03-operator-cli.md) | the local `hosaka` command |
| 04 | [boot modes](04-boot-modes.md) | console / device / kiosk / headless |
| 05 | [the device page](05-the-device-page.md) | the `/device` web UI |
| 06 | [wifi](06-wifi.md) | four ways to add a network |
| 07 | [TUI commands](07-tui-commands.md) | the full python shell command list |

---

## what gets installed

The installer (`scripts/install_hosaka.sh` or the lean variant) puts
together:

| What | Where |
|---|---|
| `hosaka` operator CLI | `/usr/local/bin/hosaka` |
| systemd units | `/etc/systemd/system/hosaka-*.service` |
| Bearer token | `/etc/hosaka/api-token` (group: `hosaka`, mode `640`) |
| Web app | `/opt/hosaka-field-terminal/` (or your `HOSAKA_DEPLOY` dir) |
| State | `/var/lib/hosaka/` (mode marker, plant data on appliance) |
| Boot mode marker | `/boot/firmware/hosaka-build-mode` (when persisted) |

systemd units installed:

- `hosaka-webserver.service` — FastAPI server on `:8421`
- `picoclaw-gateway.service` — the agent runtime (gateway socket on `:18790`)
- `hosaka-mode.service` — runs at boot to set the right mode
- `hosaka-device-dashboard.service` — TTY dashboard on HDMI when the
  kiosk is off

---

## three ways to drive it

| Surface | Best for |
|---|---|
| **Touchscreen kiosk** | day-to-day operator use; typing into the terminal |
| **Web browser on the LAN** | quick checks from any device; the `/device` page |
| **`hosakactl` on a laptop** | scripting, status, mode toggles, wifi from anywhere |

---

## the philosophy of an appliance

Hosaka's appliance design is intentionally _appliance-like_:

- one URL (`http://<pi-ip>:8421`)
- one operator user (`operator`, by convention)
- one persistent token at `/etc/hosaka/api-token`
- one alien plant at `~/.hosaka/plant.json`
- one set of systemd services; restartable individually
- one switch (`hosaka mode …`) for the two operating modes

It's not a server you log into; it's a thing you turn on. The kiosk
comes up. The plant appears. The signal is steady. Type.

> Continue with [01 · install](01-install.md).
