# 06.06 · wifi

There are four ways to add a wifi network to the appliance. Pick the
one that matches whatever device you have in your hand.

---

## 1 — from the kiosk touchscreen

If you're standing in front of the Pi:

1. Tap the **Terminal** tab (default).
2. Tap the prompt.
3. Type:

   ```
   /netscan
   ```

   …to confirm the radio is alive.
4. From the touchscreen, the simplest path is to switch to the
   `/device` page in the Chromium kiosk, then use the wifi-add form:

   - Tap the URL bar (or `Ctrl-L` if you've got a keyboard).
   - Go to `http://localhost:8421/device`.
   - Fill SSID + password, tap **add network**.

Loopback is trusted; no token prompt.

---

## 2 — from your phone (the `/device` page)

Open a browser:

```
http://hosaka.local:8421/device
```

(Use `arp -a` to find the Pi if `.local` doesn't resolve.)

- Scroll to **wifi — add network**.
- Enter SSID + password.
- Tap **add network**.

If it's your first POST to the appliance from this device, you'll be
asked for the bearer token. Get it via SSH:

```bash
ssh operator@hosaka.local "sudo cat /etc/hosaka/api-token"
```

Paste it. The browser caches it.

---

## 3 — from your laptop (`hosakactl`)

The cleanest path for an operator with a Mac.

```bash
hosakactl wifi list                         # saved + visible networks
hosakactl wifi add "Cafe Free WiFi"         # prompts for password
hosakactl wifi forget "Old SSID"
```

If you haven't linked yet:

```bash
hosakactl link http://hosaka.local:8421
# paste token when prompted
```

---

## 4 — from the TTY (device mode hotkey)

If the appliance is in **device mode** (kiosk off, TTY dashboard up),
you have keyboard hotkeys directly on the dashboard. Press:

```
w
```

…and you'll be walked through SSID + password right on tty1. This
shells out to `nmcli` under the hood; on non-NetworkManager images
this won't work.

---

## also: raw nmcli (always works on Raspberry Pi OS)

```bash
nmcli device wifi list
sudo nmcli device wifi connect "SSID" password "secret"
```

This is the lowest-level path. The dashboard, the API, and `hosakactl`
all eventually call this. If `nmcli` works but the others don't, the
issue is upstream (token, API, etc.).

---

## auth, summarized

| Source of POST | Reads | Writes (e.g. wifi add) |
|---|---|---|
| `127.0.0.1` (loopback, on the Pi) | ✓ always | ✓ always |
| LAN with bearer token | ✓ | ✓ |
| LAN without bearer token | ✓ | ✗ 403 |

The token lives at `/etc/hosaka/api-token` (mode `640`, group `hosaka`).

---

## hidden SSIDs, enterprise wifi, captive portals

- **Hidden SSID**: not supported by the dashboard / API. Use `nmcli`
  over SSH:
  ```bash
  sudo nmcli device wifi connect "MyHiddenSSID" password "..." hidden yes
  ```
- **Enterprise (WPA-EAP)**: same, via `nmcli connection add` with the
  full set of EAP options.
- **Captive portal**: connect to the SSID, then load any HTTP page in
  the kiosk's Chromium and complete the portal flow. No special
  support; just a normal browser.

---

## ap mode (aspirational)

The docs hint at a future "AP mode" for first-boot onboarding (so you
can configure wifi without already having wifi). It's not in the
current build. For now, ethernet is the recommended first-boot path.

---

## next

- [07 · TUI commands](07-tui-commands.md)
