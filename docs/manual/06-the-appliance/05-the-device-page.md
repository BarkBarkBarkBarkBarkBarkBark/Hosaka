# 06.05 · the `/device` page

> _hosaka — device mode_

When you don't have the touchscreen handy, `/device` is the appliance's
self-service web dashboard. It runs on the same `:8421` and is reachable
from any device on the LAN.

```
http://hosaka.local:8421/device
```

---

## what it shows

Five cards, auto-refreshing every ~4 seconds from `/api/v1/system/info`:

```
┌──────────────────────────────────────────┐
│  HOSAKA · device mode                    │
├──────────────────────────────────────────┤
│  network                                 │
│    ssid:       SignalLattice             │
│    ip:         192.168.1.224             │
│    gateway:    192.168.1.1               │
├──────────────────────────────────────────┤
│  system                                  │
│    hostname:   hosaka                    │
│    uptime:     00:42:11                  │
│    ram:        free 412 MiB / 906 MiB    │
│    cpu:        4% load                   │
├──────────────────────────────────────────┤
│  services                                │
│    hosaka-webserver       ● running      │
│    picoclaw-gateway       ● running      │
│    hosaka-mode            ○ exited       │
│    hosaka-device-dashboard ○ inactive    │
├──────────────────────────────────────────┤
│  urls                                    │
│    spa:    http://hosaka.local:8421/     │
│    device: http://hosaka.local:8421/device│
├──────────────────────────────────────────┤
│  wifi — add network                      │
│    ssid: [_________________]             │
│    pass: [_________________]             │
│    [ add network ]                       │
├──────────────────────────────────────────┤
│  mode                                    │
│    [ switch to console mode ]            │
└──────────────────────────────────────────┘
```

---

## what it lets you do

### add a wifi network

Type the SSID + password into the form and submit. POSTs to
`/api/v1/wifi` and triggers `nmcli device wifi connect`.

If you're on the LAN _without_ a token, you'll get a 403. See
[wifi](06-wifi.md) for the four ways to add a network and how the
token works.

### switch modes

The **switch to console mode** / **switch to device mode** button
fires a confirmation, then POSTs to `/api/v1/mode` with
`{ "mode": "console", "persist": true }`. You'll see the page reload
in console mode after a few seconds.

### see what's running

The services list is live; if a service goes red, you'll see it
within ~4 seconds. Click into one (in some builds) to see the last
journal lines.

---

## auth

The dashboard is **read-friendly** — anyone on the LAN can load it
and see the snapshot. Writes (wifi add, mode switch, service restart)
require the bearer token.

For the on-device touchscreen this happens automatically (loopback is
trusted). For your phone or laptop on the LAN:

```
Authorization: Bearer $(cat /etc/hosaka/api-token)
```

The dashboard's own forms ask for the token in browser storage on
first use. If you see a 403, copy the token from the Pi:

```bash
ssh operator@hosaka.local "sudo cat /etc/hosaka/api-token"
```

…and paste it into the dashboard's prompt. (Or set up `hosakactl`,
which keeps the token for you.)

---

## use cases

| Scenario | How |
|---|---|
| You forgot the wifi password on a new network | `/device` → wifi add |
| The kiosk is hung; you want to switch modes | `/device` → switch mode |
| Quick health check from your phone | `/device`, glance at the cards |
| Showing someone the appliance | open `/device` on a tablet |

---

## limits

- This page is read-only on the surface. Real config (mode markers,
  systemd unit edits, etc.) requires SSH or `hosakactl`.
- It can't add a hidden SSID. Use `nmcli` over SSH for that.
- It does not expose secrets. Tokens, API keys, and config files are
  not displayed.

---

## next

- [06 · wifi](06-wifi.md) — the four ways
- [07 · TUI commands](07-tui-commands.md) — the python shell command list
