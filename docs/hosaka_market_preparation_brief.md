# Hosaka: external extensions and market preparation

Prepared 2026-10-17. This is an implementation handoff, not an implemented release.

## Approved architecture and execution status

Operator direction on 2026-10-17 supersedes the older desktop/arcade and native-game
extension assumptions in this audit. Work is on `dev`, tracked in #31.
This is the golden architecture; the two existing decks may be reconfigured.
Preserve user content and working capabilities, including the small Menu button.

- Python TUI/CLI is canonical. The thin React/Electron TUI + Menu host stays
  as the deck interface; the independent desktop/arcade and Pong/Snake do not.
- RetroArch PlayStation games remain a separate native subsystem:
  `hosaka play twisted metal`, `hosaka play tekken`, `hosaka play spyro`.
- Extensions are independent packages, not Flatpak applications or ROM wrappers.
- Foliate and optional VS Code remain externally managed apps with a small,
  separate console launch adapter.
- Keep any display/session infrastructure actually required by external apps
  and RetroArch. Do not replace the terminal + Menu host with a bare terminal.

Execution slices: native paths/installation diagnostics; credential/PicoClaw
ownership; protected extension runtime; TUI/agent dispatch and external Halloween
proof; actual game/app regression checks; pilot deck and clean-storage replication.
Inventory the real decks for migration rather than maintaining every historical
layout. Keep one deck known-good until the pilot is qualified.

The first slice adds `hosaka.paths`, native setup initialization, `/paths`,
`hosaka paths --json`, `hosaka doctor --offline`, and shared ROM selection.
The next slice preserves the graphical TUI + Menu default, shares session
supervision between LXQt/Openbox, retains saved display/session choices, and
checks update restoration without restarting the login/TTY.
Neither slice implements an extension manager merely by creating directories.
Provider migration, hardware qualification and automatic appliance custom-root
propagation remain pending.

### Validation checkpoint: 2026-10-17

Validated the uncommitted `dev` working tree based on `03cda023`, not a released
or physically qualified appliance. Local Python was 3.12.8; Docker was 29.5.3.
The freshly built validation image contains PicoClaw 0.3.1.

| Check | Result |
| --- | --- |
| Targeted Python suites: paths, kiosk boot, appliance setup, console, terminal GUI, update deployment, PS1 play, PicoClaw runtime and LLM setup | 214 passed; exit 0 |
| Games, games API/menu and feature-registry smoke suites | 28 passed; exit 0 |
| Chat/provider-adapter regressions, including request overlays | 86 passed; exit 0 |
| `TEST_PYTHON="$PWD/.hosakavenv/bin/python" bash tests/test_source_install.sh` | Passed; exit 0; isolated fixture installation, not a fresh host install |
| `bash tests/test_docker_client.sh` | Passed; exit 0 |
| `tests/test_docker_client.ps1` in the existing PowerShell 7.4 Linux container | Passed; exit 0; not a native Windows qualification |
| `docker build -f docker/Dockerfile -t hosaka:validation-20261017 .` | Passed; exit 0; includes frontend `tsc -b && vite build` |
| `HOSAKA_IMAGE=hosaka:validation-20261017 bash tests/test_container_runtime.sh` | Passed; exit 0; real image startup/health, UI/build stamp, external package/data persistence across replacement, workspace mounts and local mock-provider tool round trip |
| Local `python -m hosaka paths --json` and `python -m hosaka doctor --offline --json`, using `.hosakavenv/bin/python` | Both exit 0; all offline checks passed; no provider request verified |
| Shared browser at `http://127.0.0.1:8421/?gui=1` | Menu opens/closes and the same terminal DOM element survives both operations |
| Changed shell-script syntax and `git diff --check` | Passed; exit 0 |

The Python suite files were `test_paths.py`, `test_kiosk_boot.py`,
`test_appliance_install.py`, `test_hosaka_main_console.py`,
`test_terminal_gui.py`, `test_update_deployment.py`, `test_play.py`,
`test_picoclaw_runtime.py`, `test_llm_setup.py`, `test_games.py`,
`test_games_api.py`, `test_games_menu.py`, `test_registry_smoke.py` and
`test_hosaka_chat.py`, all under `tests/`, run with
`.hosakavenv/bin/python -m pytest -q` in three focused groups.

Read-only local inventory confirms the transitional ownership boundary:

- `~/.hosaka` is operator-owned mode 0700; its installation record is 0600.
  The external extension/data/state/log directories exist.
- Canonical `config.json`, `secrets.json`, `providers.json` and the Hosaka-owned
  `picoclaw/` runtime do not yet exist. Reported target paths are not active
  credential stores.
- Legacy `~/.hosaka/llm.json` exists with mode 0644 inside the private data root;
  private-file normalization belongs to the explicit migration.
- Existing `~/.picoclaw` has a v3 config and security sidecar, both mode 0600,
  and its workspace is still `~/.picoclaw/workspace`. Its selected alias is
  `qwen2.5`, with 31 model entries. Preserve this independently managed setup,
  memories, sessions and skills until an owner-approved import.

No credential values were displayed, and no migration or runtime reconfiguration
was performed. Adding these folders to the editor workspace provides access for
deliberate integration; it does not change runtime ownership or precedence.
Pi boot/reboot, real RetroArch/Foliate behavior, real provider access, clean-device
replication and protected extension execution remain unverified.

### Read-only ownership and migration inventory slice

Implemented locally under #31 as `hosaka migrate --dry-run [--json]` and
`/migrate --dry-run [--json]`. The shared report labels effective paths in the
current process separately from proposed canonical destinations. It includes
source metadata, saved model profiles, credential candidate disagreements and
workspace/memory/session/skill locations. Stored profile references and environment
files are inspected, not applied. Existing environments may already have been
hydrated by a TUI/service; original provenance is explicitly unknown in that case.
Strict security-sidecar parsing uses the now-declared PyYAML dependency.

Docker clients bypass initialization for this command. Stopped-container
inventory uses existing read-only mounts and a read-only image filesystem;
missing mounts fail rather than creating host directories. Running-container
inventory uses the same non-mutating implementation through `docker exec`.
No extension manager, migration apply, credential rotation or automatic runtime
relocation is implemented by this slice.

Validation of the inventory implementation on 2026-10-17:

- `.hosakavenv/bin/python -m pytest -q tests/test_migration.py
  tests/test_hosaka_main_console.py tests/test_paths.py tests/test_hosaka_chat.py
  tests/test_llm_setup.py tests/test_picoclaw_runtime.py tests/test_terminal_gui.py`
  passed all 250 tests (exit 0). Coverage includes unchanged fixture file
  bytes/modes and environment, denied network/process/write operations, invalid
  JSON/YAML/schema, missing parser, read-only files, custom roots, a nonstandard
  operator, explicit overrides, saved/multiple models, conflicts and redaction.
- Bash Docker-client, PowerShell Docker-client (Linux PowerShell container) and
  isolated source-installer regressions passed (exit 0). Inventory routes bypass
  initialization, never create host mount directories or pull images, and
  preserve argument boundaries.
- `docker build -f docker/Dockerfile -t hosaka:validation-inventory-20261017 .`
  and `HOSAKA_IMAGE=hosaka:validation-inventory-20261017 bash
  tests/test_container_runtime.sh` passed (exit 0). Real running/stopped
  inventories returned valid JSON; stopped inventory left all fixture content
  and modes unchanged. An empty-home inventory succeeded on a read-only image
  filesystem with networking disabled, without creating a runtime.
- Native `bash scripts/hosaka migrate --dry-run --json` returned exit 0 and
  `inventoried` on the operator's existing split layout, with no differing
  comparable credential candidates. It reported mode-0600 warnings for the
  legacy LLM configuration and repository environment file. Checked configuration
  bytes/modes were unchanged; no credentials were displayed or imported.
- Pylance syntax/diagnostics, changed shell syntax and `git diff --check` passed.

These checks qualify the read-only inventory slice, not a migration or real
provider request. Exit 2 means candidate credentials differ and require review;
exit 1 means invalid/unreadable inputs or unavailable parsers. Warnings remain
visible even when a completed inventory exits 0.

Scope and subsequent migration work:

1. Extend the shared resolver/report to distinguish effective existing
   PicoClaw/config/credential locations from proposed canonical destinations.
   Inventory the locations listed in the credential-migration section,
   including explicit overrides and legacy system state. Inspect only
   whitelisted metadata; never dump configuration or credential values.
2. Add an explicit read-only migration dry run reporting provider/model
   selection, credential presence/source, redacted conflicts, owners/modes,
   workspace/session locations and proposed actions. Preserve standalone
   PicoClaw precedence until the operator approves a switch.
3. Cover the current split layout, conflicting sources, multiple models,
   nonstandard operators, custom data roots, paths with spaces, malformed files
   and read-only locations. Verify unchanged file bytes/modes and no directory
   creation, bootstrap, network requests or secret-bearing output.
4. Use that report to define the subsequent opt-in, versioned migration:
   protected backups; canonical secret ownership and nonsecret profile
   references; resolved Hosaka-owned PicoClaw bootstrap; private v3 adapters;
   preserved selected-model overlays; atomic/resumable switching and rollback.
   Retain legacy copies and leave unrelated upstream PicoClaw configuration
   alone. Wire launcher/service custom-root propagation and stop normal
   root-home bootstrap in that coordinated migration slice.

Exit gate for this slice: CLI and TUI expose the same redacted inventory,
the current setup continues working unchanged, and tests prove the dry run is
read-only. Provider rotation/import and real-device checks are later gates, not
success claims for inventory work. After this gate, review the inventory with the
operator and implement an explicitly approved import/ownership switch, coordinated
with launcher/service paths and elimination of normal root-home bootstrap.

## Objective

Make Hosaka a stable appliance people can extend without forking or editing its core repository. Use an independently developed Halloween joke-citation extension as the first complete demonstration. Standardize installation, games, PicoClaw runtime, provider settings, and credential storage so a device owner can understand and troubleshoot them.

Keep source installation first-class. Do not require Docker for native Raspberry Pi installation or extension authoring. Preserve the working TUI, PicoClaw agent harness, RetroArch games, and Foliate integration.

## Repository and the earlier plan

Repository: https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka

Audited main at commit `03cda0236617ef3a1733e9ae55ef631333c61345`. Recheck main before implementing; this audit describes that snapshot.

The strongest matching existing plan is [docs/increased_observability.yaml](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/blob/03cda0236617ef3a1733e9ae55ef631333c61345/docs/increased_observability.yaml):

- Phase 02 defines plugin manifests, ownership, permissions, commands, and feature contracts.
- Phases 03/05/06 require plugin lifecycle events, terminal survival after plugin failure, safe mode, and enable/disable commands.
- Its future work explicitly includes a permission sandbox for plugins.

[docs/AGENT_CONTEXT.md](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/blob/03cda0236617ef3a1733e9ae55ef631333c61345/docs/AGENT_CONTEXT.md) points to that plan. Some commands in these documents are planned, so documentation alone is not evidence they work. [docs/app_framework_progress.md](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/blob/03cda0236617ef3a1733e9ae55ef631333c61345/docs/app_framework_progress.md) is explicitly historical and describes an archived frontend.

Earlier conversation retrieval also identified a proposed `recenter/tui-first` branch and external plugins/skills, but that branch was absent from the current branch listing. Treat it as historical discussion, not an existing implementation. No matching dedicated plugin implementation issue was found in the returned issue list.

## What the code currently does

| Area | Observed behavior | Implication |
| --- | --- | --- |
| Native source install | Root `install.sh` creates/reuses a repo virtualenv, installs PicoClaw under a user prefix, seeds runtime, and writes a source launcher. | The checkout remains the live implementation; user extension code must live elsewhere. |
| Appliance install | `scripts/install_hosaka.sh` copies runtime into `/opt/hosaka-field-terminal` and writes `/etc/hosaka/repo_root`. | Retain this runtime path initially; another rename would add migration work. |
| Other installers | `install/install.sh` and `install/bin/hosaka` implement a separate Docker client. `scripts/install-local-cli.sh` can install a symlink into several different bin directories. | Document three deployment modes and eliminate launcher ambiguity. Do not silently replace one installation type with another. |
| Existing apps | `hosaka/apps.py` reads manifests from `HOSAKA_APPS_ROOT/apps`, defaulting to repo `hosaka-apps/apps`. It requires a Flatpak ID and launch command. | Useful app-launch seam, but not a general extension loader. |
| Feature registry | `docs/hosaka.features.yaml` and `hosaka/obs/registry.py` already exist. | Extend these rather than create a competing feature catalog. |
| PlayStation games | `hosaka/play.py` uses `HOSAKA_PSX_ROMS`, otherwise searches `~/RetroPie/roms/psx`, `~/Games/PlayStation`, and `~/Games/psx`. | There is no single established Hosaka game-content directory. Preserve existing libraries during migration. |
| Game integration | `hosaka/games.py`, `hosaka/web/games_api.py`, `frontend/src/TerminalGui.tsx`, and `hosaka/voice/tools.py` share the current native PS1 flow. | Keep this working while adding an external game category. |
| PicoClaw runtime | `hosaka/picoclaw_runtime.py` generates identity, manager files, and skills under `~/.picoclaw/workspace`; appliance setup also seeds root's runtime. | Account/home selection can create duplicate agent state. |
| Agent permissions | Runtime generation permits reads from `/`, writes to the home directory and `/tmp`, and disables workspace restriction. `scripts/configure-picoclaw.sh` also adds the repo to write paths. | A new folder and an agent instruction alone cannot protect core files. |
| Service identity | `systemd/hosaka-webserver.service` has no `User=`; voice and PicoClaw units specify `operator`. | The web unit defaults to root unless overridden. Extension execution must never inherit that identity. |
| Provider setup | `hosaka/llm_setup.py` writes a private profile at `~/.hosaka/picoclaw/config.json` by default; v3 credentials go into its `.security.yml`. The Hosaka secrets store records the selected config path/model. | This newer provider flow is another important credential location beyond legacy `llm.json`. |
| Legacy credentials | `hosaka/secrets/store.py` defaults to `~/.hosaka/secrets.json`, optionally mirroring `/etc/hosaka/env`. `hosaka/llm/llm_config.py` stores keys in `llm.json` under an explicit state parent, otherwise `/var/lib/hosaka` if it exists, otherwise `~/.hosaka`. | The effective key depends on launch path, environment, and account. |
| Credential resolution | `hosaka/llm/openai_adapter.py` checks environment, `llm.json`, PicoClaw config, then PicoClaw security. Entry points can hydrate environment from Hosaka secrets first. | Report the effective source without revealing values; do not assume the first file an operator finds is authoritative. |
| Recent improvement | Latest audited commit isolates selected model credentials in temporary PicoClaw request overlays in `hosaka/llm/picoclaw_adapter.py`. | Preserve this behavior; overlays do not replace the need for one persistent credential owner. |

These are source-code findings. No live Raspberry Pi, installed credentials, running services, or printer were inspected.

## Proposed directory contract

Use `~/.hosaka` as the native user-data root to minimize churn in existing installs. Here `~` always means the explicitly selected operator account, including when setup uses sudo. An override is resolved once by a shared path module and passed to every entry point.

| Purpose | Canonical native location | Ownership/lifecycle |
| --- | --- | --- |
| Maintainer checkout | Any explicitly selected path, commonly `~/Hosaka` | Source mode uses it directly. It is not an extension workspace. |
| Installed appliance core | `/opt/hosaka-field-terminal` | Administrator-owned; read-only to normal runtime and extension processes. |
| Source launchers | `${HOSAKA_PREFIX:-~/.local}/bin/hosaka` and `picoclaw` | Source installer reports exact paths. |
| Appliance launchers | `/usr/local/bin/hosaka` and `/usr/local/bin/picoclaw` | Installer/service units use exact resolved paths. |
| Nonsecret settings | `~/.hosaka/config.json` | Install mode, operator, selected provider profile, directory overrides. |
| Persistent credentials | `~/.hosaka/secrets.json` | Sole Hosaka-managed authority; parent 0700, file 0600, atomic writes. |
| Provider metadata | `~/.hosaka/providers.json` | Provider, model, endpoint, credential reference; no key values. |
| Hosaka-owned PicoClaw config | `~/.hosaka/picoclaw/config.json` | Generated adapter configuration; preserve upstream version compatibility. |
| Agent memory, identity, sessions | `~/.hosaka/picoclaw/workspace/` | Persistent agent state, explicitly separate from project/extension source. |
| Installed extension packages | `~/.hosaka/extensions/<extension-id>/` | Independent packages/repositories; core update never synchronizes or deletes this tree. |
| Extension registry/lock | `~/.hosaka/extensions.lock.json` | Enabled state, grants, source/ref, installed version/digest, development links. |
| Extension data | `~/.hosaka/extension-data/<extension-id>/` | Separate from replaceable code; retained on ordinary removal. |
| Runtime state/logs | `~/.hosaka/state/`, `~/.hosaka/logs/` | Bounded logs; persistent state; runtime temp files outside code. |
| Game content root | `~/Games/Hosaka/` | Explicit configurable `HOSAKA_GAMES_DIR`; never inside the core repository. |
| PS1 content | `~/Games/Hosaka/roms/psx/` | Existing external libraries may remain referenced in place. |
| Game support data | `~/Games/Hosaka/bios/`, `~/Games/Hosaka/saves/` | Emulator adapters must actually route saves here or report their real path. |

The source and appliance modes share data semantics, not necessarily executable locations. Do not move data based on whether `/var/lib/hosaka` happens to exist. Machine boot settings may remain under `/etc/hosaka` and `/var/lib/hosaka`, but those are not an alternate credential store.

An extension author's working copy may be any independent repo, linked through `hosaka extensions link PATH`. The installed directory is a convenient default, not a requirement to fork Hosaka. Do not nest third-party development inside the main checkout.

Docker remains a supported compatibility mode. Document its host-to-container path mapping separately; a container path is not a host installation path. Do not rewrite working Docker mounts during the native extension milestone.

## Extension contract v1

Use the existing plan's `plugin.yaml` filename and call the user-facing feature “extensions.” Add a strict versioned schema. Discover manifests without importing or executing plugin code.

```yaml
schema_version: 1
id: halloween-citations
name: Halloween Citations
version: 0.1.0
kind: extension
requires:
  hosaka_api: 1
runtime:
  type: python
  entrypoint: main.py
commands:
  - name: cite
    description: Create a joke Halloween citation
    input_schema: schemas/cite.input.json
    output_schema: schemas/cite.output.json
permissions:
  - storage:self
limits:
  timeout_seconds: 10
  max_output_bytes: 65536
feature_ids:
  - extension.halloween-citations.cite
```

The example declares only local storage. Printing is an optional, separately granted core capability added after a real printer adapter exists.

Implementation requirements:

1. Validate IDs, schema/API versions, commands, referenced schemas, paths, and limits. Reject duplicate IDs and reserved names. Unknown permission types are errors.
2. Run each invocation as a supervised child process. Never dynamically import arbitrary extension Python into the terminal/web/voice process.
3. Resolve entrypoints relative to the package, reject escapes and unsafe symlinks, and invoke an argument vector without a shell. A manifest cannot select a host executable or grant itself privileges.
4. Use a small protocol: one JSON request on stdin, one JSON result on stdout, diagnostics on bounded stderr. Include protocol version, invocation ID, command, and validated arguments. Result includes success, structured data, display text, and structured error on failure.
5. Validate results in core. Escape control sequences before displaying third-party text in the terminal. Nonzero exit plus a success JSON is a failure, not a pass.
6. Bound wall time, output, concurrent invocations, memory and process creation where supported. Kill the entire child process group on cancellation/timeout, including descendants.
7. Keep dependency environments per extension, outside the core virtualenv. Package installation is explicit; discovery and boot never run install scripts or fetch dependencies. Pin dependencies and record hashes/refs.
8. For installation from a repository/archive, stage and validate paths before activation. Reject archive traversal and out-of-root symlinks. Record exact revisions; a moving branch name alone is not a release lock.
9. Enable/disable/remove/update an extension without rebuilding the frontend or restarting core. Disable immediately blocks new invocations and cancels its active jobs.
10. Use the same registry and dispatch from CLI, TUI, and PicoClaw agent operations. An ordinary extension cannot override settings, networking, update, secrets, shell, or other core commands.
11. Contribute namespaced records to `hosaka.obs.registry` from validated metadata. Do not call extension-supplied registration functions. Reject collisions: the current registry replaces duplicate records, so the extension adapter must enforce ownership before registration.
12. Extend the existing core catalog for the extension manager itself. External package manifests describe their own features; installing one must not edit `docs/hosaka.features.yaml`.

Proposed public commands, all NEW unless independently found in current code:

```bash
hosaka paths --json
hosaka extensions create halloween-citations
hosaka extensions link /absolute/path/to/halloween-citations
hosaka extensions list --json
hosaka extensions info halloween-citations --json
hosaka extensions validate /absolute/path/to/halloween-citations
hosaka extensions enable halloween-citations
hosaka extensions run halloween-citations cite --person Marco --reason "no costume"
hosaka extensions disable halloween-citations
hosaka extensions remove halloween-citations
hosaka safe-mode
```

TUI syntax: `/extensions run halloween-citations cite ...`. A convenience `/cite ...` alias may be granted by the owner, but cannot shadow core commands. The console gets a data-driven extension listing and renders validated results. No frontend build or GUI integration is required.

## Protecting core while allowing feature development

There are two separate release requirements: extension files survive core updates, and extension execution cannot modify core or access provider secrets. Directory separation satisfies only the first.

For the marketed Linux appliance:

- Run the web service and ordinary agent interactions as a configured unprivileged operator. Audit existing privileged operations and provide narrowly scoped helpers before changing the service user; preserve working Wi-Fi, Bluetooth, boot-mode, and game flows.
- Keep installed core and update machinery administrator-owned. Runtime must not have a general sudo path for copying arbitrary code into core.
- Run extension processes inside an OS-enforced boundary. A concrete native Linux option is Bubblewrap with private mount/process namespaces, no host network by default, a minimal read-only runtime/package view, private temporary storage, and only that extension's data directory writable. Verify the actual device supports the chosen mechanism before advertising containment.
- Hide the host home, secret stores, PicoClaw security files, arbitrary sockets, systemd control, Docker socket, and update tools. Sanitize inherited environment; a stripped API-key variable alone is insufficient if its backing file is readable.
- Core capabilities are request/response operations mediated by the parent, scoped to the invocation and permission grants. Any socket/token must be invocation-bound and must not expose a general host shell or unrestricted file API. Reject executable/escape sequences in printer payloads.
- Manifest permissions are requests. The owner's installed grants and enforced runner policy determine access. Editing `plugin.yaml` cannot escalate grants. Permission expansion on update requires owner acceptance.
- “Build this extension” should create a development session whose writes are confined to the chosen extension working copy and scratch data. Enforce that boundary for shell tools too. Existing PicoClaw write-path settings or a prompt saying “do not edit core” do not constrain arbitrary child shell commands.
- Keep maintenance/deployment operations outside extension-authoring sessions. A privileged coding session with a writable core checkout is a separate explicitly chosen workflow.

The Linux market-readiness gate requires real negative access tests. If the sandbox is unavailable, core should still boot and explain why protected extensions are unavailable. Do not silently launch them with unrestricted host permissions. macOS/Windows source use may initially support trusted extensions only; report that limitation instead of claiming identical protection.

Preserve the existing low-memory design. No new always-on extension daemon is required; reuse the existing web process for management and spawn bounded workers only on invocation.

## PicoClaw and credentials: one owner, explicit adapters

Implement shared resolution for operator, data root, provider selection, paths, and effective credentials. Native launchers, TUI/CLI, PicoClaw adapters, applicable services, and installer use it.

1. Hosaka owns persistent provider secrets in `~/.hosaka/secrets.json`. Provider metadata refers to a credential name, such as `OPENAI_MAIN`, without embedding its value. Keep the existing flat string store compatible where practical.
2. Move `PICOCLAW_CONFIG_PATH` and selected-model metadata out of the secrets dictionary into nonsecret configuration, with compatibility reads during migration.
3. Preserve PicoClaw v3 `.security.yml` support. Generate private adapter credentials in an owner-only runtime directory when invoking PicoClaw; remove ephemeral copies after use. If a gateway needs a persistent generated sidecar, explicitly label it a derived cache, refresh atomically, and test rotation/restart. Do not call it an independent authority.
4. Retain the latest selected-model request overlay behavior. Do not rewrite an unrelated user's global PicoClaw config or merge other model credentials into an extension execution environment.
5. Existing independently managed `~/.picoclaw` belongs to upstream PicoClaw until an explicit migration/import. New Hosaka installs use the Hosaka-owned path. Update identity/skill bootstrapping to accept the resolved PicoClaw home, instead of hardcoding `home/.picoclaw`.
6. Eliminate automatic root-home bootstrap for normal appliance operation. Resolve the configured operator explicitly. No root/operator guessing based on hardcoded `/home/operator` directories.
7. Stop treating `/etc/hosaka/env` as a second editable credential authority. Keep nonsecret service settings there; use the shared credential resolver or a deliberately generated restricted adapter. Never hydrate all secrets into every child environment.
8. Define precedence visibly: explicit process override for the trusted core, selected profile's canonical credential, then a documented migration-only legacy fallback. Production launchers should not inherit unrelated provider overrides accidentally. `hosaka doctor` reports the winning source and conflicts, never the secret.
9. Diagnostics report presence, effective provider/model, resolved paths, owner, permissions, and whether a real provider check ran. Separate “configured” from “request verified.” Do not hardcode a required OpenAI key for Anthropic/local-only users.

Migration must inventory all currently supported locations: `~/.hosaka/secrets.json`, selected `~/.hosaka/picoclaw/config.json` and `.security.yml`, legacy user/system `llm.json` including saved profiles, `~/.picoclaw/config.json` and `.security.yml`, configured environment files, and explicit overrides. Preserve provider/model choices and sessions. Never print key values or place them in shell arguments, Git history, logs, or crash bundles.

If sources disagree, show a redacted conflict and ask the operator which source to import. Do not silently guess. Back up protected files, write canonical state atomically, validate it, then switch adapters. Migration is versioned, resumable, and idempotent. Legacy copies are not deleted merely because an import succeeded; provide a deliberate cleanup step after verified operation, with backup locations clearly reported.

## Installer and games requirements

Root `install.sh` becomes the documented native source entry point. Appliance setup delegates to the same path/runtime initialization, plus its existing boot/service provisioning. Keep explicit mode selection rather than having one script unexpectedly alter desktop boot.

On first install and rerun:

- Resolve operator, install mode, source/runtime directories, binary paths, data root, extension root, and games root once.
- Create external directories with correct ownership. Generate a short README and extension-authoring agent instructions outside core. Never overwrite user extensions, games, sessions, or existing settings.
- Write an installation record sufficient for `hosaka paths --json` and support diagnostics. Detect multiple `hosaka`/`picoclaw` binaries on PATH and report the exact executable services will use.
- Initialize manifest discovery, shared dispatch, and agent-accessible list/run operations. Creating an empty directory does not complete installation of the extension feature.
- Add extension discovery to TUI help/list surfaces through a registry. The second extension must require zero core code edits.
- Make the existing PS1 CLI/TUI/agent launcher resolve the same game root. Preserve `HOSAKA_PSX_ROMS` as a compatibility override.
- If an old ROM directory is populated, record its path and continue using it until the operator chooses relocation. Do not move/copy/delete a potentially large library automatically.
- Preserve `/play list psx`, `/play <title>`, `hosaka play twisted metal`, stop behavior, public-host restrictions, and current RetroArch integration. Do not convert ROMs into extensions or expand scope to legacy GUI arcade games.
- Never put user content under a deployment target covered by `rsync --delete`.
- Finish with concrete path output and offline checks. No successful-install claim if the selected runtime cannot load its registry or the launcher points to the wrong copy.

## First external extension: Halloween joke citations

Deliver the example as a self-contained folder that can become its own GitHub repository. Installing it on a clean Hosaka should require no Hosaka fork and no additional core code changes.

Minimal behavior:

- Input: optional person's name, one or more reason codes, optional note, optional issuing nickname.
- Included reasons: `no-costume` → “No costume”; `drank-too-much` → “Drank too much”; allow owner-edited reason text in the extension's own configuration.
- Output: a readable novelty citation with local citation number, date/time, selected offenses, and a clear Halloween joke label. Use deterministic templates; no LLM or API key required.
- Save structured JSON and a plain-text receipt in the extension's data directory. Text output is mandatory; HTML is optional and must be rendered safely.
- A user should be able to edit reasons/templates and rerun it without editing core or rebuilding the frontend.
- A printer is an optional follow-up adapter: preview first, print only when requested, return a real spool/job result, and never report “printed” merely because text was generated. No printer implementation was established by this audit.
- Example calls: cite Marco for “no costume”; cite a friend for “drank too much”; create an unnamed citation. State the configured local timezone explicitly on receipts.
- Removing the package removes its commands. Saved receipts remain until an explicit data-purge action.

The example's source and user-facing templates must not be compiled into core. A reference copy may live in examples for documentation, but the acceptance test installs from outside the Hosaka checkout.

## Implementation sequence and likely files

Before code changes, follow `docs/issue-tracking.md`: find/reuse a matching issue or create one. This brief does not create issues, comments, branches, or pull requests.

| Milestone | Concrete output | Likely code seams |
| --- | --- | --- |
| 1. Paths and migration | Shared resolver, installation record, `paths --json`, redacted inventory/dry run | New `hosaka/paths.py`; `install.sh`; `scripts/hosaka`; native setup/bootstrap; `hosaka/picoclaw_runtime.py` |
| 2. Credential ownership | Profile references, canonical resolver, private PicoClaw adapters, consistent operator | `hosaka/secrets/`; `hosaka/llm_setup.py`; `hosaka/llm/llm_config.py`; OpenAI/PicoClaw adapters; service units |
| 3. Extension manager | Schema, discovery, per-package env, registry/lock, install/link/enable/disable/run, safe mode | New `hosaka/extensions/`; `hosaka/__main__.py`; `scripts/hosaka`; `hosaka/tui/terminal.py`; feature registry/catalog |
| 4. Protected execution | Linux runner and permission broker, bounded failure handling, restricted development session | Runner module; service permissions; existing shell/PicoClaw launch seams; explicit platform capabilities |
| 5. Shared surfaces | TUI help/list/run commands and PicoClaw-accessible dispatch; preserve hosted restrictions | `hosaka/main_console.py`; CLI router; shared extension dispatcher; PicoClaw skills |
| 6. Games/apps | Existing RetroArch regression checks; separate Foliate/optional VS Code launch integration | `hosaka/play.py`; `hosaka/games.py`; `hosaka/apps.py`; `skills/hosaka-games/SKILL.md` |
| 7. External proof | Halloween package, editable templates, receipts, independent author workflow | External example project, not core feature implementation |
| 8. Release qualification | Clean installs/upgrades, core integrity evidence, rollback, user/agent docs | Existing install/LLM/game tests; new contract/integration tests; generated docs pipeline |

Keep these as reviewable changes, not a simultaneous rewrite. Existing observability should record extension lifecycle metadata and failures with bounded/redacted payloads; do not make logging a prerequisite for core startup or successful invocation.

## Acceptance tests and release gates

Record actual commands, exit codes, versions, artifacts, and device results. A unit test passing is not evidence of a verified Pi boot, successful provider call, or printed receipt.

1. Fresh native source install and fresh appliance install create the documented folders and resolve operator-owned PicoClaw state. Repeat installation; settings, extension files, receipts, ROM references, saves, and sessions are unchanged.
2. Upgrade representative old layouts and rerun migration. Test conflicting credential sources, a nonstandard operator name, nondefault data root, paths with spaces, and read-only parent directories. A partial failure leaves the previous installation usable.
3. Install the Halloween package from an independent temp directory/repo; list and run it through CLI, TUI, and shared PicoClaw dispatch. It works offline with no provider key. Validate structured receipt fields and edited template output, not just a zero exit code.
4. Install a second small extension without editing/rebuilding core. Verify Flatpak app manifests and the RetroArch ROM catalog remain distinct from extension discovery.
5. Verify existing PS1 list, matching, ambiguous title handling, launch failure, confirmed launch, and stopping still work. Hardware smoke testing confirms real RetroArch behavior and save paths.
6. A malformed manifest, unsupported version, ID/command collision, escaping path, symlink escape, invalid output, nonzero exit, timeout, output flood, or child-process leak cannot crash/block the terminal or web service. Public mode rejects extension execution unless expressly supported and authorized.
7. Linux isolation tests actively attempt writes to installed core, the developer's core checkout, another extension, and system configuration; attempts fail. Reads of canonical credentials, PicoClaw sidecars, and unrelated home files fail. Forbidden network/socket access fails. Spawned children inherit the boundary.
8. Extension-authoring sessions can edit the selected external project and cannot modify core even through shell commands. Confirm with attempted writes and before/after hashes, not just agent promises or tool configuration inspection.
9. Credentials rotate once and take effect consistently in TUI/CLI and PicoClaw. Explicitly test OpenAI, Anthropic, and a local compatible provider, preserving selected-model overlay isolation. Use mocks in CI and owner-run real provider smoke checks separately.
10. Core update/rollback leaves extension code/data and games untouched. Extension update can roll back its code without silently downgrading incompatible data; extension data migration must back up and document downgrade support.
11. Disable/removal stops invocation and removes aliases/tools/help entries; safe mode starts with all third-party execution disabled and allows diagnosis. Missing sandbox/dependency/printer produces an actionable failure with core still usable.
12. A clean external-author workflow leaves `git status --porcelain` empty in the Hosaka checkout and the installed core digest unchanged. Only the external package and its allowed data change.

Start with existing relevant suites: source/appliance installer tests, `test_llm_setup.py`, `test_picoclaw_runtime.py`, `test_play.py`, games/menu/API tests, and registry/observability smoke tests. Determine and run the repo's actual frontend checks when UI changes are made. This audit did not run them because no implementation was changed.

The final release report must list implemented behavior, migration coverage, verified platforms/hardware, measured resource use on the target Pi, remaining limitations, and rollback instructions. Linux containment and actual clean-install/upgrade evidence are required before describing this build as ready for market.
