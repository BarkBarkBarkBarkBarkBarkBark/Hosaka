# 05.03 · the terminal tab

The terminal is the main thing. Everything else in Hosaka exists to
support what happens here.

```
hosaka:/operator › _
```

---

## anatomy

It's an `xterm.js` terminal wired to a custom REPL called `HosakaShell`.
The shell:

- prints the **HOSAKA banner** on boot
- renders the **plant header** above the prompt
- routes input through three dispatchers: slash, bang, and free-text
- never crashes or shows a stack trace; every error is in-character

Touch, mouse, and keyboard are first-class. On phones the chrome
shrinks; the prompt always stays focused when you tap the panel.

---

## the three input modes

### 1. slash commands `/foo`

Handled entirely in the browser. Fast, deterministic, offline.

```
/help        # quick start
/commands    # the full list
/plant       # check the alien
/orb         # the orb sees you
/lore        # fragments from before the cascade
/status      # hosted-mode status
/clear       # wipe the screen
```

See the full reference: [09 · command reference](09-command-reference.md).

### 2. bang commands `!cmd`

Passed through to the picoclaw sandbox shell. Real `bash`, real output,
real (sandboxed) filesystem.

```
!ls
!cat README.md
!ls bin/
!bin/orb
!find . -name '*.txt'
```

Requires the agent channel to be open. If it's not, you get:

```
channel is off — type /agent on first.
```

### 3. free-form text

Just type words.

- If the words match the **magic word**, the agent channel opens.
  ([opening the channel](02-opening-the-channel.md))
- If the agent channel is **on**, your text goes to picoclaw.
- If the agent channel is **off**, you get a polite reminder of how to
  open it. (`/ask` is also available for one-shot Gemini questions.)

---

## the prompt as conversation

Once the channel is open, the terminal is essentially a chat with an
agent that has hands. You can:

- **ask** it questions in natural language
- **command** it with bangs (`!ls`, `!cat …`)
- **mix** the two in the same session

```
hosaka:/operator › list the files in your workspace
... picoclaw walks the directory ...
README.md  bin/  notes/  haiku.txt

hosaka:/operator › !cat notes/the-orb.md
the orb is patient.
the orb does not need credentials.
it has always been here.

hosaka:/operator › write a haiku about the orb to haiku.txt
[ orb watches in the dark / the channel is open now / signal steady ]
written.
```

---

## the plant header

Above every prompt is a frame of plant ASCII art and the current state.
It updates every command.

```
  * \ _ /
   @( )@   plant: stable
  */\|/\*
 (@)|  /\
  \ | /(_)
```

The hosted plant is **per-session**: refresh the page and it resets.
The appliance plant is **persistent** at `~/.hosaka/plant.json`.

> Tend it. Type things. The plant blooms when used.

---

## the boot banner

On first paint:

```
██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗
██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗
███████║██║   ██║███████╗███████║█████╔╝ ███████║
██╔══██║██║   ██║╚════██║██╔══██║██╔═██╗ ██╔══██║
██║  ██║╚██████╔╝███████║██║  ██║██║  ██╗██║  ██║
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

Field Terminal Online.       hosted edition
Signal steady.

/commands to explore  ·  /help to start  ·  /ask the orb anything

channel is open — just type and picoclaw will answer.
(or, on the hosted build: type the magic word.)
```

---

## error handling, in-character

Hosaka **never** shows you raw stack traces, HTTP codes, or API key
names. Every failure is rephrased.

| Real cause | What you see |
|---|---|
| Gemini rate limit | `the channel is crowded. breathe. try again in a moment.` |
| Vercel edge proxy down | `the orb is quiet. the relay is resting.` |
| Empty Gemini response | `the orb heard you but had nothing to say. try again.` |
| Unknown error | `signal faint. try again in a moment.` |

The same convention applies to picoclaw — see
[opening the channel](02-opening-the-channel.md#error-messages).

---

## fun things to try

```
/echo signal steady
/draw cathedral of crystal
/lore
/orb
/orb
/orb
/plant
/netscan
/ask what is the long quiet?
```

---

> _no wrong way._ next: [the reading tab](04-reading.md).
