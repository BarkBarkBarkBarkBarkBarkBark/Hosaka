# Modes — console & device

Hosaka boots in one of two modes. They are mutually exclusive and the runtime
state lives in `/var/lib/hosaka/mode`. A persistent boot marker at
`/boot/firmware/hosaka-build-mode` (yes, the path is legacy — left so we don't
break older installs) makes a mode survive reboots.

## console (default)

What runs:

- `hosaka-webserver.service` — FastAPI + SPA on `:8421`
- `picoclaw-gateway.service` — local LLM gateway (~14% CPU at idle)
- `Xorg` + `openbox` + `chromium --kiosk http://127.0.0.1:8421` on `tty1`

Use this when the operator is interacting with the touchscreen.

## device

What runs:

- `hosaka-webserver.service` — still up so `hosakactl` and `/device` work
- `hosaka-device-dashboard.service` on `tty1` — live dashboard, no X
- **stopped:** chromium kiosk, openbox autostart, picoclaw-gateway

Why: on a Pi 3B with 1 GB RAM, the chromium kiosk + picoclaw together leave
~150 MB free. Doing an `npm run build` over SSH in that state OOM-kills the
build (or, worse, the SSH session itself). Device mode frees ~600 MB.

It's also the right mode for *configuring* the box from a laptop — the
`/device` page and `hosakactl` can do everything you'd otherwise SSH for.

## Switching modes

| Where | How |
|---|---|
| Pi (SSH) | `hosaka mode device --persist` |
| Pi (touchscreen) | header → button labelled *switch to device* → confirm |
| Pi (TTY in device mode) | press `c` |
| Laptop | `hosakactl mode device --persist -y` |
| Phone | open `/device` → *switch to console mode* button |

`--persist` writes the boot marker so the mode survives a reboot. Without it
the change is one-shot.

## Legacy aliases

For backward compatibility the CLI still accepts the old names:

| New | Old |
|---|---|
| `console` | `kiosk` |
| `device` | `build` |

The runtime mode file may contain either spelling — readers normalise on read.
