# 05.02 · opening the channel

> _the channel is off. behind it: **picoclaw** — an agent_
> _that walks a sandboxed workspace and answers in full thoughts._
> _type **/agent on** to bring it back._

When the hosted terminal first opens, the channel to the picoclaw
agent is **closed**. You can use `/help`, `/plant`, `/ask`, and any
other slash command. But free-form text and `!shell` commands need
the channel to be open.

There are two ways to open it.

---

## method 1 — the magic word

The frontend ships with a **magic word** baked into the build (in the
`VITE_HOSAKA_MAGIC_WORD` env var). The default is `neuro`. Your
operator may have changed it.

Type the word at the prompt and press enter:

```
hosaka:/operator › neuro
```

You will see something like:

```
// the word was spoken
authorizing
passphrase accepted
connecting
agent channel open

you are now speaking with picoclaw
— an agentic framework
with a sandboxed workspace it can
walk, read, write, and probe

things to try:
  list the files in your workspace
  make a tiny haiku in haiku.txt
  what tools do you have?

it answers slowly — agents think before they speak.

to close the channel, type /agent off
```

From now on, free-form text routes to picoclaw and `!cmd` runs in the
sandboxed shell.

> The magic word and the **`HOSAKA_ACCESS_TOKEN`** on the Fly.io agent
> server **must match**. They are the same word, on two sides of a door.

---

## method 2 — `/agent on`

If you already know the URL of an agent and the passphrase, you can
configure it from the terminal:

```
/agent url wss://agent.hosaka.app/ws/agent
/agent passphrase neuro
/agent on
```

To check the configuration:

```
/agent status
```

You'll see something like:

```
agent mode: on
url:        wss://agent.hosaka.app/ws/agent
passphrase: ********
```

To ping it:

```
/agent test
```

To turn it off:

```
/agent off
```

---

## what changes when the channel is open

| Before | After |
|---|---|
| Free text → "channel is off" copy | Free text → picoclaw response |
| `!ls` → "channel is off — type /agent on first" | `!ls` → real `ls` output from the sandbox |
| `/netscan` → fake tcpdump-style traffic only | `/netscan` → fake feed _interleaved_ with real `ss` output tagged `[REAL]` |
| Plant ticks only on commands | Plant ticks on commands; agent thoughts tick too |

The channel is **per-tab** and lives in `localStorage`. Closing the
tab keeps your config; closing the channel doesn't drop it.

---

## what picoclaw can do

The agent has a sandboxed workspace (a `chroot`-like jail under the
agent server's working directory) with the following tools:

- **walk** the directory tree
- **read** any file in the sandbox
- **write** new files in the sandbox
- **run** shell commands (filtered through `shlex.split` + a denylist)
- **probe** the network (limited, for `/netscan`'s `[REAL]` tag)

Each session starts with a pre-seeded workspace containing easter eggs:
notes, lore relics, hidden haiku, and tiny shell scripts in `bin/`.
Try:

```
!ls
!ls bin/
!cat README.md
!bin/orb
```

There's a story in there. The orb is patient.

---

## error messages

The agent rarely shouts. When it can't reach you, it says something
like:

| Message | What's going on |
|---|---|
| `the channel isn't tuned yet. set /agent url or check settings.` | no URL configured |
| `the door didn't recognize the word. try another.` | wrong passphrase |
| `the relay is sleeping. give it a moment and try again.` | Fly.io machine is cold-starting |
| `the signal took too long to come back. try again.` | timeout |
| `too many pings in a short window. breathe, then try again.` | rate limit |
| `still listening to the last thing you said. patience.` | request in flight |
| `the channel blinked. try once more.` | websocket dropped |
| `picoclaw heard you but said nothing. try rephrasing.` | empty response |

The orb does not throw stack traces. The orb is too polite for that.

---

## next

- [03 · the terminal tab](03-terminal.md)
- [09 · command reference](09-command-reference.md)
