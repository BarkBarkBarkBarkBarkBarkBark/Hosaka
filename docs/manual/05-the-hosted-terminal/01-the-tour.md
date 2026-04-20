# 05.01 · the tour

A guided walk around the hosted terminal screen, from top to bottom.

```
┌──────────────────────────────────────────────────────────────────┐
│  ▓▒ HOSAKA ▒▓   [ EN ] [signal steady ●] [plant: stable ❀] [⚙] │   ← header
├──────────────────────────────────────────────────────────────────┤
│  [ Terminal ] [ Reading ] [ Open Loops ] [ Video ]               │   ← dock
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   * \ _ /                                                        │
│    @( )@   plant: stable                                         │
│   */\|/\*  (your alien header)                                   │
│                                                                  │
│   hosaka:/operator › _                                           │   ← prompt
│                                                                  │
│   (your terminal output)                                         │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│   :: signal steady ::                                            │   ← footer
└──────────────────────────────────────────────────────────────────┘
```

---

## the header

Left to right:

### the title block

`▓▒ HOSAKA ▒▓` — the brand mark. Tiny. On purpose.

### the language picker `[ EN ]`

Hosaka speaks six languages out of the box (English, German, Spanish,
French, Italian, Portuguese — plus operator-friendly variants). All
strings are pulled from `frontend/public/locales/<lang>/*.json`. Pick
one; the UI swaps live without a refresh.

### the signal badge `[ signal steady ● ]`

Three states:

- `... waking the orb ...` — the SPA is booting / hydrating.
- `signal steady` — everything is fine. Default.
- `signal faint` — something is intermittent (rare).

The dot color matches the state. It's a glance-check, not a metric.

### the plant badge `[ plant: stable ❀ ]`

Shows the **current vitality** of your plant: `dead`, `wilted`, `dry`,
`stable`, `growing`, `bloom`, or `colony`.

The hosted plant is _ephemeral_ — it lives in the page lifetime and
advances one tick per submitted command. The appliance plant persists
to disk at `~/.hosaka/plant.json`. (See [the plant](../09-lore/03-the-plant.md).)

### the mode switch (appliance only)

On a Pi, you'll also see a **mode switch** here that flips the
appliance between `console` (kiosk) and `device` (TTY dashboard) modes.
On the hosted version this is hidden because there's nothing to switch.

### the settings cog `[ ⚙ ]`

Visible only when `VITE_SHOW_SETTINGS=1` is set at build time. Opens
the [settings drawer](08-settings.md).

---

## the dock

The four tabs:

| Tab | What it is | When to use |
|---|---|---|
| **Terminal** | The xterm.js + Hosaka shell | the default; almost everything happens here |
| **Reading** | Library of lore vignettes, rendered as markdown | `/read`, leisure, immersion |
| **Open Loops** | A persistent todo panel | `/todo add …`, then forget about it |
| **Video** | A loop (TikTok / YouTube short / mp4) | ambient. mostly for the appliance kiosk. |

> The **Messages** panel exists in code but is not in the dock by
> default. It can be summoned via the `hosaka:open-tab` event. See
> [messages](06-messages.md).

---

## the body

By default, the **Terminal** is showing.

Above the prompt, the plant header renders the current plant ASCII
art with its name, so you can see your alien mood without leaving the
keyboard.

Below the plant header, you have the prompt:

```
hosaka:/operator › _
```

This is the **Hosaka shell** — a simulated REPL that exists entirely
in your browser. It dispatches commands itself, and only reaches out
to the network when you specifically invoke `/ask`, the agent, or
`!` shell passthrough.

---

## the footer

```
:: signal steady ::
```

Just a vibe-check. It says `signal steady` until something stops being
steady, at which point the manual is happy to lie to you on its behalf.

---

## what next

- Learn how to talk to the agent → [opening the channel](02-opening-the-channel.md)
- See every command available → [command reference](09-command-reference.md)
- Walk through each panel:
  - [terminal](03-terminal.md) · [reading](04-reading.md) · [open loops](05-open-loops.md) · [messages](06-messages.md) · [video](07-video.md)
