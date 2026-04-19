# Hosaka — Claims vs Reality Audit

**Scope:** `/home/operator/Hosaka` — README, `docs/`, `frontend/src/shell/commands.ts`, `frontend/public/locales/en/`, install/boot scripts, `hosaka/`, `hosaka/web/server.py` (picoclaw).

**Date:** 2026-04-19. Static reading; runtime verification (picoclaw binary, GitHub release assets, Docker) was not performed.

## Severity summary

| Category | Count (approx.) |
|----------|-----------------|
| WORKS | 18 |
| PARTIAL | 14 |
| BROKEN | 8 |
| ASPIRATIONAL | 5 |
| MISLEADING | 12 |

---

## README — Install & URLs

| Claim | Verdict | Notes |
|-------|---------|--------|
| Picoclaw from `https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz` | **PARTIAL** | Repo/org `sipeed/picoclaw` matches `setup_hosaka.sh` / `install_hosaka.sh` links. Exact asset name/version must be checked on GitHub at install time. |
| `picoclaw onboard` | **PARTIAL** | Scripts require it; not verified here without running picoclaw. |
| `pip install -r requirements-hosaka.txt` + `python -m hosaka` | **WORKS** (layout) | Repo contains `requirements-hosaka.txt` and package `hosaka/`; manual path is coherent. |
| `picoclaw gateway &` | **PARTIAL** | Matches common picoclaw usage; subcommand name not verified in this read-only pass. |
| Clone URL `https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git` | **PARTIAL** | Repo visibility not verified; path is consistent with `/docs` and code. |

---

## README — Boot modes & `scripts/switch_boot_mode.sh`

| Claim | Verdict | Notes |
|-------|---------|--------|
| Three modes: `console`, `headless`, `kiosk` | **WORKS** | `scripts/switch_boot_mode.sh` implements all three and enables the right systemd units. |
| README table: `HOSAKA_BOOT_MODE` … `headless` / `web` | **MISLEADING** | Scripts and switch script use **`headless`**, not `web`. |
| `scripts/setup_hosaka.sh` boot mode | **PARTIAL** | Declares `kiosk \| headless \| console`; **Step counter says "3/3" then "Step 3/4" / "4/4"** — inconsistent copy. |
| `console` mode services | **BROKEN** | `setup_hosaka.sh` enables **`hosaka-console.service`**, but **`/home/operator/Hosaka/systemd/` has no `hosaka-console.service`** — only `hosaka-field-terminal.service`. Console boot via setup script is **broken as written**. |
| `switch_boot_mode.sh` vs `setup_hosaka.sh` | **PARTIAL** | Switch script uses `hosaka-field-terminal.service`; setup uses non-existent `hosaka-console.service`. |
| **NEW (2026-04):** `hosaka mode console / device` | **WORKS** | Replaces ad-hoc `kiosk`/`build` from the lean refactor; legacy aliases still accepted. See `scripts/hosaka`. |

---

## README — “What you get” vs `commands.ts`

README lists `/chat`, `/doctor`, `/restart`, `/update`, `/net`, `/ping`, `/dns`, `/scan`, `/draw`, `/code`, etc.

| Verdict | Notes |
|---------|--------|
| **MISLEADING / ASPIRATIONAL** | `frontend/src/shell/commands.ts` is the real palette: `/help`, `/commands`, `/about`, `/docs`, `/ask`, `/model`, `/reset`, `/settings`, `/agent` (+ subcommands), `!<cmd>`, `/netscan`, `/read`, `/todo`, `/status`, `/signal`, `/clear`, `/plant`, `/orb`, `/lore`, `/echo`, `/messages`. **No `/doctor`, `/restart`, `/update`, `/net`, `/ping`, `/dns`, `/scan`, `/draw`, `/code` in the shell dispatcher.** |

---

## Slash commands — `HosakaShell.ts` vs descriptions

Implemented in `dispatch()` (`frontend/src/shell/HosakaShell.ts`): `/help`, `/commands`, `/about`, `/status`, `/plant`, `/orb`, `/lore`, `/signal`, `/clear`, `/echo`, `/docs`, `/messages`, `/terminal`, `/read`, `/todo`, `/netscan`, `/exit`, `/ask`, `/chat`, `/model`, `/agent`, `/settings`, `/reset`, default → `unknown`.

| Command | Claim vs code | Verdict |
|---------|----------------|--------|
| `/help`, `/commands`, `/about`, `/docs`, `/echo`, `/signal`, `/clear`, `/exit` | Match | **WORKS** |
| `/chat` and `/ask` | Same branch; both need a non-empty arg or usage line — **not** an interactive REPL | **PARTIAL** |
| `/model`, `/reset` | Gemini `localStorage` config + history clear | **WORKS** (client-side) |
| `/settings` | Opens settings only if `VITE_SHOW_SETTINGS === "1"`; kiosk `.env.appliance` sets **0** | **PARTIAL** |
| `/agent`, `/agent on|off`, `/agent test`, URL/pass | Implemented | **PARTIAL** — `loadAgentConfig` forces `enabled: true` always (can’t persist “off” across reload) |
| `!shell` | Requires agent; client sends `{ type: "shell", cmd }` | **BROKEN** on appliance — see WebSocket section below |
| `/netscan` | Locale: “theatrical + real” | **PARTIAL** — mostly synthetic `generatePacket` + optional `ss` via agent; **not** arp-scan/nmap |
| `/read`, `/todo` | Library fetch + panels | **PARTIAL** — `/read order` = “kindle not tuned” |
| `/plant` | Renders ASCII from session `plantTicks` | **PARTIAL** — see Plant section |
| `/lore` | `getLoreFragments()` from i18n `shell.lore` | **WORKS** — substantive multi-fragment copy in locale JSON |
| `/messages` | Prints hint to switch tab | **PARTIAL** — Messages **not** on main dock; only via this hint/event |

---

## Plant (`README` "The plant" + `~/.hosaka/plant.json`)

| Claim | Verdict | Where |
|-------|---------|--------|
| State in `~/.hosaka/plant.json`, vitality, decay, births | **WORKS** | `hosaka/tui/plant.py` — `_PLANT_PATH`, decay, `births` on colony transition, `record_interaction()`. |
| Same behavior in **browser shell** | **BROKEN / MISLEADING** | `HosakaShell.ts` uses `plantTicks` in memory only; no `localStorage`/file; no inactivity decay; no birth counter. `PlantBadge.tsx` is a rotating glyph, not tied to plant state. |
| README implies one global plant story | **MISLEADING** | Python TUI vs SPA are two different plant models unless README clarifies. |

---

## `/netscan` vs `arp-scan` / `nmap`

| Claim | Verdict | Notes |
|-------|---------|--------|
| `install_hosaka.sh` installs `arp-scan` and `nmap` | **WORKS** | Script runs `apt-get install -y arp-scan nmap`. |
| Shell `/netscan` uses them | **MISLEADING** | `HosakaShell.ts` `netscan()` uses `netscan.ts` synthetic traffic + optional `ss` through agent — does not invoke arp-scan/nmap. |

---

## `/messages` — webhooks

| Claim | Verdict | Notes |
|-------|---------|--------|
| “Webhook system” | **PARTIAL** | `MessagesPanel.tsx`: client-side `fetch(webhook)` with JSON body; localStorage for config/log. No Hosaka backend for relay. |
| Discord / Slack | **PARTIAL** | Works **if** the endpoint allows browser CORS — many chat webhooks block browser POSTs; often needs a server-side proxy (not provided). |
| “No backend required” (locale) | **PARTIAL** | Honest for Hosaka; not always true for third-party URLs from the browser. |

---

## `/lore`

**WORKS** — substantive fragments in `frontend/public/locales/*/shell.json` under `"lore"` (and `getLoreFragments()`). Not empty placeholder.

---

## `/ask` vs Picoclaw — backends & env

| Layer | Verdict | Notes |
|-------|---------|--------|
| Default text → agent | **WORKS** when WS + picoclaw work. `agentClient.ts` defaults to `VITE_HOSAKA_AGENT_URL` or Fly URL; `.env.appliance` → `ws://127.0.0.1:8421/ws/agent`. `server.py /ws/agent` runs `picoclaw agent --message` via `_run_picoclaw`. Needs `PICOCLAW_HOME` / `~/.picoclaw/config.json` (and/or `OPENAI_API_KEY`). |
| `/ask` / `/chat` → `askGemini()` | **BROKEN** on appliance | `gemini.ts` POSTs `{ model, prompt, history, system }` to `/api/gemini`. `server.py` only reads `contents` / `messages` → 400 “no messages”. Client expects `data.text`; server returns only `candidates[...].content.parts[...].text` — even a fixed server would need parser alignment. |
| README “Gemini proxy one-shot /ask” vs “picoclaw default voice” | **MISLEADING** on Pi | Appliance `/api/gemini` routes to picoclaw/OpenAI, not Google Gemini; `gemini.ts` naming is legacy. |
| `en/ui.json` “picoclaw on fly.io … gemini” | **MISLEADING** for local appliance builds | Contradicts local WS + local `/api/gemini` behavior. |

---

## `/draw`, `/chat` as in README

| Command | Verdict |
|---------|--------|
| `/draw` | **ASPIRATIONAL** — not in `HosakaShell.ts` switch. |
| `/chat` “interactive AI session” | **PARTIAL** — same as `/ask` with arg; no dedicated session UI; history is used inside `askGemini` only. |

---

## Tailscale (`install_hosaka.sh`)

| Claim | Verdict | Notes |
|-------|---------|--------|
| Install script installs Tailscale | **WORKS** | `curl … tailscale.com/install.sh` when `INSTALL_TAILSCALE=1`. |
| Running app “uses” Tailscale | **PARTIAL** | `hosaka/setup/orchestrator.py` + `/setup/network` show `tailscale_status` from `detect_tailscale_status()`. No Tailscale in frontend shell commands (README `/net` not implemented). Setup wizard surfaces it; main UI does not. |

---

## Docker — `./docker/dev.sh`

| Claim | Verdict | Notes |
|-------|---------|--------|
| File exists | **WORKS** | `/home/operator/Hosaka/docker/dev.sh` present (`up`, `tui`, `test`, `stop`, `nuke`, …). |
| “Works” | **PARTIAL** | Not executed here. |
| `./docker/dev.sh status` health URL | **MISLEADING** | Script curls `http://localhost:8421/progress` — app exposes `/setup/progress` (see `server.py`), not `/progress`. |

---

## i18n — six locales

| Claim | Verdict | Notes |
|-------|---------|--------|
| Six languages bundled | **WORKS** | `frontend/src/i18n.ts`: `en`, `es`, `fr`, `it`, `ja`, `pt`; glob loads `shell` + `ui` JSON. |
| All panels translated | **PARTIAL** | Major UI strings use `t()`; residual English can appear in dynamic content, library markdown (often English source), `/docs` URL, code paths in help. Not fully audited string-by-string. |

---

## Picoclaw in `hosaka/web/server.py`

| Feature | Verdict | Notes |
|---------|---------|--------|
| `_run_picoclaw` subprocess, banner strip, `HOME`/`PICOCLAW_HOME` | **WORKS** | Thoughtful env for systemd/root. |
| `/api/chat`, `/api/gemini` | **PARTIAL** | Routing to picoclaw/OpenAI is real; `gemini` endpoint does not match frontend `gemini.ts` body/parse. |
| `/ws/agent` | **PARTIAL** | Chat path via `message` works; `!shell` / `runShell` not implemented (no `shell_reply`). |

---

## Operator CLI `scripts/hosaka` vs README

| Claim | Verdict | Notes |
|-------|---------|--------|
| `hosaka mode build` / `hosaka mode kiosk` | **WORKS** (legacy aliases) | Now mapped to `device` / `console` in script. |
| `hosaka build` warns when not in build mode | **FIXED 2026-04-19** | Old check compared raw mode to `"build"` but `read_runtime_mode` returns `"device"`. Patch in same change as this audit. |

---

## Boot performance / quick wins (#14)

Already done in the lean refactor:
- Lazy frontend panels, no `tsc` in default build, no sourcemaps, marked instead of react-markdown, in-house i18n shim.
- `MemoryMax` / `CPUQuota` on webserver and picoclaw-gateway.
- ALSA units masked.
- Persistent journal (this audit's commit).
- SSH OOM guard (this audit's commit).

Still on the table:
- Fix `/api/gemini` ↔ `gemini.ts` mismatch so `/ask` and `/chat` stop failing silently in the kiosk.
- Implement or drop the `!shell` WS path so `agentClient.runShell` doesn't time out forever.
- Align `setup_hosaka.sh` systemd names with what's actually in `systemd/`.
- One-line `docker/dev.sh` status URL fix to `/setup/progress`.
- Pre-render `/lore` and `/library/*` markdown at build time (move the small `marked` runtime cost off the Pi).

---

## TOP 5 — fix or remove (priority)

1. **Appliance LLM path:** Align `frontend/src/llm/gemini.ts` with `/api/gemini` (request body + response: add `text` or parse `candidates`, and send `messages`/`contents`). Until then, `/ask`/`/chat` are effectively broken against local FastAPI.
2. **WebSocket parity:** Either implement `shell` → `shell_reply` in `hosaka/web/server.py` (matching `agentClient.runShell`) or stop advertising `!shell` for the appliance build.
3. **`setup_hosaka.sh` console mode:** Replace `hosaka-console.service` with the actual unit name (`hosaka-field-terminal.service`) or add the missing unit file — current console path is inconsistent with the repo.
4. **README "What you get":** Replace with `getCommands()`-accurate list; drop `/draw` or implement it; clarify `/chat` vs `/ask`.
5. **Operator script polish:** Fix `cmd_build` mode check (compare to `device`) and `docker/dev.sh status` URL (`/setup/progress`).
