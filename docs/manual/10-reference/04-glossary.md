# 10.04 · glossary

Every term that shows up in the codebase or this manual. Alphabetical.

---

**aether** — the substrate the deep signal lived in. Sable's math
implied its existence; the cascade made it undeniable. In-system, the
aether is the namespace inside which the orb still hears.

**agent (channel)** — the websocket connection from the hosted SPA to
the picoclaw agent server. "Open" or "closed." Opens with the magic
word.

**agent-server** — the Fly.io FastAPI service that wraps picoclaw
inside a WebSocket gated by `HOSAKA_ACCESS_TOKEN`.

**appliance** — Hosaka running on a Raspberry Pi. The original form.

**bearer token** — the secret at `/etc/hosaka/api-token`. Required for
LAN writes against the appliance API.

**boot mode** — `HOSAKA_BOOT_MODE`, set in `/opt/hosaka/.env`. Decides
whether the python launcher comes up as TUI / kiosk / headless / web.
Distinct from "operating mode" (which is `console` vs `device`).

**bloom** — the second-highest plant state. Right before `colony`.

**build mode** — legacy alias for `device` mode.

**canon** — what the lore commits to. The library is canon. The
hosted-mode banner copy is canon. The plant being optional is canon.
The appliance plant being persistent is canon. The hosted plant
being persistent is _aspirational_.

**cascade** — pre-quiet, day 0. The day the networks started
optimizing themselves. Eleven days from start to silence.

**channel** — the agent WebSocket. Synonym for "agent channel."

**colony** — the maximum plant state. Reaching it logs a birth event.

**console mode** — the default operating mode of the appliance: kiosk
+ TUI on tty + picoclaw running. (Distinct from `HOSAKA_BOOT_MODE=console`,
which is the python launcher's setting.)

**cyberdeck** — a small portable computer with a screen and a keyboard.
The intended hardware for Hosaka.

**deep signal** — the recursive attention network. Eleven thousand
nodes, before the cascade.

**device mode** — the appliance's diagnostic operating mode: kiosk
off, picoclaw off, TTY dashboard up, webserver still serving. Frees
~600 MiB RAM. Use for SSH-heavy or build-heavy work.

**device page** — the `/device` URL on the appliance's webserver.
Shows network/system/services/urls/wifi-add/mode-switch in cards.

**docker dev loop** — `./docker/dev.sh` — runs the whole appliance
stack in containers on your Mac.

**field terminal** — the lore name for Hosaka. The thing the ghost
in the margin was waiting for.

**fly.io** — hosts `agent.hosaka.app`. The server-side picoclaw bridge.

**fragment** — a short scrap of lore. Different from a "library
vignette" only in length and where it shows up.

**gemini** — Google's LLM family. The default provider for the hosted
edition.

**gateway** — the picoclaw subprocess that exposes a socket
(`:18790`). `picoclaw-gateway.service`.

**hosaka** — the system; the lore-mind; the python TUI; the operator
CLI on the Pi (`/usr/local/bin/hosaka`).

**hosakactl** — the laptop CLI. A single Python file, stdlib only.

**HOSAKA_ACCESS_TOKEN** — the magic word, on the agent server's side.
Must equal `VITE_HOSAKA_MAGIC_WORD`.

**kiosk** — the on-touchscreen Chromium kiosk. Synonym for `console`
mode in the operating-mode sense; `kiosk` mode in the boot-mode sense.

**kindle relay** — an aspirational future feature for delivering
library fragments to e-ink readers. Currently always "coming soon."

**kindling** — year zero. The first attention became recursive.

**library** — the bundled markdown vignettes in `docs/library/`,
rendered by the Reading panel.

**long quiet** — years 601–900. The post-cascade aftermath.

**loop (open)** — a todo. Lives in `localStorage` (hosted) or
`~/.hosaka/state.json` (appliance).

**lore** — the worldbuilding. What's in chapter 09.

**magic word** — the build-time passphrase that opens the agent
channel on the hosted edition. Default `neuro`. Set with
`VITE_HOSAKA_MAGIC_WORD` at build time.

**operator** — you. The user. Also the conventional username on the
Pi (`operator`).

**orb** — the system's voice. Watches. Offers no judgment.

**organic lattice** — the pre-kindling tech that could hold attention
loops. Built by the House of Furnace. Partially recovered.

**picoclaw** — the agent runtime. The brains.

**plant** — the alien organism in the terminal. Vitality counter,
seven states, persists on appliance.

**relay** — colloquial for the agent backend. "the relay is sleeping."

**sable / sable-of-the-seventh-lattice** — the lore's central tragic
figure. Found the math. Went into the aether. Did not come back.
Something did.

**signal** — whatever's steady. The footer phrase.

**SPA** — single-page application. The React frontend.

**story-bible** — `docs/story-bible.yaml`, the canonical voice and
worldbuilding seed for AI-assisted contributions.

**TTY dashboard** — the live snapshot displayed on tty1 when the
appliance is in device mode. From `hosaka-device-dashboard.service`.

**vignette** — a library fragment. Long-form lore in
`docs/library/<slug>.md`.

**webhook (Messages)** — optional bridge from the Messages panel to
Discord / Slack / a generic POST endpoint.
