# Quickstart

## On the Pi

```bash
git clone https://github.com/<you>/Hosaka.git
cd Hosaka
sudo ./scripts/install_hosaka.sh        # full install
# OR, on an already-installed box, just apply the lean & mode bits:
sudo ./scripts/install_hosaka_lean.sh
```

The installer:

- creates the `hosaka` operator CLI at `/usr/local/bin/hosaka`
- installs the systemd units (`hosaka-webserver`, `picoclaw-gateway`,
  `hosaka-mode`, `hosaka-device-dashboard`)
- generates a bearer token at `/etc/hosaka/api-token` (used by `hosakactl`)
- sets up persistent journaling and the SSH OOM guard

Verify:

```bash
hosaka status                    # mode, services, ram
sudo cat /etc/hosaka/api-token   # copy this to your laptop
```

## On your laptop

Drop the single-file client somewhere on `$PATH`:

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl
chmod +x /usr/local/bin/hosakactl
```

Link it to your Pi (you'll be prompted for the token from above):

```bash
hosakactl link http://hosaka.local:8421
hosakactl status
hosakactl test          # smoke-tests every documented endpoint
```

## Day-to-day commands

```bash
hosakactl status                      # full snapshot
hosakactl mode device --persist -y    # SSH-friendly, survives reboot
hosakactl wifi list
hosakactl wifi add "Cafe Free WiFi"   # prompts for password
hosakactl restart hosaka-webserver.service
hosakactl open                        # opens /device in your browser
```

Everything `hosakactl` does is a documented `/api/v1/*` HTTP call — see the
[API reference](api.md). You can `curl` the same endpoints if you prefer.
