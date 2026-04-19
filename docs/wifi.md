# Wifi setup

Hosaka uses NetworkManager (`nmcli`) on the Pi. There are four equivalent
ways to add or change a network — all of them are thin wrappers over the
same `nmcli device wifi connect` command.

## 1. Phone or laptop browser → `/device`

Best for a stranger's wifi when you only have a phone in your pocket and the
Pi is already on a hotspot or ethernet:

1. Find the Pi's IP (TTY shows it, or `arp -a` for `hosaka.local`).
2. Open `http://<pi-ip>:8421/device` in any browser.
3. Use the *wifi — add network* form.

The page POSTs to `/api/v1/wifi/networks`. No auth needed from the LAN by
default for reads; for the POST you need either loopback or a bearer token.
The first time, the easiest path is to be on the same wifi the Pi is already
on (hotspot from your phone), because then loopback isn't an option.

!!! note "Token from the LAN"
    The installer drops `/etc/hosaka/api-token` (`chmod 0640`,
    group `hosaka`). On the Pi: `sudo cat /etc/hosaka/api-token`. Paste it
    into your laptop with `hosakactl link http://<pi>:8421 --token <T>`.

## 2. Laptop → `hosakactl`

```bash
hosakactl wifi list                       # see what's around
hosakactl wifi add "Cafe Free WiFi"       # prompts for password
hosakactl wifi add "MyHomeNet" --psk hunter2
hosakactl wifi forget "OldHotelLobby"
```

## 3. Pi TTY → press `w`

When the Pi is in device mode and you're in front of the touchscreen with a
keyboard plugged in, press `w` from the dashboard. It scans, prompts for the
SSID + password, and runs `nmcli device wifi connect` for you.

## 4. SSH → `nmcli` (manual)

The lowest-level fallback. All paths above just call:

```bash
nmcli device wifi list --rescan yes
nmcli device wifi connect "<ssid>" password "<psk>"
```

If `nmcli` itself isn't working, fall back to dropping a
`/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` and `systemctl restart
wpa_supplicant@wlan0`. That's outside the scope of this doc.

## Future: AP fallback

If you arrive at a place with no wifi at all and you didn't pre-load a
network, the next step is to make the Pi broadcast its own AP (`hostapd` +
`dnsmasq`) so you can connect to it directly and configure from there.
This is *not* implemented yet — see [the claims audit](claims.md) for the
list of outstanding work.
