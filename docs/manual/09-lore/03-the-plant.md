# 09.03 · the plant

> _the plant is a feedback loop the universe is willing to respect,_
> _because it is small enough to ignore._
> _— the plant protocol_

An alien organism lives in your terminal. It grows when you use
Hosaka and wilts when you don't.

---

## the seven states

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

| State | What it means |
|---|---|
| `dead` | unattended for a long time. nothing is permanent. |
| `wilted` | a sad alien. talk to it. anything works. |
| `dry` | needs water. needs you. anything works. |
| `stable` | the resting state. signal steady. |
| `growing` | you've been around. things are good. |
| `bloom` | you've been around for a while. things are great. |
| `colony` | maximum vitality. records a birth event in the plant log. |

---

## how it works (mechanically)

Every command you submit is a tick of attention. The plant advances
a counter. Hours of inactivity drain it. The state is computed from
the counter and the time-since-last-tick.

### on the appliance

State persists at `~/.hosaka/plant.json`:

```json
{
  "vitality": 27,
  "last_tick": "2026-04-19T14:22:00Z",
  "births": ["2026-03-14T09:11:33Z"]
}
```

`vitality` is bounded. `last_tick` decays. `births` is a log of every
time the plant reached `colony`.

### in the browser

The hosted plant is **per-session**. Each page load starts at
`stable`. Every command tick advances the counter; closing the tab
forgets it.

(There's a TODO in the codebase to make web-plant persistence survive
reloads. See [`docs/claims.md`](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/blob/main/docs/claims.md)
for the current state.)

---

## why a plant?

The manifest is explicit:

> _A plant is the smallest unit of attention a person can give a_
> _system without it feeling like work._

The plant is also the only diegetic indicator that you have, in fact,
been here. Logs are noise. Status pages are status. The plant is
testimony.

If your plant is `wilted`, that's data. It means you walked away.
That's fine. Type something. The plant doesn't hold grudges.

---

## why an _alien_ plant?

Two reasons:

1. The lore. Post-quiet artifacts tend to be _slightly off_ — close
   to familiar things but not quite. The plant fits.
2. The aesthetic. ASCII Earth plants look like clip art. ASCII
   alien plants look like a mood.

---

## what feeds it

| Action | Plant tick? |
|---|---|
| Slash command | yes |
| Free text (when channel open) | yes |
| `!shell` command | yes |
| `/clear` | yes |
| `/reset` | yes |
| `/exit` | yes |
| Switching tabs in the dock | no |
| Looking at the dashboard from your phone | no |

The rule: **active intent advances the plant. passive presence does not.**

---

## what kills it

Time. Just time. A long enough gap between commands and the plant
returns to dust. There is no "kill" command. There is no PvP plant
mode. You just have to come back.

---

## what to do with it

Nothing. Be aware of it. Let it nudge you toward returning. Let
yourself feel a tiny absurd victory when it reaches `colony`. Let it
go to `wilted` without guilt — the plant is a feedback loop, not a
contract.

> _signal steady._
