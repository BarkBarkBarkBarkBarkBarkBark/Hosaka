# 07.02 · command reference

Every `hosakactl` command, in one place.

---

## `hosakactl link <url> [--token <t>] [--no-token]`

One-time setup. Stores `{ host, token }` in `~/.hosaka/client.json`
(mode `0600`).

```bash
hosakactl link http://hosaka.local:8421                # prompts for token
hosakactl link http://hosaka.local:8421 --token "$T"   # one-shot
hosakactl link http://localhost:8421 --no-token        # docker / loopback
```

---

## `hosakactl status`

Full snapshot:

```
HOSAKA · status
  hostname: hosaka
  ip:       192.168.1.224
  ssid:     SignalLattice
  uptime:   00:42:11
  ram:      free 412 MiB / 906 MiB
  cpu:      4% load
  mode:     console (persisted: yes)
  services:
    hosaka-webserver       ● running
    picoclaw-gateway       ● running
    hosaka-mode            ○ exited
    hosaka-device-dashboard ○ inactive
  urls:
    spa:    http://hosaka.local:8421/
    device: http://hosaka.local:8421/device
```

---

## `hosakactl mode [console|device] [--persist] [-y]`

Switch operating mode (see [boot modes](../06-the-appliance/04-boot-modes.md)).

```bash
hosakactl mode                                 # print current mode
hosakactl mode device                          # one-shot
hosakactl mode device --persist                # survives reboot
hosakactl mode console --persist -y            # no confirm prompt
```

---

## `hosakactl wifi <list|add|forget>`

```bash
hosakactl wifi list                            # saved + visible
hosakactl wifi add "Cafe Free WiFi"            # prompts for password
hosakactl wifi add "Hidden SSID" --hidden
hosakactl wifi forget "Old SSID"
```

Add will fail with 403 if you have no token from a LAN address.

---

## `hosakactl services`

List the systemd units `hosakactl` knows about and their state.

```bash
hosakactl services
```

Whitelisted units (the only ones you can `restart`):

- `hosaka-webserver.service`
- `picoclaw-gateway.service`
- `hosaka-mode.service`
- `hosaka-device-dashboard.service`

---

## `hosakactl restart <unit>`

Restart a unit (must be in the whitelist above):

```bash
hosakactl restart hosaka-webserver.service
hosakactl restart picoclaw-gateway.service
```

---

## `hosakactl test`

Smoke-test every endpoint. Exits 0 on full green, 1 on any failure.
Perfect for cron / CI / pre-deploy.

```bash
hosakactl test
# ✓ /api/v1/health
# ✓ /api/v1/system/info
# ✓ /api/v1/mode (read)
# ✓ /api/v1/wifi (read)
# ✓ /api/v1/services
# ✓ auth boundary: write rejected without token
# ALL GREEN
```

The local workspace ships a deeper version too:

```bash
bash ~/Cursor_Folder/Cursor_Codespace/local_workspace/scripts/hosaka_smoke.sh
```

…which mirrors `hosakactl test` plus auth-boundary checks and legacy
appliance helpers.

---

## `hosakactl open`

Opens `http://<host>/device` in your default browser. Same as visiting
the page manually; just less typing.

---

## `hosakactl --help`

Shows the full command list with flags.

---

## env vars `hosakactl` cares about

| Var | Default | What it does |
|---|---|---|
| `HOSAKA_HOST` | from `~/.hosaka/client.json` | override the host per call |
| `HOSAKA_TOKEN` | from `~/.hosaka/client.json` | override the token per call |
| `HOSAKACTL_CONFIG` | `~/.hosaka/client.json` | use a different config file |

---

## examples that get a lot of mileage

```bash
# I just want to see if the Pi is alive
hosakactl status

# I want to free RAM and ssh in to deploy
hosakactl mode device --persist -y
ssh operator@hosaka.local
# … do work …
exit
hosakactl mode console --persist -y

# I'm at a new cafe
hosakactl wifi add "Cafe Free WiFi"

# I want to restart the webserver remotely
hosakactl restart hosaka-webserver.service

# I want to verify everything's fine after a deploy
hosakactl test
```

---

## next

- [03 · troubleshooting](03-troubleshooting.md)
