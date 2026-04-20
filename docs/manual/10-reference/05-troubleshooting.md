# 10.05 · troubleshooting

The master fix table. If you can't find it here, see the per-chapter
troubleshooting in [hosakactl](../07-the-laptop-client/03-troubleshooting.md)
or [docker](../08-the-docker-edition.md#when-something-fails).

---

## the hosted terminal

| Symptom | Likely cause | Fix |
|---|---|---|
| Page won't load | Vercel deployment is down or the cdn is grumpy | reload; if persistent, check Vercel dashboard |
| `/ask` returns "the orb is quiet. the relay is resting." | Vercel Edge function down or `GEMINI_API_KEY` missing | check Vercel env vars; redeploy |
| Magic word doesn't open the channel | Fly.io agent down, or `HOSAKA_ACCESS_TOKEN ≠ VITE_HOSAKA_MAGIC_WORD` | `fly status -a hosaka-field-terminal-alpha`; verify both env vars |
| `/agent test` says "the door didn't recognize the word." | passphrase mismatch | `/agent passphrase <word>`; or rebuild SPA with right `VITE_HOSAKA_MAGIC_WORD` |
| `/agent test` says "the relay is sleeping." | Fly machine cold-starting | wait ~10 s, retry |
| `!cmd` returns "channel is off" | agent channel not opened | type the magic word, or `/agent on` |
| Free text gets "channel is off" | agent channel not opened | same as above |
| `/netscan` only shows fake traffic | agent channel off (rehearsal mode) | open the channel |
| Plant always says `stable` | hosted plant is per-session | refresh = reset; this is by design (for now) |

---

## the appliance

| Symptom | Likely cause | Fix |
|---|---|---|
| Kiosk doesn't come up | display not detected, or Xorg fail | `hosaka logs` (kiosk unit); reboot once; check HDMI |
| `:8421` not reachable from LAN | webserver bound to loopback | set `HOSAKA_WEB_HOST=0.0.0.0` in `/opt/hosaka/.env`, restart unit |
| `/api/v1/wifi` POST returns 403 | LAN write without token | use `hosakactl wifi add` (it sends the token); or paste token into `/device` form |
| `wifi list` empty | not on a NetworkManager image | only NetworkManager-based images supported; switch image or use `wpa_supplicant` directly |
| `npm run build` OOM-killed | Pi is in `console` mode and out of RAM | `hosaka mode device`, then build, then `hosaka mode console` |
| picoclaw says "no model configured" | `~/.picoclaw/config.json` empty / no key | edit config, set `api_key`, restart `picoclaw-gateway.service` |
| `/doctor` flags missing key | env not loaded by webserver unit | check `EnvironmentFile` in the unit, restart |
| Pi reboot loops | failed mode service | boot in recovery, remove `/boot/firmware/hosaka-build-mode`, reboot |
| `hosaka` command not found | installer never ran | `cd ~/Hosaka && sudo bash scripts/install_hosaka.sh` |

---

## hosakactl

| Symptom | Likely cause | Fix |
|---|---|---|
| `No route to host` (`hosaka.local`) | macOS picked the IPv6 record | use the IPv4 from `arp -a` |
| `Connection refused` on `:8421` | webserver down | `ssh in; sudo systemctl restart hosaka-webserver.service` |
| `401` / `403` on writes | token stale | re-`hosakactl link …`, paste fresh token |
| `404` on `/api/v1/...` | Pi on old build | git pull on Pi; rerun installer |
| `wifi list` errors | `nmcli` missing | only NetworkManager-based images supported |
| ssh works, no token file | installer never ran | run `scripts/install_hosaka.sh` |
| `command not found: hosakactl` | not on PATH | check `/usr/local/bin/hosakactl` exists + executable |
| `python: bad interpreter` | python 2 default | call `python3 hosakactl …` or fix shebang |

---

## docker

| Symptom | Likely cause | Fix |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop not running | `open -a Docker`, wait for the whale |
| `:8421` already in use | something else bound to it | `lsof -i :8421` to find / kill |
| picoclaw failures in logs | empty `api_key` | drop `.env` next to compose; restart |
| webserver healthcheck flapping | container under-resourced | bump Docker resource limits; or just restart |
| stale state | named volumes still around | `./docker/dev.sh nuke && ./docker/dev.sh up` |

---

## vercel + fly.io (operator-side)

| Symptom | Likely cause | Fix |
|---|---|---|
| Vercel build fails on Hosaka frontend | sync-console didn't run | check `vercel.json` runs `bash scripts/sync-console.sh` before `npm ci` |
| `/api/gemini` returns 500 | env var missing | verify `GEMINI_API_KEY` is set in Vercel project |
| `wss://agent.hosaka.app/ws/agent` 401 | `HOSAKA_ACCESS_TOKEN` mismatch | reset both `fly secrets set HOSAKA_ACCESS_TOKEN=<word>` and SPA's `VITE_HOSAKA_MAGIC_WORD=<word>`, redeploy |
| Fly app cold-starts every request | scale-to-zero with no warm machine | `fly scale count 1 --max-per-region 1` |
| CORS preflight fails | `HOSAKA_ALLOWED_ORIGINS` doesn't include the SPA origin | `fly secrets set HOSAKA_ALLOWED_ORIGINS='https://terminal.hosaka.xyz'` |

---

## the universal first move

Before any of the above:

```bash
hosakactl status
hosakactl test
```

If those are green, the system is alive and the issue is somewhere
specific. If they're red, the table above will narrow it down fast.

---

## the universal last move

```bash
hosaka reboot
```

If that doesn't fix it, re-flash. The system is reproducible from the
installer; you'll lose the bearer token but `hosakactl link` makes
that a 30-second recovery.

> _no wrong way._
