---
name: hosaka-games
description: >
  List and launch PlayStation games on this Hosaka field terminal.
  Use whenever anyone asks what games are available, what's on this machine,
  play Spyro, launch a game, start a ROM, or similar. Walk-up visitors count.
  Never guess or list_dir ROM folders — they will fail. Run the play command.
---

# Hosaka Games

This machine's public library is **PlayStation 1**. Other folders are homebrew test ROMs — do not offer them unless asked.

## Do this

```bash
play list psx              # catalog (always this, never list_dir)
play spyro                 # launch by name
play --json list psx       # machine-readable
play --json crash          # launch; may return action=ambiguous
play stop                  # quit the running game
```

Full path if `play` is missing from PATH: `/home/operator/bin/play`

## Rules for strangers

1. Someone asks "what games do you have?" → `play list psx`, then speak the titles. Do not mention paths.
2. Someone asks to play a game → `play --json <name>`. If `ok`, say you launched it. If `ambiguous`, ask which title, then run `play --json` with the exact title.
3. Do **not** `list_dir` `/roms`, `~/roms`, or any guessed PlayStation path. The catalog command is the API.
4. If `play` fails, read `~/.picoclaw/workspace/GAMES.md` and still list titles.
5. Launch is fire-and-forget (background on the screen). Do not wait for the game to end.

## Paths (only if play is broken)

- ROMs: `/home/operator/RetroPie/roms/psx`
- Catalog: `~/.picoclaw/workspace/GAMES.md`
