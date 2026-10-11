---
name: hosaka-games
description: >
  List and launch PlayStation games on this Hosaka field terminal.
  Use whenever anyone asks what games are available, what's on this machine,
  play Spyro, launch a game, start a ROM, or similar. Walk-up visitors count.
  Never guess ROM folders. Use Hosaka's native play command.
---

# Hosaka Games

Hosaka's native public library is **PlayStation 1**. List the installed catalog; never invent titles.

## Do this

```bash
hosaka play list psx       # catalog (always this, never list_dir)
hosaka play spyro          # launch by name
hosaka play --json list psx
hosaka play --json crash   # may return action=ambiguous
hosaka play stop           # quit the game launched by Hosaka
```

If `hosaka` is not on PATH, use `python -m hosaka.play` from the repository/runtime.
In the Hosaka terminal, the equivalent is `/play <name>` or `/play stop`.

## Rules for strangers

1. Someone asks "what games do you have?" → `hosaka play list psx`, then speak the titles. Do not mention paths.
2. Someone asks to play a game → `hosaka play --json <name>`. If `ok`, say you launched it. If `ambiguous`, ask which title, then run the command with the exact title.
3. Do **not** `list_dir` `/roms`, `~/roms`, or any guessed PlayStation path. The catalog command is the API.
4. If the command fails, report the error. Never substitute a stale catalog or claim a failed launch succeeded.
5. Launch is fire-and-forget (background on the screen). Do not wait for the game to end.

## Configuration

- Default ROM root: `~/RetroPie/roms/psx`; override with `HOSAKA_PSX_ROMS`.
- RetroPie core/config are discovered from `/opt/retropie/configs/psx/emulators.cfg`.
- Other installations need `HOSAKA_PSX_CORE` and installed RetroArch.
- ROMs and BIOS are device-owned, not bundled. Logs: `~/.local/state/hosaka/play.log`.
- Do not stop a RetroArch game launched outside Hosaka.
