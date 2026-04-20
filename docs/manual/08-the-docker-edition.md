# 08 · the docker edition

> _the same Python package the Pi runs, in a container on your Mac._

If you don't have a Pi (or you want to hack on the backend without
risking the appliance), the Docker dev loop gives you the full
appliance experience on your laptop. Same `:8421`, same `hosakactl`
workflow, same banner.

```
hosaka:/operator › _
```

---

## prerequisites

- **Docker Desktop** running (`open -a Docker`, wait for the whale).
- The Hosaka repo at `~/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka`.

```bash
docker version --format '{{.Server.Version}}'   # any 24+ is fine
```

---

## the one-command dev loop

```bash
cd ~/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka
./docker/dev.sh                              # build + start headless on :8421
./docker/dev.sh tui                          # ★ full interactive TUI
./docker/dev.sh status                       # container + picoclaw health
./docker/dev.sh logs                         # tail container logs
./docker/dev.sh shell                        # bash inside the container
./docker/dev.sh test                         # pytest inside the container
./docker/dev.sh stop                         # stop everything
./docker/dev.sh nuke                         # stop + delete volumes (full reset)
./docker/dev.sh export                       # save a shippable image tarball
```

---

## what `up` (the default) gives you

| Port | What |
|---|---|
| `http://localhost:8421` | Hosaka web UI (same SPA the Pi serves) |
| `:18790` (in-container) | picoclaw gateway (agent runtime) |

---

## two services off the same image

`docker/compose.yml` defines two services off the same image:

| service | mode | when to use |
|---|---|---|
| `hosaka` | `HOSAKA_BOOT_MODE=headless` | background; you talk over http on `:8421` |
| `console` | `HOSAKA_BOOT_MODE=console` | foreground TUI in your terminal |

`./docker/dev.sh tui` swaps the headless service out and runs the
console service with `--service-ports` so the same `:8421` is yours.
`Ctrl-C` exits cleanly back to your shell.

---

## point hosakactl at the container

It's just an http server on `:8421` — `hosakactl` doesn't care if it's
a Pi or a container. Loopback is unauthenticated, so no token needed:

```bash
hosakactl link http://localhost:8421 --no-token
hosakactl status
hosakactl test
bash ~/Cursor_Folder/Cursor_Codespace/local_workspace/scripts/hosaka_smoke.sh
```

(re-link to your real Pi later with the token.)

---

## configure your model key

Picoclaw is baked into the image but ships with an empty `api_key`.
Two ways to fill it in:

### option 1 — drop a `.env` next to the compose file (auto-loaded)

```bash
cat > ~/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka/.env <<'EOF'
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
EOF
./docker/dev.sh stop && ./docker/dev.sh up
```

### option 2 — edit picoclaw's config inside the container

```bash
./docker/dev.sh shell
vi /root/.picoclaw/config.json   # set api_key
exit
./docker/dev.sh stop && ./docker/dev.sh up
```

Config persists in the `picoclaw-config` named volume across restarts.
State persists in `hosaka-state`. `./docker/dev.sh nuke` wipes both.

---

## live-edit the source

`docker/compose.yml` bind-mounts the host source over the image's copy:

```
../hosaka   → /opt/hosaka-field-terminal/hosaka
../docs     → /opt/hosaka-field-terminal/docs
../scripts  → /opt/hosaka-field-terminal/scripts
../tests    → /opt/hosaka-field-terminal/tests
```

So any edit on your Mac is visible inside the container immediately.
Restart the service to pick up code changes:

```bash
./docker/dev.sh stop && ./docker/dev.sh up
```

---

## ship the container to a Pi (or anywhere)

```bash
./docker/dev.sh export hosaka:ship hosaka-field-terminal.tar.gz
scp hosaka-field-terminal.tar.gz operator@<pi-ip>:~/
ssh operator@<pi-ip> '
  docker load < hosaka-field-terminal.tar.gz
  docker run -d -p 8421:8421 --name hosaka hosaka:ship
'
```

---

## when something fails

| symptom | fix |
|---|---|
| `Cannot connect to the Docker daemon` | `open -a Docker`, wait for it to settle |
| port `:8421` already in use | `lsof -i :8421` to find the offender |
| picoclaw failures in logs | empty/invalid `api_key` — see "configure your model key" |
| webserver healthcheck flapping | `./docker/dev.sh logs` then `./docker/dev.sh shell` to poke around |
| stale state after big change | `./docker/dev.sh nuke && ./docker/dev.sh up` |

---

## what's _not_ here

- No touchscreen kiosk (no Xorg in the container).
- No `nmcli` (so wifi commands won't do anything useful).
- No persistent journal across `./docker/dev.sh nuke`.

In other words: this is the appliance's _brains_, with the body left
out. Perfect for development, demos, and smoke tests. Not the same as
running on real hardware.

> _continue: [09 · lore](09-lore/README.md)_
