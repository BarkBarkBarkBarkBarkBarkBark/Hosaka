# 07.03 · troubleshooting

Most failures fall into a small handful of buckets. Here's the table
that covers ~95% of them.

| Symptom | Likely cause | Fix |
|---|---|---|
| `No route to host` (with `hosaka.local`) | macOS picked the IPv6 record | Use the IPv4 from `arp -a` |
| `Connection refused` on `:8421` | webserver unit down on Pi | `ssh operator@hosaka.local "sudo systemctl restart hosaka-webserver.service"` |
| `:8421` listening on `127.0.0.1` only | bound to loopback | Set `HOSAKA_WEB_HOST=0.0.0.0` in `/opt/hosaka/.env`, restart unit |
| `401` / `403` on writes | token missing / stale | Re-`hosakactl link …` and paste fresh token |
| `404` on `/api/v1/...` | Pi on old build | `ssh in; cd ~/Hosaka && git pull && sudo bash scripts/install_hosaka_lean.sh` |
| `wifi list` empty / errors | `nmcli` not present | only NetworkManager-based images supported |
| ssh works but no token file | installer never ran | run `scripts/install_hosaka.sh` or `install_hosaka_lean.sh` on the Pi |
| `hosakactl: command not found` | not on `$PATH` | check `/usr/local/bin/hosakactl` exists + is executable |
| Python complains about syntax | python 2 default on path | call with `python3 hosakactl ...` or update shebang |

---

## diagnosing it from your laptop

If something's not right, this sequence will tell you which layer is broken:

```bash
# 1. can you reach the host at all?
ping -c 1 hosaka.local

# 2. is :8421 open?
nc -vz hosaka.local 8421

# 3. is the api alive?
curl -fsS http://hosaka.local:8421/api/v1/health | jq .

# 4. is your token good?
HOSAKA_TOKEN=... curl -fsS \
  -H "Authorization: Bearer $HOSAKA_TOKEN" \
  http://hosaka.local:8421/api/v1/system/info | jq .

# 5. does hosakactl agree?
hosakactl status
hosakactl test
```

If 1 fails → network. If 2 fails → webserver down. If 3 fails → API
broken (or non-Hosaka thing on `:8421`). If 4 fails → token is wrong.
If 5 fails but 4 succeeds → `hosakactl` config is stale; re-link.

---

## diagnosing it from the Pi

```bash
ssh operator@hosaka.local

# what's running?
hosaka status
sudo systemctl status hosaka-webserver.service
sudo systemctl status picoclaw-gateway.service

# what's listening?
sudo ss -tlnp | grep 8421

# what's in the logs?
hosaka logs web
hosaka logs pico
sudo journalctl -u hosaka-webserver.service -e

# is the token there?
sudo ls -l /etc/hosaka/api-token
sudo cat /etc/hosaka/api-token | head -c 16; echo …
```

---

## "I broke the Pi"

You probably didn't.

```bash
# most things heal with a service restart
sudo systemctl restart hosaka-webserver.service
sudo systemctl restart picoclaw-gateway.service

# stuck? reboot.
hosaka reboot     # safe sync + reboot

# really stuck? re-run the installer (idempotent)
cd ~/Hosaka && git pull && sudo bash scripts/install_hosaka_lean.sh
```

---

## last resort

Re-flash the SD card. The whole appliance is reproducible from the
installer plus your Pi imager settings — and your laptop still has the
token from `hosakactl link`, which was just a sha256 anyway.

> _no wrong way._
