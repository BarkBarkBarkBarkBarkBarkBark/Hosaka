# 07 · the laptop client (`hosakactl`)

> _stdlib only. no install. works on Mac, Linux, and the Pi itself._

`hosakactl` is the operator's remote control. A single Python file
(stdlib only — no `pip install`, no venv) that talks to a Hosaka
appliance's `/api/v1/*` endpoints and gives you a clean CLI for
status, mode toggles, wifi, and unit restarts.

```bash
hosakactl link http://hosaka.local:8421
hosakactl status
hosakactl test
hosakactl mode device --persist -y
hosakactl wifi add "Cafe Free WiFi"
hosakactl restart hosaka-webserver.service
hosakactl open
```

---

## what's in this chapter

| # | doc | what's in it |
|---|---|---|
| 01 | [install + link](01-install-and-link.md) | get the binary, link to your Pi |
| 02 | [command reference](02-command-reference.md) | every flag of every command |
| 03 | [troubleshooting](03-troubleshooting.md) | what fails, how to fix it |

---

## why a separate client at all?

Three reasons:

1. **No SSH for routine ops.** Mode toggles, wifi adds, status checks,
   service restarts — all of that should be one command, not a
   five-step shell session.
2. **Scriptable.** `hosakactl test` is one process exit code; perfect
   for a CI smoke check or a cron line.
3. **Stdlib only.** It runs on whatever Python a fresh laptop has,
   no virtualenv, no `pip install`. Drop the file in `/usr/local/bin/`
   and you're done.

---

## the auth model, in one paragraph

The appliance trusts loopback (`127.0.0.1`) absolutely. From the LAN,
**reads** are open and **writes** require a bearer token. The token
lives at `/etc/hosaka/api-token` on the Pi. `hosakactl link` asks for
it once; subsequent commands read it from `~/.hosaka/client.json`
(mode `0600`).

You can override per-call with env vars:

```bash
HOSAKA_HOST=http://hosaka.local:8421 \
HOSAKA_TOKEN=$(cat /etc/hosaka/api-token) \
  hosakactl status
```

---

## quickstart

```bash
# install (one of)
sudo cp hosaka_console/Hosaka/scripts/hosakactl /usr/local/bin/
sudo chmod +x /usr/local/bin/hosakactl

curl -fsSL https://raw.githubusercontent.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl && sudo chmod +x /usr/local/bin/hosakactl

# link
hosakactl link http://hosaka.local:8421     # paste token

# play
hosakactl status
hosakactl wifi list
hosakactl mode device --persist -y
hosakactl test
```

→ Continue with [01 · install + link](01-install-and-link.md).
