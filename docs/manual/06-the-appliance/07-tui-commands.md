# 06.07 · TUI commands

The appliance runs the **full Python TUI** (`python -m hosaka`),
which has a superset of the hosted shell's commands. If you SSH in
and run `hosaka` without arguments, or if you're on tty1 with the TTY
dashboard, this is the universe you have access to.

The hosted commands ([reference](../05-the-hosted-terminal/09-command-reference.md))
all work here too. What follows is the **delta** — commands that exist
on the appliance but not in the browser.

---

## chat & ai

| Command | Description |
|---|---|
| `/chat` | open an interactive AI session (multi-turn) |
| `/ask <text>` | one-shot question |

---

## system

| Command | Description |
|---|---|
| `/status` | uptime, ip, model, services |
| `/doctor` | diagnose config (api keys, picoclaw, services, model) |
| `/picoclaw` | picoclaw subcommands |
| `/picoclaw status` | picoclaw status |
| `/picoclaw doctor` | picoclaw diagnostic |
| `/restart terminal` | restart the TUI |
| `/restart gateway` | restart picoclaw gateway |
| `/restart all` | restart everything |
| `/update` | git pull + redeploy |
| `/uptime` | system uptime |
| `/whoami` | who you are to hosaka |

---

## file system

| Command | Description |
|---|---|
| `/cd <path>` | change directory |
| `/pwd` | print working directory |
| `/ls` | list files |
| `/tree` | print a directory tree |
| `/read <file>` | open a file in the reader (markdown, text) |
| `/library` | list bundled library fragments |

The `read` command is also available _without_ a slash:

```
read manifest
read README.md
read /var/lib/hosaka/state.json
```

Reader controls: `Enter` = next page, `q` = exit.

---

## network

| Command | Description |
|---|---|
| `/net` | ip, wi-fi, tailscale snapshot |
| `/netscan` | full network scan |
| `/ping <host>` | ICMP ping |
| `/traceroute <host>` | hop trace |
| `/ports` | list open local ports |
| `/dns <name>` | DNS lookup |
| `/scan` | shorthand for a quick LAN scan |

---

## tools

| Command | Description |
|---|---|
| `/draw <subject>` | AI-generated ASCII art |
| `/orb` | the orb sees you |
| `/plant` | check on your alien plant |
| `/code` | drop to a real shell (subshell escape) |
| `/history` | command history |
| `/weather` | local weather (uses location heuristics) |
| `/video` | open the video panel on the kiosk |

`!cmd` works the same as on the hosted side: passes through to the
real shell (no sandbox here — you're on the Pi).

---

## reference

| Command | Description |
|---|---|
| `/help` | quick start |
| `/commands` | the full list |
| `/manifest` | the no-wrong-way manifest |
| `/about` | system info |
| `/lore` | random fragments |

---

## open loops

| Command | Description |
|---|---|
| `/todo` | open / show |
| `/todo add <text>` | add |
| `/todo list` | list |
| `/todo done <n>` | mark done |
| `/todo remove <n>` | delete |
| `/todo clear` | wipe |

The appliance todo list lives in `~/.hosaka/state.json` (see
[env vars](../10-reference/01-env-vars.md) for `HOSAKA_STATE_PATH`).
The hosted one lives in `localStorage`.

---

## misc

| Command | Description |
|---|---|
| `/echo <text>` | say something back at yourself |
| `/clear` | wipe the screen |
| `/exit` | "there's nowhere to exit to. you're already here." |

---

## hot keys (in the python TUI)

- `Ctrl-C` — cancel the current command (does **not** exit)
- `Ctrl-D` — same as `/exit` (which doesn't exit, but politely)
- `Ctrl-L` — clear screen
- `↑` / `↓` — history
- `Tab` — completion (commands, paths)

---

## the `read` companion

`read` is its own little command, not a slash command. It opens
anything text-shaped in a paged reader:

```
read manifest                                # alias for read /opt/hosaka/docs/no_wrong_way_manifest.md
read README.md
read /var/lib/hosaka/state.json
read /etc/hosaka/api-token                   # technically; not advised
```

Reader controls:

- `Enter` — next page
- `q` — exit

---

## what runs where

| Command | Hosted | Appliance |
|---|---|---|
| `/help`, `/commands`, `/about` | ✓ | ✓ |
| `/plant`, `/orb`, `/lore` | ✓ | ✓ |
| `/ask`, `/chat`, `/model`, `/reset` | ✓ | ✓ |
| `/agent on/off/url/passphrase/test`, `!cmd` | ✓ (sandbox) | ✓ (host shell) |
| `/read`, `/todo`, `/todo add` | ✓ (panels) | ✓ (terminal) |
| `/status`, `/signal`, `/clear`, `/echo` | ✓ | ✓ |
| `/draw`, `/netscan` | ✓ | ✓ |
| `/doctor`, `/picoclaw …`, `/restart …`, `/update` | ✗ | ✓ |
| `/cd`, `/pwd`, `/ls`, `/tree`, `/library` | ✗ | ✓ |
| `/net`, `/ping`, `/traceroute`, `/ports`, `/dns`, `/scan` | ✗ | ✓ |
| `/manifest`, `/uptime`, `/whoami`, `/weather`, `/history`, `/code` | ✗ | ✓ |

> _no wrong way._
