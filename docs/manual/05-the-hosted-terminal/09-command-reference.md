# 05.09 · command reference (hosted)

Every command available in the **hosted** Hosaka shell. The appliance
has a superset of these — see [TUI commands](../06-the-appliance/07-tui-commands.md)
for the longer list.

Commands are grouped by category. Anything not here is unknown — and
the unknown handler is friendly:

```
unknown command: /foo
no wrong way — try /commands.
```

(Specials: `/rm` → `bold choice.`  ·  `/sudo` → `glad it didn't work.`)

---

## chat & ai

| Command | Description |
|---|---|
| `/ask <text>` | ask the orb a question (one-shot, via Gemini) |
| `/chat` | alias for `/ask` |
| `/model` | show the current Gemini model |
| `/model <name>` | set the Gemini model (e.g. `/model gemini-2.5-flash`) |
| `/reset` | forget the current conversation; start fresh |

---

## agent

| Command | Description |
|---|---|
| `/agent` | show picoclaw agent status |
| `/agent on` | open the channel — route free text to picoclaw |
| `/agent off` | close the channel — route free text to gemini |
| `/agent url <wss://…>` | set the agent websocket url |
| `/agent passphrase <phrase>` | set the magic word (browser-only) |
| `/agent test` | ping the agent backend |
| `!cmd` | run `cmd` in the picoclaw sandbox shell (e.g. `!ls`) |

---

## reference

| Command | Description |
|---|---|
| `/help` | quick start guide |
| `/commands` | this list |
| `/about` | what is this thing |
| `/docs` | link to the original field terminal repo |
| `/lore` | fragments from before the cascade |

---

## reading

| Command | Description |
|---|---|
| `/read` | list library fragments |
| `/read <slug>` | open a fragment in the reading tab (e.g. `/read the-cascade`) |
| `/read order` | the kindle relay (coming soon) |

---

## open loops

| Command | Description |
|---|---|
| `/todo` | open the open loops panel |
| `/todo add <text>` | add a loop from the terminal |
| `/todo list` | list open loops in-terminal |

---

## panels

| Command | Description |
|---|---|
| `/terminal` | switch to the terminal tab |
| `/messages` | hint: open the messages tab |

---

## system

| Command | Description |
|---|---|
| `/status` | hosted-mode status (host, mode, signal, plant, orb, clock) |
| `/signal` | confirm persistence (`Signal steady. Persistence confirmed.`) |
| `/clear` | wipe the screen |
| `/settings` | open the settings drawer |
| `/exit` | `there's nowhere to exit to. you're already here.` |

---

## tools

| Command | Description |
|---|---|
| `/plant` | check the alien plant; see its current state |
| `/orb` | the orb sees you (random art + caption) |
| `/echo <text>` | say something back at yourself |
| `/netscan` | theatrical + real network scanner |

`/netscan` is the most fun. With the agent channel **off** it streams
fake `tcpdump`-style traffic (rehearsal mode). With the channel **on**
it interleaves real `ss` output tagged `[REAL]`.

To stop it: `/netscan` again, or any other input.

---

## the unknown

Type anything that isn't a command and isn't the magic word:

- if the agent is **on**, it routes to picoclaw
- if the agent is **off**, you get the `channel is off` copy

Type the **magic word** (default `neuro`) and the channel opens.

---

## quick recipes

| You want to… | Try |
|---|---|
| see the alien plant | `/plant` |
| get a one-shot LLM answer | `/ask explain the long quiet` |
| open a story | `/read sables-last-transmission` |
| jot a reminder | `/todo add re-tune the relay` |
| run a real `ls` | `neuro` then `!ls` |
| change the LLM model | `/model gemini-2.5-flash` |
| check the agent connection | `/agent test` |
| reset everything | `/reset`, `/clear`, refresh tab |

> _no wrong way._
