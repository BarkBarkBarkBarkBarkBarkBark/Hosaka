# 06.04 · boot modes

The Pi has **906 MiB of RAM** (on a 3B+). With Chromium kiosk +
uvicorn + picoclaw + the SSH session loaded, there is no headroom
left for `npm run build`. So Hosaka has two operating modes you can
flip between, and a couple of more exotic ones.

---

## the two main modes

### `console` (a.k.a. `kiosk`) — the default

What's running:

- `hosaka-webserver.service` — yes
- `picoclaw-gateway.service` — yes
- Xorg + openbox + Chromium kiosk — yes
- TTY dashboard — no

Best for: normal operator use. The touchscreen shows the SPA. The
plant is happy.

```bash
hosaka mode console               # one-shot
hosaka mode console --persist     # survives reboot
hosakactl mode console --persist -y   # from your laptop
```

### `device` (a.k.a. `build`) — for SSH and headroom

What's running:

- `hosaka-webserver.service` — yes (still serving on `:8421`)
- `picoclaw-gateway.service` — **no**
- Xorg + Chromium kiosk — **no**
- TTY dashboard — **yes** (on tty1, with hotkeys)

Best for:

- SSH sessions where you want RAM to spare
- `npm run build` (frees ~600 MiB)
- anything OOM-sensitive
- diagnosing the appliance with the kiosk out of the way

```bash
hosaka mode device                # one-shot
hosaka mode device --persist      # survives reboot
hosakactl mode device --persist -y    # from your laptop
```

---

## persistence — `--persist`

By default, mode changes are **one-shot**: the next reboot returns to
whatever's in `/var/lib/hosaka/mode` (default `console`).

`--persist` writes the marker file `/boot/firmware/hosaka-build-mode`
so the Pi stays in device mode across reboots until you flip back
with `hosaka mode console --persist`.

This matters for headless installs where you might reboot mid-build.

---

## fully kill the webserver — `--full`

Rare. Stops the webserver too.

```bash
hosaka mode device --full
```

You'll lose the API while you're in this state. Useful only for
kernel-level work.

---

## switching mode, every which way

| You're at… | Use |
|---|---|
| the touchscreen | tap the **mode** card on the SPA's `ModeSwitch` button |
| an SSH session on the Pi | `hosaka mode device --persist` |
| your laptop | `hosakactl mode device --persist -y` |
| the TTY dashboard (in device mode) | press `c` to switch back to console |
| your phone | open `http://hosaka.local:8421/device` and click "switch to console mode" |
| a script | `curl -X POST -H "Authorization: Bearer $TOKEN" -d '{"mode":"device","persist":true}' http://hosaka.local:8421/api/v1/mode` |

All paths converge on the `/api/v1/mode` endpoint. There's only one
source of truth; the buttons are just sugar.

---

## boot modes for the python launcher (HOSAKA_BOOT_MODE)

There's a secondary axis: how the **launcher** decides what to start.
Set in `/opt/hosaka/.env`:

| `HOSAKA_BOOT_MODE` | What it does |
|---|---|
| `console` (default) | webserver + picoclaw + (if display) kiosk + TUI on tty |
| `headless` | webserver + picoclaw, no TUI, no kiosk (pure server) |
| `web` | webserver "primary"; no TUI; web is the only surface |
| `kiosk` | same as `console` but skips the TUI on tty (touchscreen only) |

Most people leave this at the default. The mode-switcher above is for
day-to-day ops; this is for "is this Pi ever going to have a screen?"

---

## why is this so elaborate?

Because the Pi is small, the build is large, and the kiosk needs to
stay out of the way when an operator is over SSH. Splitting the modes
gives you a clean way to free ~700 MiB on demand without breaking the
appliance.

> _signal steady._

---

## common mode recipes

```bash
# I want to deploy from SSH without OOM-killing the build
hosaka mode device
cd ~/Hosaka && git pull && hosaka deploy
hosaka mode console

# I'm leaving the appliance somewhere headless for a week
hosaka mode device --persist

# I'm coming back home and want the kiosk back
hosaka mode console --persist

# something's wrong with the kiosk and I want to investigate
hosaka mode device      # one-shot, will revert on reboot
hosaka logs web
sudo systemctl restart hosaka-webserver.service
```

---

## next

- [05 · the device page](05-the-device-page.md) — the `/device` web UI you reach from your phone
- [06 · wifi](06-wifi.md) — adding a network from anywhere
