# Troubleshooting

How to interrogate a misbehaving Hosaka without guessing. Read top to
bottom; each section assumes the previous one returned what it should.

## one-shot snapshot

```bash
hosaka logs dump
```

Prints, in order: runtime mode · deployed bundle hash · systemd unit
status · memory + load · disk · journald usage · webserver journal ·
kiosk journal · picoclaw journal · recent flatpak attempts · health
probe · capabilities probe · git HEAD.

Pipe to a file or paste into chat. This is the canonical "what's going
on right now" command.

## "did my update actually load?"

The frontend bundle is content-hashed, so a new deploy means new
filenames under `/opt/hosaka-field-terminal/hosaka/web/ui/assets/`.
Two ways to confirm:

1. **In the kiosk** — bottom-right of the topbar shows a 7-char build
   sha (e.g. `3f1e423`). Click it to copy the full sha + ISO timestamp.
   This sha is baked at `npm run build` time; if the kiosk is showing a
   sha that doesn't match the one your laptop just built, the kiosk is
   serving a stale bundle.
2. **From SSH** — `cat /opt/hosaka-field-terminal/hosaka/web/ui/build-stamp.json`
   shows what's on disk. Compare against `git -C ~/Hosaka rev-parse --short=10 HEAD`.

If the on-disk stamp matches HEAD but the chip in the kiosk doesn't:
Chromium is caching the SPA. Quick fix:

```bash
sudo systemctl restart hosaka-kiosk.service
```

The kiosk launcher (`scripts/kiosk-electron.sh`) evicts the HTTP cache
on every start. It deliberately keeps V8 Code Cache + GPUCache to avoid
re-parsing the 3.7 MB Automerge chunk on every restart.

## "an app says install failed"

First check arch compatibility:

```bash
flatpak --arch=aarch64 remote-info flathub com.spotify.Client
# error: Can't find ref com.spotify.Client/aarch64
```

If that error appears, the app does not exist for your CPU on Flathub
and never will via this path. Hosaka's registry tags
`spotify`, `steam`, `discord`, `slack` with `flatpakArches: [x86_64]`
so the install button should already say `unavailable` and explain why.
If the app you're trying to install is not in that list, file an issue
with the `flatpak --arch=$(uname -m)` output.

For apps that *should* work (foliate, vscode, firefox, telegram,
betterbird, alienarena), watch the install in real time:

```bash
journalctl -u hosaka-webserver -f | grep -E 'flatpak|install'
```

Or shell out manually to see the full flatpak progress output:

```bash
flatpak --user install -y --noninteractive flathub com.github.johnfactotum.Foliate
```

The `--user` flag matters: hosaka-webserver runs as the same user, so
system-wide installs (`--system`) won't be visible to it.

## "the screen jumps every few seconds"

Two pollers can cause this:

1. `DiagnosticsPanel` (when open) — used to refresh every 8 s; now 30 s
   and only when the panel is the active tab.
2. `hosaka-device-dashboard` — the *device-mode* TTY dashboard, NOT the
   kiosk. Refreshes every 5 s by design. Only visible when you toggle
   to device mode (`hosaka mode device` or the topbar mode switch).

If you still see jumps in the kiosk: confirm the build sha (above);
you're probably on an old bundle.

## "the kiosk feels slow"

Remember the floor: Pi 3B+, 1 GB RAM, SD-card storage, 4-core ARM A53
@ 1.4 GHz. SD random read is ~10–30 MB/s. There is no fixing that in
software. What we *can* do is in `docs/plausible_otimizations.yaml` —
deferred items are ranked by impact / effort / risk for incremental
work.

Quick wins before filing a perf bug:

```bash
hosaka logs dump | grep -E 'mem|pressure|swap'   # under memory pressure?
df -h /                                            # SD card full?
journalctl --disk-usage                            # journald hoarding?
sudo systemctl list-units --state=running | wc -l  # service sprawl?
```

## "polling won't stop"

Find what's polling:

```bash
sudo journalctl -u hosaka-webserver -n 200 --no-pager \
  | awk '/GET/ {print $NF}' | sort | uniq -c | sort -rn | head
```

Top of that list is what's hammering the API. If it's `/api/health`
every ~5 s, that's `hosaka-device-dashboard` (the TTY one). If it's
`/api/v1/diag/*`, the `DiagnosticsPanel` is mounted. If it's
`/api/v1/inbox/*`, an Inbox tab is open.

Polling intervals (post-perf-pass):

| panel              | interval | gated on visible? |
|--------------------|----------|-------------------|
| DiagnosticsPanel   | 30 s     | yes (active tab)  |
| DiagOverlay        | 30 s     | yes (visibility)  |
| DocsPanel          | 30 s     | no                |
| InboxPanel         | 30 s     | yes (active tab)  |
| NodesPanel         | 45 s     | yes (active tab)  |
| PlantBadge         | 4.2 s    | yes (visibility)  |
| device-dashboard   | 5 s      | TTY only          |

## "spotify and steam will never work?"

On a Pi, correct. Both are x86_64-only on Flathub. Workarounds, in
order of effort:

1. Use the spotify *web player* via the `internet` panel.
2. Run hosaka on an x86_64 mini-PC and the apps install normally.
3. (Heroic) Run a qemu-user-static x86_64 layer. Out of scope here.

## the diagnostic methodology in one paragraph

Reproduce → snapshot the Pi (`hosaka logs dump`) → confirm bundle sha
matches HEAD → check the relevant API directly with `curl` (cheap, no
UI in the loop) → check the underlying shell command if `curl` works
(eliminates HTTP layer) → only then change code. The order is chosen
so each step rules out a layer rather than adding a guess.
