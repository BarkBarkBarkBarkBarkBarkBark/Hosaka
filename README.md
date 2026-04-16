# Hosaka Field Terminal

```
  ██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗
  ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗
  ███████║██║   ██║███████╗███████║█████╔╝ ███████║
  ██╔══██║██║   ██║╚════██║██╔══██║██╔═██╗ ██╔══██║
  ██║  ██║╚██████╔╝███████║██║  ██║██║  ██╗██║  ██║
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

      * \ _ /
       @( )@          A console-first AI field terminal.
      */\|/\*         Signal steady. No wrong way.
     (@)|  /\
      \ | /(_)
       _|_/_
      [_____]
```

An AI-powered appliance shell for cyberdecks and Raspberry Pis.
Type anything — it goes straight to the agent.
Use it enough and the plant blooms. Neglect it and it wilts.

There is no wrong way.

---

## Install

### 1. Install Picoclaw

```bash
cd /tmp
curl -L https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz \
  -o picoclaw.tar.gz
tar -xzf picoclaw.tar.gz && chmod +x picoclaw && sudo mv picoclaw /usr/local/bin/
picoclaw onboard
```

### 2. Clone and run

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-hosaka.txt
picoclaw gateway &
python -m hosaka
```

### 3. Appliance install (Raspberry Pi)

```bash
./scripts/setup_hosaka.sh
```

One command. Installs everything, enables systemd services, starts onboarding.

---

## What you get

```
hosaka:/home/operator > /commands

  ── Chat & AI ──
    /chat              Interactive AI session
    /ask <text>        One-shot question

  ── System ──
    /status            Uptime, IP, model, services
    /doctor            Diagnose config
    /restart all       Restart services
    /update            Pull + redeploy

  ── Network ──
    /net               IP, Wi-Fi, Tailscale
    /ping /dns /scan   Network tools

  ── Tools ──
    /draw <subject>    AI-generated ASCII art
    /plant             Check on your alien plant
    /orb               The orb sees you
    /code              Drop to shell

  ── Reference ──
    /help              Quick start
    /lore              ...
    /about             System info
```

Everything else you type goes to the AI agent. Prefix `!` for shell commands.

---

## The plant

An alien organism lives in your terminal. It grows when you use Hosaka
and wilts when you don't.

```
  dead        wilted       dry        stable      growing      bloom       colony

              ,            \ |         _         \ _ /       * \ _ /     *@* _ *@*
              |\            \|        ( )        -( )-        @( )@      \@(*)@/ *
   .          | )            |        \|/       / \|         */\|/\*    */\\|//\@*
   |          |/             |         |       (_) |/\      (@)|  /\    (@)|  /\(@
   |         _|_           __|__     __|__         |/        \ | /(_)    *\|*/(_)*
  .|.       [___]         [_____]   [_____]      __|__        _|_/_      __|_/__|_
 [___]                                          [_____]      [_____]    [___][__]
```

State persists to `~/.hosaka/plant.json`. Every command feeds it.
Hours of inactivity drain it. Reach colony state and it records a birth.

---

## Docker (no Pi required)

```bash
./docker/dev.sh               # start services
./docker/dev.sh tui            # full interactive terminal
./docker/dev.sh test           # run tests
./docker/dev.sh stop           # shut down
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `HOSAKA_STATE_PATH` | `~/.hosaka/state.json` | Persistent state |
| `HOSAKA_BOOT_MODE` | `console` | `console` or `headless` |
| `HOSAKA_WEB_PORT` | `8421` | LAN setup web server port |
| `PICOCLAW_SESSION` | `hosaka:main` | Agent session key |
| `PICOCLAW_MODEL` | *(default)* | Override model |

---

## Requirements

- Python 3.10+
- Picoclaw v0.2+
- systemd (for appliance boot)
- No desktop environment needed
