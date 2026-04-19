# `hosakactl` — laptop client

Single Python file. **Stdlib only.** Tested on Python 3.9+. Lives in the
repo at [`scripts/hosakactl`](https://github.com/example/Hosaka/blob/main/scripts/hosakactl).

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl
chmod +x /usr/local/bin/hosakactl
```

## Commands

```text
hosakactl link <url> [--token T]      save host + token in ~/.hosaka/client.json
hosakactl status                      one-shot snapshot
hosakactl mode [console|device]       get / set operating mode
                  --persist           survive reboots
                  -y / --yes          skip confirm
hosakactl wifi list                   saved + visible networks
hosakactl wifi add <ssid> [--psk]     join a network (prompts for psk)
hosakactl wifi forget <ssid>          delete a saved network
hosakactl services                    list known systemd units
hosakactl restart <unit>              restart a unit (whitelisted set only)
hosakactl test                        smoke-test every endpoint
hosakactl open                        open /device in your browser
```

Config lives in `~/.hosaka/client.json`. You can also point at a different
host with the `HOSAKA_HOST` and `HOSAKA_TOKEN` env vars.

## Why a single-file client?

* Zero install pain on a fresh laptop — `curl` and you're done.
* Stdlib only ⇒ same script works on macOS, every Linux distro, the Pi
  itself, and (mostly) Termux.
* Easy to audit: every request is a `urllib.request.Request` against a
  documented `/api/v1/*` URL.
* Same wire contract as the kiosk SPA, the `/device` page, and the TTY
  hotkey — so debugging one debugs all of them.

## Wifi from the road

Three equivalent paths to add a network. Pick whichever you have nearby:

=== "Laptop"

    ```bash
    hosakactl wifi add "Cafe Free WiFi"
    # prompts for password
    ```

=== "Phone (any browser)"

    Open `http://<pi-ip>:8421/device` and use the *wifi — add network* form.

=== "TTY (the Pi itself)"

    On the touchscreen in device mode, press `w` and follow the prompts.
