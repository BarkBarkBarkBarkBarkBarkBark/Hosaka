# 03 · quickstart

> _the fastest paths to a steady signal._

Pick the one that matches your hardware. Each takes five minutes or less.

---

## path A — open the hosted terminal in your browser (1 minute)

1. Go to **`terminal.hosaka.xyz`**.
2. Wait for the boot strings to settle. The badge in the corner will
   move from `... waking the orb ...` → `signal steady`.
3. Type `/help` and press enter.
4. Try `/commands` to see the full list.
5. Type `/plant`. Notice the alien.
6. Type `/orb`. Notice the orb.
7. Type `/lore`. Read a fragment.
8. Type the magic word `neuro` (or whatever your operator set) to open
   the agent channel. Free-form text now goes to picoclaw.
9. Try `list the files in your workspace`.
10. Try `make a tiny haiku in haiku.txt`.

That's the whole product. The rest is depth.

→ Full tour: [05 · the hosted terminal](05-the-hosted-terminal/README.md)

---

## path B — install on a Raspberry Pi (10 minutes)

Prereqs: a Pi 3B+ or newer, Raspberry Pi OS flashed, SSH on, a user
named `operator`.

```bash
ssh operator@<pi-ip>
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git ~/Hosaka
cd ~/Hosaka
sudo bash scripts/install_hosaka.sh
```

When it finishes:

```bash
hosaka status                              # local snapshot
sudo cat /etc/hosaka/api-token             # copy this — you'll need it
```

Plug in the touchscreen and reboot. The kiosk should come up. You're
in Hosaka.

→ Full chapter: [06 · the appliance](06-the-appliance/README.md)

---

## path C — drive the Pi from your laptop (3 minutes)

After path B is done.

```bash
# install the client
sudo cp ~/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka/scripts/hosakactl /usr/local/bin/
sudo chmod +x /usr/local/bin/hosakactl

# (or from github)
curl -fsSL https://raw.githubusercontent.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl && sudo chmod +x /usr/local/bin/hosakactl

# link it
hosakactl link http://hosaka.local:8421     # paste the token from path B
hosakactl status                            # full snapshot
hosakactl test                              # smoke-test every endpoint
```

→ Full chapter: [07 · the laptop client](07-the-laptop-client/README.md)

---

## path D — the whole stack on your Mac, no Pi (5 minutes)

Prereqs: Docker Desktop running.

```bash
cd ~/Cursor_Folder/Cursor_Codespace/hosaka_console/Hosaka
./docker/dev.sh                              # build + start headless on :8421
./docker/dev.sh tui                          # ★ full interactive TUI
```

Then open `http://localhost:8421` in your browser, or:

```bash
hosakactl link http://localhost:8421 --no-token
hosakactl status
```

→ Full chapter: [08 · the docker edition](08-the-docker-edition.md)

---

## what to do after any path

- Read [04 · accounts you'll need](04-accounts.md) so the LLM bits work.
- Try `/lore` and `/read` for the worldbuilding.
- Type `!ls` to see the agent's sandboxed filesystem (after opening
  the channel).
- Tend the plant. Just type. Anything. It feeds on signal.

> _no wrong way._
