# 09.01 · the no-wrong-way manifest

The original manifest, as it ships in the appliance at
`/opt/hosaka/docs/no_wrong_way_manifest.md`. Reproduced here, with
brief operator-side notes after each section.

---

# NO WRONG WAY // HOSAKA FIELD TERMINAL MANIFEST

> _You can't really break this experience by experimenting._
> _If a command fails, Hosaka should redirect, not punish._

## what this system is

Hosaka Field Terminal is a console-first appliance shell for cyberdeck
operation. It is designed to feel like a dedicated product, not a
generic Linux desktop.

> _operator note: this is the difference between "a Pi running stuff"
> and "a thing." Hosaka is a thing._

### core pillars

1. Terminal-first operator identity.
2. Guided onboarding with resumable state.
3. Local-network setup path for cross-device configuration.
4. Offline-resilient behavior with deterministic fallback help.
5. **"No Wrong Way" interaction model.**

> _operator note: pillar 5 is load-bearing. read it twice._

## how to navigate

At the `hosaka>` prompt, you can:

- run slash commands (`/help`, `/status`, `/manifest`, etc.)
- run shell commands (`ls`, `ip a`, `uptime`, etc.)
- read files with `read <file>`

Examples:

- `read manifest`
- `read README.md`
- `read /var/lib/hosaka/state.json`
- `/status`
- `/network`

## recommended first actions

1. `read /var/lib/hosaka/state.json`
2. `/status`
3. `/network`
4. `read README.md`

## picoclaw agent

Picoclaw is the brains of operation — a lightweight local agent binary.
Everything typed at the `hosaka>` prompt goes straight to Picoclaw.

Flow:

- Picoclaw must be installed and onboarded before first boot
  (`picoclaw onboard`).
- The console routes all free-form input through the Picoclaw
  subprocess adapter.
- `/picoclaw status` and `/picoclaw doctor` for diagnostics.

> _operator note: picoclaw is the only thing in the room that thinks.
> the rest of Hosaka is shape, mood, and reflex._

## failure behavior

When a command fails or is unknown, the system should:

1. Explain what happened.
2. Suggest next best commands.
3. Keep the user in control.

**No dead ends. No wrong way.**

## reader mode

Use `read <file>` to open any text file.

Reader controls:

- `Enter` = next page
- `q` = exit reader early

## operator motto

**NO WRONG WAY**

---

## the operator gloss

The manifest says it. We'll add three sentences:

1. **Errors are in-character.** "the orb is quiet. the relay is
   resting." instead of `502 Bad Gateway`. Stack traces never reach
   the user.
2. **Unknown commands are an opportunity.** `unknown command: /foo —
   no wrong way — try /commands.` Sometimes a joke (`/rm`, `/sudo`).
   Always a hint.
3. **The plant is the user, not the system.** It tells you _you_ have
   been here, not whether the system is healthy. The signal badge is
   for the system.

That's the whole thing. Everything else in the manual is mechanics.

> _read it again, slower:_
>
> _**no wrong way.**_
