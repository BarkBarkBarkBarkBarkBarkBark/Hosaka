# 07.01 · install + link

Three steps: get the file, find your Pi, paste the token.

---

## step 1 — install

`hosakactl` is a single Python script. Pick a path:

### from the local checkout (fastest, works offline)

```bash
sudo cp ~/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka/scripts/hosakactl /usr/local/bin/
sudo chmod +x /usr/local/bin/hosakactl
hosakactl --help
```

### from GitHub (works on any laptop, anywhere)

```bash
curl -fsSL https://raw.githubusercontent.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl && sudo chmod +x /usr/local/bin/hosakactl
```

Verify:

```bash
hosakactl --help
# (prints usage + commands)
```

Requires Python 3.9+. macOS already has one. Linux usually does. No
`pip install` needed.

---

## step 2 — find your Pi

The appliance always serves on port `8421`. Resolve the host however
your network supports:

```bash
ping -c 1 hosaka.local                                # mDNS
arp -a | grep -iE 'b8:27:eb|dc:a6:32|d8:3a:dd'        # rpi MAC prefixes
tailscale status | grep -i hosaka                     # tailnet name + 100.x.y.z
```

> **macOS gotcha:** macOS prefers IPv6 on `.local` names. If
> `hosakactl link http://hosaka.local:8421` returns `No route to host`,
> use the explicit IPv4 from `ping`/`arp` instead. The IPv6 record may
> resolve to a stale link-local address.

---

## step 3 — get the bearer token

The installer (`scripts/install_hosaka_lean.sh`) generates this once
with `openssl rand -hex 32` and stores it on the Pi only:

```bash
ssh operator@hosaka.local "sudo cat /etc/hosaka/api-token"
```

It's group-readable by the `hosaka` group. There's no remote
bootstrap — you need ssh or physical access to the Pi to get it the
first time.

---

## step 4 — link

```bash
hosakactl link http://192.168.1.224:8421     # paste token when prompted
hosakactl status                             # full snapshot
hosakactl test                               # smoke-test every endpoint
```

Config persists at `~/.hosaka/client.json` (mode `0600`). Subsequent
commands need no flags.

One-shot link if you already have the token:

```bash
TOKEN=$(ssh operator@hosaka.local "sudo cat /etc/hosaka/api-token")
hosakactl link http://192.168.1.224:8421 --token "$TOKEN"
```

For Docker / loopback (no auth needed):

```bash
hosakactl link http://localhost:8421 --no-token
```

---

## step 5 — verify

```bash
hosakactl status         # mode, ip, ssid, ram, services, urls
hosakactl test           # exits 0 on green, 1 on any failure
hosakactl open           # opens /device in your browser
```

If you see green, you're done. The Pi is now driveable from your
laptop without ever opening another SSH session.

---

## rotating the token

Any time:

```bash
ssh operator@hosaka.local '
  sudo bash -c "openssl rand -hex 32 > /etc/hosaka/api-token && \
                chgrp hosaka /etc/hosaka/api-token && \
                chmod 640 /etc/hosaka/api-token && \
                systemctl restart hosaka-webserver.service"
'
hosakactl link http://192.168.1.224:8421     # re-paste the new token
```

---

## env override

If you'd rather not persist anything:

```bash
HOSAKA_HOST=http://192.168.1.224:8421 \
HOSAKA_TOKEN=$(ssh operator@hosaka.local "sudo cat /etc/hosaka/api-token") \
  hosakactl status
```

You can also point at a separate config file with `HOSAKACTL_CONFIG`.

---

## next

- [02 · command reference](02-command-reference.md)
- [03 · troubleshooting](03-troubleshooting.md)
