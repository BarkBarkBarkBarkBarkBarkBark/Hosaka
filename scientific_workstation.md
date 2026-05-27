# Neurodeck — Scientific Workstation Charter

> Cross-repo charter for a unified neurotech command station. Authored in the Hosaka repo because Hosaka contributes the canonical shell. The runtime will live in a new monorepo at `neurodeck/`.

## Purpose

Build a single operator-facing workstation that controls and observes a Neuralynx / DHN acquisition rig end-to-end:

- Live and replay acquisition (DHN_Acq via Pegasus / SSH bridge)
- NRD UDP packet emission and probing (port 26090, ATLAS subnet 192.168.3.0/24)
- Real-time spike sorting and control output (SNNeuro)
- Offline feature / unit-separation benchmarking (spike_discrim)
- Inline embedding of each tool's existing dashboard (no tab sprawl)
- Networking: interface enumeration, Wireshark / tshark / tcpdump on UDP 26090
- Local agent assistance (Picoclaw → Copilot → OpenAI → offline cascade)
- Headless rig operation via TUI

## Decision

**Option C — new `neurodeck/` monorepo** that lifts the strongest pieces from each existing app and pulls the four neuro repos in as git submodules. SAW and Hosaka remain buildable as fallback shells through Phase 5 and are not deprecated.

### Why not extend SAW alone

- Browser-only shell. Embedding the Django UIs from SNNeuro (`:8000`), dhn_client (`webapp/`), and the spike_discrim FastAPI frontend (`:8099`) requires `external_tab` launches — every tool opens a new browser tab. This is the #1 ergonomic problem with the previous SAW-only plan.
- No native networking primitives. Wireshark / nmcli / Tailscale would all be net-new.
- No terminal-first mode for headless rigs.

### Why not extend Hosaka alone

- No persistent workstation memory. The 24h SQLite ring buffer is fine for observability, wrong for artifacts and embeddings.
- No plugin runtime with agent-gated writes (`caps.json`), service supervisor, port allocation, or healthcheck. Building these would duplicate SAW's existing `service_manager` / `run_manager` / `plugins_runtime`.
- No subprocess host adapter — Hosaka's app model is Flatpak-only, which is wrong for the four neuro repos that run as host Python processes.

### Why a new monorepo

Both apps already converged on the same stack (React 18 + Vite 5, FastAPI, OpenAI fallback). Each has exactly the part the other lacks. A merge picks one of each — clean. The vestigial-code risk you flagged is real for both A and B; only C avoids it.

## Comparison

| Dimension | A. Extend SAW | B. Extend Hosaka | C. New `neurodeck/` |
|---|---|---|---|
| Primary shell | React canvas (browser) | Electron kiosk + `<webview>` + TUI | Electron kiosk wrapping React canvas; TUI optional |
| Embedding model | `external_tab` (new browser tabs) | `<webview>` panels (inline, no X-Frame-Options grief) | Inherits Hosaka `<webview>` |
| Process lifecycle | `service_manager.py` (subprocess, port, healthcheck) — strong | Electron `spawn()` for Flatpak only | Lift SAW supervisor + add Flatpak adapter behind common interface |
| Plugin metadata | YAML manifest, schema/bundle/external_tab UI modes, `caps.json` agent gating | TS `appRegistry.ts` + Flatpak YAML, `PreferredHost`, `EmbedPolicy` | Unified manifest with `host_adapter`, `embed_policy`, `arches`, `healthcheck` |
| LLM / agent | Copilot SDK + OpenAI fallback | Picoclaw → OpenAI → offline cascade | Hosaka router shape; adapters: Picoclaw, Copilot, OpenAI, offline |
| Persistence | Postgres + pgvector | SQLite 24h ring buffer | Both: Postgres for artifacts, SQLite ring for observability |
| Networking | None | nmcli, Tailscale, peer discovery, bridge gateway | Inherit Hosaka + new `capture` module for UDP 26090 |
| Wireshark / capture | Net-new | No prior art (but networking primitives present) | Capture service uses Hosaka networking + SAW supervisor |
| TUI | None | Custom ANSI TUI + `xterm` panel + `/code` shell | Keep Hosaka TUI as `neurodeck console` for headless rigs |
| Identity / skills | `copilot-instructions.md` | `identity/AGENT.md` + `skills/index.yaml` + `manager/charter.yaml` | Single `identity/` + `skills/` tree; skills become plugin tool surfaces |
| Upfront cost | Low | Medium | High |
| Vestigial code risk | High | High | **Lowest** |
| Time to first acquisition demo | Fastest | Slow | Slow first milestone, faster steady state |

> Note: "openclaw" mentioned in scoping was a misnomer for **Picoclaw** (Sipeed local agent runtime, gateway on `ws://127.0.0.1:18790`), already integrated in Hosaka via `hosaka/llm/router.py`.

## Canonical seams

| Concern | Source | Target in `neurodeck/` |
|---|---|---|
| Electron kiosk shell | Hosaka | `apps/kiosk/` |
| React SPA + panel registry | Hosaka | `apps/web/` |
| Plugin runtime + manifests | SAW | `packages/plugin-runtime/`, `services/api/app/plugins_runtime.py` |
| Service supervisor (subprocess, port, healthcheck) | SAW | `services/api/app/service_manager.py` |
| Run manager (artifact dirs, output capture) | SAW | `services/api/app/run_manager.py` |
| LLM router + adapters (Picoclaw, OpenAI, +Copilot) | Hosaka | `packages/llm-router/` |
| Networking (nmcli, Tailscale, discovery) | Hosaka | `packages/networking/` |
| Capture (Wireshark / tshark / tcpdump on UDP 26090) | New | `packages/networking/capture.py` |
| Identity, skills, charter | Hosaka | `packages/identity/` |
| TUI / headless console | Hosaka | `apps/console/` (optional) |
| Postgres + pgvector (artifacts, embeddings) | SAW | `services/api/app/embeddings.py` |
| SQLite 24h observability ring | Hosaka | `services/api/app/observability.py` |
| Agent-gated writes (`caps.json`) | SAW | `packages/plugin-runtime/caps.py` |
| Acquisition orchestration + diagnostics | dhn_client | submodule under `neuro/dhn_client/` |
| NRD UDP emit / probe | dhn_stream | submodule under `neuro/dhn_stream/` |
| Real-time spike sorting | SNNeuro | submodule under `neuro/SNNeuro/` |
| Offline feature benchmarking | spike_discrim | submodule under `neuro/spike_discrim/` |

## Host adapter model

A single `HostAdapter` interface unifies how the workstation starts, embeds, and stops a piece of software. Plugin manifests select an adapter via `host_adapter:` and an embed strategy via `embed_policy:`.

```
HostAdapter
  prepare()       -> resolve binary / arch / install_strategy
  start(ctx)      -> spawn / launch, return PID / port / URL
  healthcheck()   -> liveness + readiness probe
  embed_url()     -> URL the UI should render (None if no web surface)
  stop()          -> graceful shutdown + reap
```

| Adapter | Source pattern | Use for |
|---|---|---|
| `SubprocessAdapter` | SAW `service_manager` | dhn_stream CLI, SNNeuro `start.sh`, spike_discrim `spike-api`, dhn_client Django webapp, Wireshark GUI |
| `FlatpakAdapter` | Hosaka kiosk IPC | Spotify, Firefox, VS Code, Discord, etc. (operator tools) |
| `WebviewAdapter` | Hosaka `<webview>` | Embed any returned URL inline as a panel |
| `ExternalTabAdapter` | SAW external_tab | Browser-only fallback when `apps/kiosk` is not running |

## Plan

### Phase 0 — Charter and extraction map *(this deliverable)*
- Land `scientific_workstation.md` and `scientific_workstation.yaml` in the Hosaka repo as the cross-repo charter.
- Inventory exact files to lift from SAW and Hosaka with target paths in `neurodeck/`.
- Decide canonical seams (above).

### Phase 1 — Repo skeleton
- Create `neurodeck/` with pnpm + uv workspaces.
- Layout:
  ```
  neurodeck/
    apps/
      kiosk/              # Electron host (lifted from Hosaka kiosk/)
      web/                # React SPA (lifted from Hosaka frontend/)
      console/            # Optional TUI (lifted from hosaka/tui/ + main_console.py)
    services/
      api/                # FastAPI (SAW plugin runtime + Hosaka /api/v1)
    packages/
      plugin-runtime/     # SAW plugins_runtime + caps
      host-adapters/      # SubprocessAdapter | FlatpakAdapter | WebviewAdapter | ExternalTabAdapter
      llm-router/         # Hosaka router + Picoclaw/OpenAI/Copilot adapters
      networking/         # nmcli, tailscale, discovery, capture
      identity/           # AGENT.md, SOUL.md, USER.md, skills/, charter.yaml
    neuro/
      dhn_stream/         # submodule
      dhn_client/         # submodule
      SNNeuro/            # submodule
      spike_discrim/      # submodule
    machine-specs/        # YAML specs incl. this charter
  ```
- Decide submodule vs. workspace package per neuro repo. **Recommendation: submodules** (independent CI, releases, owners).

### Phase 2 — Lift Hosaka shell *(parallel with Phase 3)*
- Move `kiosk/main.js`, `kiosk/preload.js`, `kiosk/package.json` → `apps/kiosk/`. Keep `<webview>` IPC bridges (`hosakaBrowserAdapter`, `hosakaAppHost`) renamed to `neurodeck*`.
- Move `frontend/src/{App.tsx,shell,panels,apps,ui/appRegistry.ts}` → `apps/web/src/`. Keep panel lazy-chunk pattern.
- Move `hosaka/llm/{router.py,picoclaw_adapter.py,openai_adapter.py}` → `packages/llm-router/`.
- Move `hosaka/network/` (nmcli, tailscale, discovery) → `packages/networking/`.
- Move `hosaka/tui/` + `hosaka/main_console.py` → `apps/console/`.
- Move `identity/`, `skills/`, `manager/charter.yaml` → `packages/identity/`.

### Phase 3 — Lift SAW runtime *(parallel with Phase 2)*
- Move `services/saw_api/app/{plugins_runtime.py,service_manager.py,run_manager.py}` → `services/api/app/`.
- Extend the SAW `PluginManifest` with Hosaka's `arches`, `embed_policy`, `preferred_host`, `install_strategy` fields. Add `host_adapter:` selector.
- Move SAW Postgres + pgvector setup. Keep Hosaka SQLite 24h observability ring as a separate events store.
- Add `CopilotAdapter` to the lifted LLM router so it sits alongside Picoclaw + OpenAI.

### Phase 4 — Host adapter unification *(depends on 2 + 3)*
- Define `HostAdapter` interface in `packages/host-adapters/`.
- Implement `SubprocessAdapter` (from SAW `service_manager`), `FlatpakAdapter` (from Hosaka kiosk IPC), `WebviewAdapter` (returns embed URL for `<webview>`), `ExternalTabAdapter` (browser fallback).
- Plugin manifests select adapter via `host_adapter:`; UI picks `<webview>` panel vs. external tab from `embed_policy`.

### Phase 5 — Neuro plugins *(depends on 4)*
- Port the four utility plugins from the prior plan, now using `host_adapter: subprocess` + `embed_policy: prefer_embed`:
  - `neuro.snn_dashboard` — wraps `SNNeuro/start.sh` or `python manage.py run_all`; embeds the Django dashboard.
  - `neuro.spike_discrim_workbench` — wraps `spike-api`; embeds `:8099` frontend.
  - `neuro.dhn_pipeline_dashboard` — wraps `dhn_client/webapp/manage.py runserver`; embeds the Django UI.
  - `neuro.dhn_stream_control` — schema UI for `dhn-stream` and `dhn-probe` parameters.
- Add `neuro.station_control` native panel: profile selector (sim / live), packet rate, service status, capture buttons.

### Phase 6 — Wireshark + capture service *(depends on 4)*
- New `packages/networking/capture.py`: interface enumeration, dumpcap / tshark / tcpdump / wireshark availability and permission probes.
- New plugin `neuro.capture` with three actions:
  1. Live Wireshark GUI via allowlisted argv `["wireshark", "-k", "-i", iface, "-f", "udp port 26090"]`.
  2. Background tshark → pcap capture.
  3. Remote tcpdump-over-SSH for live-lab profile.
- Reuse Hosaka `HOSAKA_HTTP_ALLOWED_HOSTS` pattern as `NEURODECK_CAPTURE_ALLOWED_IFACES`.

### Phase 7 — Live-lab orchestration *(depends on 5)*
- Wrap `dhn_client` `SessionOrchestrator.from_yaml` / `run` and `Diagnostics.run_all` as plugins with explicit start gates (no auto-start on page load).
- Reuse `dhn_client/configs/example_session.yaml` as base session template.
- Two first-class profiles: `simulated` and `live-lab`. `live-lab` requires explicit user action and configured SSH host / user / interface.

### Phase 8 — Integration data contracts
- Normalize station event records: service lifecycle, packet health, capture sessions, SNN spikes / control, spike_discrim summaries.
- Timebase contract: NRD microsecond timestamps are canonical; SNN runs on decimated sample indices; spike_discrim works on trough-aligned snippets.

### Phase 9 — Verification
1. `apps/kiosk` boots, loads `apps/web`, embeds a placeholder URL via `<webview>`.
2. `services/api` `/api/health` and `/api/plugins/list` return the new neuro utilities.
3. Each neuro plugin starts via `SubprocessAdapter`, healthcheck passes, URL embeds inline.
4. LLM router cascade test: force Picoclaw down → Copilot; force Copilot down → OpenAI; force all down → offline.
5. Wireshark GUI launches with fixed UDP 26090 filter on the chosen interface; PID tracked.
6. Live-lab readiness probes (no acquisition): `Diagnostics.run_all`, dumpcap perms, interface enumeration.
7. Per-repo tests still pass via submodule CI: `dhn_stream` pytest, `spike_discrim` pytest, SNN smoke launch.
8. SAW and Hosaka original repos still build (kept as fallback shells through Phase 5).

## LLM router order

`Picoclaw → Copilot → OpenAI → offline`

Rationale: Picoclaw is local, free, and private; Copilot has the strongest tool / agent surface when the workstation is online; OpenAI is the broadest fallback; offline keeps the rig usable without network.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Two extractions before any neuro feature ships | Phases 2 and 3 run in parallel; SAW + Hosaka kept buildable as fallbacks |
| Plugin runtime + LLM router are the most opinionated parts | Pick canonical owners up front: SAW for runtime, Hosaka for router |
| Picoclaw not present on workstation | Cascade falls through to Copilot / OpenAI; Picoclaw is opportunistic |
| Submodule churn (four repos) | Pin to commit SHAs; bump deliberately; CI runs per-submodule tests |
| Electron + React SPA + FastAPI + Postgres footprint on field rigs | TUI / headless mode kept first-class; kiosk is opt-in |
| Wireshark permissions (dumpcap group, sudoers) | Capture service probes and reports remediation steps; manual launch fallback |

## Open questions

1. **Submodule vs. workspace packages** for neuro repos. Default: submodules. Override if you want lockstep versioning.
2. **TUI scope.** Default: keep first-class as `apps/console/`. Override to demote to `tools/`.
3. **Picoclaw availability** on your workstation — confirm whether the binary is installed on `127.0.0.1:18790`. If not, the cascade still works but Picoclaw will be skipped.

## Relevant files

### Hosaka (lift to `apps/kiosk`, `apps/web`, `apps/console`, `packages/llm-router`, `packages/networking`, `packages/identity`)
- `Hosaka/kiosk/main.js`, `Hosaka/kiosk/preload.js`, `Hosaka/kiosk/package.json`
- `Hosaka/frontend/src/App.tsx`, `Hosaka/frontend/src/ui/appRegistry.ts`, `Hosaka/frontend/src/{shell,panels,apps}/`
- `Hosaka/hosaka/llm/{router.py,picoclaw_adapter.py,openai_adapter.py}`
- `Hosaka/hosaka/network/{nmcli.py,tailscale.py,discovery.py}`
- `Hosaka/hosaka/tui/`, `Hosaka/hosaka/main_console.py`
- `Hosaka/hosaka-apps/manifest.schema.yaml`, `Hosaka/hosaka-apps/registry.yaml`
- `Hosaka/identity/`, `Hosaka/skills/`, `Hosaka/manager/charter.yaml`

### SAW (lift to `services/api`, `packages/plugin-runtime`)
- `Scientific-A.I.-Workstation/services/saw_api/app/plugins_runtime.py`
- `Scientific-A.I.-Workstation/services/saw_api/app/service_manager.py`
- `Scientific-A.I.-Workstation/services/saw_api/app/run_manager.py`
- `Scientific-A.I.-Workstation/services/saw_api/app/embeddings.py`
- `Scientific-A.I.-Workstation/services/saw_api/app/main.py` (extract route definitions)
- `Scientific-A.I.-Workstation/saw-workspace/plugins/saw.utility.file_browser/` (template)
- `Scientific-A.I.-Workstation/src/components/TopBar.tsx` (Utilities menu pattern)

### Neuro repos (enter as submodules under `neuro/`)
- `dhn_stream/src/darkhorse_neuralynx/cli.py`, `dhn_stream/src/darkhorse_neuralynx/udp_raw/probe.py`
- `dhn_client/src/darkhorse_neuralynx/orchestrator/run.py`
- `dhn_client/src/darkhorse_neuralynx/dhn_client/diagnose.py`
- `dhn_client/webapp/manage.py`, `dhn_client/configs/example_session.yaml`
- `SNNeuro/start.sh`, `SNNeuro/src/snn_agent/server/app.py`, `SNNeuro/dashboard/api.py`
- `spike_discrim/api/main.py`, `spike_discrim/scripts/run_benchmark.py`

## Decisions

- "openclaw" reinterpreted as **Picoclaw** (Hosaka's existing local agent runtime).
- Recommended path is **Option C** (new `neurodeck/` monorepo).
- Charter lives in the Hosaka repo at `scientific_workstation.{md,yaml}`.
- Neuro repos enter as **git submodules**, not absorbed packages.
- SAW + Hosaka kept buildable as fallback shells through Phase 5; no immediate deprecation.
- LLM router cascade: **Picoclaw → Copilot → OpenAI → offline**.
- TUI / headless console kept first-class.
