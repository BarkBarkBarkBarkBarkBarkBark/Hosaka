# 06.02 · first boot

The Pi comes up. The screen flickers. Then this happens.

---

## what you see, in order

1. **Pi splash + console scroll** — kernel boot, services starting.
2. **Hosaka mode service runs** — reads `/var/lib/hosaka/mode` (or the
   boot marker `/boot/firmware/hosaka-build-mode`) and decides whether
   to come up in **console** mode (kiosk) or **device** mode (TTY).
3. **If console mode (default):**
   - Xorg starts, openbox launches, Chromium opens fullscreen on
     `http://localhost:8421`.
   - The HOSAKA banner prints. The plant appears. The signal settles
     to steady.
4. **If device mode:**
   - You stay on tty1.
   - The `hosaka-device-dashboard` service prints a live snapshot:
     IP, SSID, services, URLs, recent log lines.
   - The bottom of the screen shows hotkeys: `c` to switch to console
     mode, `w` to add wifi, etc.

In both cases, `hosaka-webserver.service` and `picoclaw-gateway.service`
are running in the background.

---

## verify it from the inside

SSH in. Run:

```bash
hosaka status
```

You should see something like:

```
HOSAKA · status
  hostname: hosaka
  ip:       192.168.1.224
  uptime:   00:04:13
  ram:      free 412 MiB / total 906 MiB
  mode:     console (persisted: yes)
  services:
    hosaka-webserver.service     active (running)
    picoclaw-gateway.service     active (running)
    hosaka-mode.service          active (exited)
    hosaka-device-dashboard.service  inactive (dead)
  urls:
    spa:    http://hosaka.local:8421/
    device: http://hosaka.local:8421/device
```

If the webserver is _not_ running:

```bash
sudo systemctl status hosaka-webserver.service
sudo journalctl -u hosaka-webserver.service -e
```

Most "didn't come up" issues are `nmcli` missing on a non-NetworkManager
image, or the kiosk failing to find a display. Both have explicit
journal entries.

---

## verify it from the outside

From your laptop:

```bash
curl -fsS http://hosaka.local:8421/api/v1/system/info | jq .
```

Should return JSON with `hostname`, `ip`, `mode`, etc.

```bash
curl -fsS http://hosaka.local:8421/api/v1/health | jq .
```

Should return `{"ok": true, "checks": {...}}`.

The `/api/v1/health` payload also tells you whether your `OPENAI_API_KEY`
or `GEMINI_API_KEY` is reachable, which is the next thing to fix.

---

## verify it from your hand

Open a browser on your phone. Go to `http://hosaka.local:8421/`. The
SPA should load. The dock should show **Terminal · Reading · Open Loops · Video**.
The terminal should print the banner. Try `/help`.

Then `http://hosaka.local:8421/device`. You should see the **device
dashboard**: network, system, services, and a small wifi-add form.
(See [05 · the device page](05-the-device-page.md).)

---

## the plant, on first boot

The appliance plant lives at `~/.hosaka/plant.json`. On first boot,
it's seeded as `stable`. It will:

- **Tick up** every time you submit a command.
- **Tick down** after hours of inactivity.
- **Reach `colony`** if you really stick around — at which point it
  records a "birth" event in the plant log.

Don't be surprised if it's `wilted` after a long weekend. The plant
is honest about what it knows.

→ [the plant lore](../09-lore/03-the-plant.md)

---

## what to do next

| If you want to… | Go to |
|---|---|
| Configure a Gemini / OpenAI key | [accounts](../04-accounts.md) |
| Drive it from your laptop | [hosakactl](../07-the-laptop-client/README.md) |
| Add wifi from your phone | [wifi](06-wifi.md) |
| Free up RAM for `npm run build` | [boot modes → device mode](04-boot-modes.md) |
| See every TUI command | [TUI commands](07-tui-commands.md) |

> _signal steady._
