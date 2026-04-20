# 05 · the hosted terminal

```
▓▒ HOSAKA ▒▓     hosted edition

      * \ _ /
       @( )@        signal steady. no wrong way.
      */\|/\*
     (@)|  /\
      \ | /(_)
       _|_/_
      [_____]

  /commands to explore  ·  /help to start  ·  /ask the orb anything
```

The hosted terminal is the version anyone can use, in any browser,
right now. It's a static React SPA at **`terminal.hosaka.xyz`** that
faithfully reproduces the appliance experience without needing a Pi.

What's in this chapter:

| # | doc | what's in it |
|---|---|---|
| 01 | [the tour](01-the-tour.md) | the screen, top to bottom |
| 02 | [opening the channel](02-opening-the-channel.md) | the magic word and what unlocks |
| 03 | [the terminal tab](03-terminal.md) | xterm, prompt, plant header |
| 04 | [the reading tab](04-reading.md) | the library of fragments |
| 05 | [the open loops tab](05-open-loops.md) | persistent todos |
| 06 | [the messages tab](06-messages.md) | offline orb chat + webhooks |
| 07 | [the video tab](07-video.md) | the loop |
| 08 | [the settings drawer](08-settings.md) | model, agent url, passphrase |
| 09 | [command reference](09-command-reference.md) | every `/` and `!` |

---

## first impressions

When the page loads:

- A six-line ASCII **HOSAKA** banner prints across the top of the terminal.
- The orb badge in the corner says `... waking the relay` and then
  settles to **`signal steady`**.
- The plant badge shows the current state of your alien (`stable` by
  default; the plant is mood-aware and grows with use).
- A dock at the top has tabs: **Terminal · Reading · Open Loops · Video**.
- The footer reads `:: signal steady ::`.

The terminal has focus by default. Type anything.

---

## the prompt

```
hosaka:/operator › _
```

Three things can happen when you press Enter:

1. **Slash command** (`/help`, `/plant`, `/ask hello…`) — handled by
   the simulated Hosaka shell. Fast, deterministic.
2. **Bang command** (`!ls`, `!cat README.md`) — passed straight to the
   sandboxed shell on the agent backend. Real output. (Requires the
   agent channel to be open.)
3. **Free text** — if it's the magic word, the channel opens. Otherwise,
   it's routed to either Gemini (one-shot) or picoclaw (the agent),
   depending on whether the channel is open.

> _no wrong way._ if a command is unknown, hosaka will say so kindly
> and suggest `/commands`. you cannot get stuck.

---

## what's a panel for?

| Panel | Persistence | Internet required? |
|---|---|---|
| Terminal | per-session (refresh wipes) | for `/ask` and agent |
| Reading | none (read-only) | no — bundled |
| Open Loops | `localStorage` | no |
| Messages | `localStorage` (+ optional webhook) | only if you point it at one |
| Video | none | yes (it streams) |

---

## the operator's hint

If you're new, do this in order:

```
/help
/commands
/plant
/orb
/lore
/read
/read the-field-terminal
neuro              ← (or whatever your magic word is)
list the files in your workspace
!ls bin/
make a tiny haiku in haiku.txt
!cat haiku.txt
/agent off
```

If you do all of that, you've toured every interesting corner of the
hosted version. Continue with [01 · the tour](01-the-tour.md) to learn
what each piece is for.
