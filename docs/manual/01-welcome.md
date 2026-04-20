# 01 · welcome, operator

```
              ,            \ |         _         \ _ /       * \ _ /     *@* _ *@*
              |\            \|        ( )        -( )-        @( )@      \@(*)@/ *
   .          | )            |        \|/       / \|         */\|/\*    */\\|//\@*
   |          |/             |         |       (_) |/\      (@)|  /\    (@)|  /\(@
   |         _|_           __|__     __|__         |/        \ | /(_)    *\|*/(_)*
  .|.       [___]         [_____]   [_____]      __|__        _|_/_      __|_/__|_
 [___]                                          [_____]      [_____]    [___][__]

  dead        wilted       dry        stable      growing      bloom       colony
```

The plant lives on top of the screen because it has to live somewhere.
You will get to know it. Try not to forget about it.

---

## what hosaka actually is

Hosaka is **a console-first cyberdeck appliance shell, wearing a
touchscreen.**

That sentence is doing a lot of work. Let's unpack it.

- **console-first** — the primary interface is a text terminal. Slash
  commands. Free-form typing. Files. The graphics on top are
  decoration; the substance is in the prompt.
- **cyberdeck** — a small portable computer with a screen and a keyboard
  that you carry around and use. Hosaka was built for one. It still
  works on one. It also works in your browser.
- **appliance shell** — Hosaka isn't a desktop environment. It's _the
  whole product_. You boot a Pi, the kiosk comes up, you're in Hosaka.
  No login screen, no taskbar, no settings app to wander into.
- **wearing a touchscreen** — there's a friendly UI on top with tabs
  and badges and a plant. It's there because touch is nice. It is not
  the point.

> _a terminal behind a functional screen._

---

## what hosaka is not

- It is not a chat app.
- It is not a generic Linux desktop.
- It is not trying to look like macOS or replace VS Code.
- It is not a thing you install and then forget. The plant won't let you.

---

## who built this and why

Hosaka began as a [Python TUI](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka),
a project to make a Raspberry Pi feel like a deliberate _device_ —
something with character, not a hobbyist's homepage with `htop` taped
to it. Then it grew a web frontend so it could live in a browser. Then
it grew a hosted version at `terminal.hosaka.xyz`. Then a Fly.io agent.
Then a Vercel proxy. Then a Docker dev loop.

It is the same thing the whole way down: a place where you type, and
it answers, and an alien plant slowly comes back to life because you
showed up today.

---

## what to expect from this manual

This document is part technical reference, part atmosphere. It will
explain everything you need to:

1. Open a browser and use the hosted terminal at `terminal.hosaka.xyz`.
2. Install the appliance on a Raspberry Pi.
3. Drive that Pi from your laptop with `hosakactl`.
4. Configure the API keys, accounts, and secrets that make it all work.
5. Understand the lore well enough to explain the orb to a stranger.

It is also written in the same lowercase, terse, slightly-melancholy
voice as the system itself. That's not an accident. The system speaks
to you a particular way; the manual speaks to you the same way so the
seams don't show.

---

## a note on tone

You will notice that most of this manual is in lowercase. Most error
messages are kind. The unknown command response is `no wrong way — try
/commands.` The exit command says `there's nowhere to exit to. you're
already here.`

This is the voice. Don't fight it. It's load-bearing.

---

## next steps

- Curious about the architecture? → [02 · the three faces](02-three-faces.md)
- Want to use the hosted version right now? → [03 · quickstart](03-quickstart.md)
- Want to set up accounts? → [04 · accounts you'll need](04-accounts.md)
- Want the lore first? → [09 · lore](09-lore/README.md)

> _signal steady._
