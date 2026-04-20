# 06.01 · install

A Raspberry Pi, a touchscreen, ten minutes.

---

## what you need

| Hardware |
|---|
| Raspberry Pi **3B+ or newer** (4B is comfortable, 5 is luxurious) |
| microSD card, 16 GB or larger |
| Power supply appropriate for your Pi |
| Touchscreen (HDMI + USB touch, or the official Pi screen) — _optional_ |
| Network — wired ethernet for first boot is easiest |

| Software |
|---|
| Raspberry Pi Imager (or `dd`) |
| An SSH client on your laptop |

---

## 1 — flash the OS

Use Raspberry Pi Imager.

1. Open Raspberry Pi Imager.
2. **Choose OS** → Raspberry Pi OS (Lite is fine — Hosaka doesn't need a desktop).
3. **Choose storage** → your microSD.
4. Click the gear ⚙ icon (or `Ctrl-Shift-X`) to set:
   - hostname: `hosaka` (so you can ssh `operator@hosaka.local`)
   - username: **`operator`**
   - password: anything memorable
   - enable SSH (with password or key)
   - configure your wifi (or skip, if using ethernet)
   - set locale + timezone
5. **Write.** Wait for verify.

Eject. Slot the SD into the Pi. Power on.

---

## 2 — first ssh

Give it ~60 seconds to come up. Then:

```bash
ssh operator@hosaka.local
# (or use the IP from your router / `arp -a`)
```

If `hosaka.local` doesn't resolve on macOS:

```bash
ping -c 1 hosaka.local
arp -a | grep -iE 'b8:27:eb|dc:a6:32|d8:3a:dd'
```

(Those MAC prefixes are Raspberry Pi.)

---

## 3 — clone and install

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git ~/Hosaka
cd ~/Hosaka
sudo bash scripts/install_hosaka.sh        # full install (first time)
```

There's also a lighter variant:

```bash
sudo bash scripts/install_hosaka_lean.sh   # lean install (skips heavier extras)
```

Either way, the installer:

- creates the `hosaka` group and adds `operator` to it
- installs systemd units for webserver, picoclaw, mode, dashboard
- writes the bearer token to `/etc/hosaka/api-token`
  (`openssl rand -hex 32`, mode `640`, group `hosaka`)
- installs the operator CLI at `/usr/local/bin/hosaka`
- enables persistent journaling
- installs the SSH OOM guard (so a runaway build doesn't kill your ssh)

It runs unattended; expect a few minutes on a slow SD card.

---

## 4 — install picoclaw

Picoclaw is the agent runtime. It needs to be installed once.

```bash
cd /tmp
curl -L https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz \
  -o picoclaw.tar.gz
tar -xzf picoclaw.tar.gz && chmod +x picoclaw && sudo mv picoclaw /usr/local/bin/
picoclaw onboard
```

Then point it at a model. Open `~/.picoclaw/config.json`:

```json
{
  "model_list": [
    {
      "model_name": "gpt-4o-mini",
      "model": "openai/gpt-4o-mini",
      "api_key": "sk-your-key-here",
      "api_base": "https://api.openai.com/v1"
    }
  ]
}
```

If you skip this, Hosaka will prompt you for the key on first launch.

(Gemini? Use `"model": "gemini/gemini-2.5-flash-lite"` and your `AIza…`
key. See [accounts](../04-accounts.md).)

---

## 5 — verify

```bash
hosaka status                       # uptime, ip, ram, mode, services
sudo cat /etc/hosaka/api-token      # copy this; you'll need it on your laptop
sudo ss -tlnp | grep 8421           # webserver bound on 0.0.0.0:8421
```

If `:8421` is bound and `hosaka status` looks clean, you're done. The
appliance is alive.

---

## 6 — plug in the screen (optional)

If you have a touchscreen:

```bash
sudo reboot
```

When the Pi comes back, the kiosk should auto-launch. Chromium opens
fullscreen on `http://localhost:8421`. The plant header appears. The
signal is steady.

---

## 7 — point your phone at it

Any device on the same network can use the appliance:

```
http://hosaka.local:8421/        ← the SPA
http://hosaka.local:8421/device  ← the device dashboard (wifi, mode, etc.)
```

The first time you POST anything from another device (e.g. add a wifi
network from your phone), it'll need the token. See [the device page](05-the-device-page.md)
for the flow.

---

## next

- [02 · first boot](02-first-boot.md) — what to look at first
- [03 · the operator CLI](03-operator-cli.md) — the `hosaka` command
- [accounts you'll need](../04-accounts.md) — set up your LLM key

> _signal steady._
