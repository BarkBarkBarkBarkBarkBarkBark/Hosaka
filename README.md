# Hosaka Field Terminal

```
  ██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗
  ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗
  ███████║██║   ██║███████╗███████║█████╔╝ ███████║
  ██╔══██║██║   ██║╚════██║██╔══██║██╔═██╗ ██╔══██║
  ██║  ██║╚██████╔╝███████║██║  ██║██║  ██╗██║  ██║
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
```

A terminal-first AI workspace for your laptop, Raspberry Pi, or cyberdeck.
Type normally to talk to an agent that can use tools and work on files.
The Python TUI is the app; the optional React/Electron host adds a small
**Menu**, not a second chat interface.

An alien plant grows as you use the terminal and wilts when you leave it.
There is no wrong way.

## Start here

| I want to... | Go to |
| --- | --- |
| Try Hosaka without building it | [Docker install](#install-in-one-line) |
| Run the current source on my machine | [Source install](#install-from-source-macos--linux) |
| Configure a provider or local model | [Model setup](#set-up-a-model-and-api-key) |
| Set up a dedicated Raspberry Pi | [Appliance setup](#raspberry-pi-appliance) |
| Build an application for Hosaka | [Extensions](#extensions) and the [extension agent guide](docs/extensions/AGENT_GUIDE.md) |
| Change Hosaka core as a coding agent | [AGENTS.md](AGENTS.md), then [development](#development-and-agent-navigation) |
| Diagnose an existing installation | [Paths and diagnostics](#paths-and-diagnostics) |

This README describes the source in this checkout. Docker `:latest` is the
last successfully verified `main` image, not necessarily the newest commit.
Check the [image workflow](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/actions/workflows/image.yml)
before assuming a pushed feature is available to Docker users.

## Install in one line

Requires [Docker](https://www.docker.com/products/docker-desktop/) installed
and running. This installs a Docker-backed CLI, **not native Pi services or
fullscreen boot**.

**macOS / Linux**

```bash
curl -fsSL https://install.hosaka.xyz | sh
```

**Windows PowerShell**

```powershell
iwr https://install.hosaka.xyz/windows | iex
```

Then, in a terminal:

```bash
hosaka configure llm --provider openai --model gpt-4.1
hosaka tui
```

Setup prompts privately for the API key. Choose a model available to your
account; see [model setup](#set-up-a-model-and-api-key) for other providers.
`hosaka tui` attaches to a running local container or starts a disposable one
with the same persistent state. A continuously running node is optional:

```bash
hosaka up       # start the local web backend on http://127.0.0.1:8421
hosaka open     # open the local web UI in a browser
hosaka status
hosaka down
```

Use `hosaka tui` for the container's interactive terminal. Publishing a web
port does not relax the native browser PTY's loopback-only access policy.

Installers download the image before reporting success and refuse to replace
an existing non-Docker Hosaka installation. Use the existing installation's
update path instead. See [installer details](install/README.md) for locations,
Windows behavior, overrides, and launcher updates.

### Container workspaces

The default private workspace persists at `~/.hosaka/workspace`. To share an
existing host project, stop the node before changing mounts:

```bash
hosaka down
hosaka workspace ~/your-project                # read-only at /workspace
hosaka tui
```

Use `hosaka workspace ~/your-project --read-write` to explicitly permit edits,
or `hosaka workspace clear` to return to the private writable workspace.
Only the selected folder is shared; symlinks do not expose outside host paths.
Agent identity, memory, and sessions use a separate writable runtime workspace.

**Read-only sharing prevents project edits, not network access or writes to
private container state. Docker is not a complete security sandbox.** Do not
mount your entire home or the Docker socket for an untrusted agent.

`hosaka link HOST` routes browser/status commands to another node, not the
native TUI. For a remote terminal, SSH to that machine and run `hosaka tui`.
Use `hosaka unlink` to return the Docker client to its local node.

## Install from source (macOS / Linux)

Requires Python 3.10+, Git, and internet access. Run as your normal user,
**not sudo**:

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
hosaka doctor --offline
hosaka tui
```

Open a new terminal, or source the shell startup file printed by the installer:

```bash
hosaka configure llm --provider openai --model gpt-4.1
cd ~/your-project
hosaka tui
```

The [source installer](install.sh) creates a repo-local Python environment,
installs or upgrades PicoClaw to a config-v3-compatible release (0.3.1+),
seeds Hosaka's agent runtime, and adds a launcher under `~/.local/bin`.
Keep the checkout: the launcher uses it directly. `HOSAKA_PREFIX` changes the
launcher prefix.

For the graphical TUI + Menu host, install Node.js/npm and use
`bash install.sh --gui`, then `hosaka gui`. Bare-terminal installs need neither
Node nor a desktop session. This user-level setup does not configure boot or
system services.

**Source agents run with your host user's permissions.** The calling directory
is the TUI's project workspace, not an isolation boundary.

## Set up a model and API key

These commands work with source and Docker-client installations:

```bash
hosaka configure llm --provider openai --model gpt-4.1
hosaka configure llm --provider anthropic --model claude-sonnet-4-5
hosaka configure llm --provider openai-compatible --model YOUR_MODEL \
  --api-base https://your-provider.example/v1
```

Run **one** setup command for the provider/model you want. It prompts for the
key without echoing it and selects a private PicoClaw profile. Do not put keys
in shell arguments, source files, or issue reports. Profiles are private files,
not encrypted storage; protect your account and backups.

For a local OpenAI-compatible server, use `--no-key` if it needs no credentials.
Inside Docker, `localhost` means the container; Docker Desktop commonly exposes
host services at `http://host.docker.internal:11434/v1`.

Restart `hosaka tui`, then use `/llm` to test a request. Setup does not contact
the provider or prove key/model access. Agent requests go to the selected
provider and may incur charges.

In the TUI, `/select llm` lists choices; `/select llm <number>` selects from
the last displayed list. `/help` and `/commands` show the active command map.
Console AI uses **PicoClaw's agent harness and tools**, not a direct-completion
fallback. A gateway process is not required for console chat.
See [PicoClaw backend notes](docs/picoclaw_cli_backend.md) for session behavior,
request overlays, and advanced configuration.

## The TUI, Menu, and applications

- **Terminal:** normal text goes to the agent. Use `/help` for commands and
  `/plant` to check your plant. The graphical host embeds this same Python TUI.
- **Menu:** device controls, games, flash overlay, and enabled extensions.
  Linux networking uses NetworkManager; Bluetooth uses BlueZ. Unsupported host
  operations report errors rather than simulated devices.
- **Extensions:** independent application packages with host-rendered views;
  see [below](#extensions). Opening or closing one preserves the terminal.
- **Games:** a separate native PS1 launcher using RetroArch. Use
  `hosaka play list psx`, `hosaka play spyro`, and `hosaka play stop`, or `/play`
  in the TUI. Ambiguous names return matches rather than guessing.
- **External applications:** `hosaka launch` lists configured Flatpak-backed
  targets. These are not extensions and are managed separately.

Games require a graphical session, RetroArch, a compatible PS1 core, and your
own local games/BIOS. Nothing downloads or bundles ROMs or BIOS. Existing RetroPie
configuration is reused; `HOSAKA_PSX_ROMS` and `HOSAKA_PSX_CORE` provide explicit
overrides. Game libraries are not relocated during initialization.

The independent desktop/arcade, app-store/webview bridges, and browser voice UI
are [archived](archive/desktop-frontend/), not alternate supported routes.
The optional [native voice backend](docs/voice.md) is separate from console chat.

## Extensions

Build ordinary applications **outside this core checkout**. Start with the
[agent guide](docs/extensions/AGENT_GUIDE.md), [implemented v1 specification](docs/extensions/SPECIFICATION.md),
[security boundary](docs/extensions/SECURITY.md), and
[reference package](examples/extensions/reference-extension/).
The canonical manifest is `extension.yaml`.

```bash
hosaka extensions list --json
hosaka extensions create my-extension --path /absolute/path/to/my-extension
hosaka extensions validate /absolute/path/to/my-extension
hosaka extensions info my-extension --json
hosaka extensions doctor --json
```

Installers seed a validated reference package, disabled and without grants.
Discovery and validation do not import package code, run its tests, or install
dependencies. Existing package source, data, approvals, and enablement survive
initialization.

After inspecting the source, the **owner** can approve the current digest,
grant storage, and separately enable the package:

```bash
hosaka extensions trust my-extension --trusted-local --allow-storage
hosaka extensions enable my-extension
hosaka extensions run my-extension echo --params '{"message":"Hello"}'
```

These execution examples require an unprivileged local runtime. Enabled
packages appear in **Menu → Extensions** when the web backend also runs as the
configured unprivileged operator. Root-run Docker/appliance backends cannot
execute them; do not bypass that restriction.

**Trusted-local is not an OS sandbox.** Approved Python retains your user's
file, network, and process privileges, including access to readable credential
files. Sanitized worker environments do not hide those files. Root/public
execution is refused. New code needs reapproval; no installer or web API
silently approves, grants permissions, or enables a package.

Implemented capabilities include bounded workers, schema-validated actions,
declarative forms/tables/navigation/lookups, and text persistence. Optional
managed data directories, network grants, background actions, and binary
upload/download controls have separate opt-in permissions; see
[persistent and background capabilities](docs/extensions/PERSISTENCE.md).
Application schemas, migrations, authentication, and sync remain package-owned.
No per-package frontend route or core edit is needed.

Use `hosaka extensions disable ID` or `hosaka extensions revoke ID` to stop
execution; `hosaka extensions safe-mode on` blocks and cancels all extension
jobs. `remove ID` unregisters a package but retains its source and data.
The same commands are available after `/extensions` in the TUI.

**Not implemented:** OS-enforced confinement, per-package dependency environments,
dedicated PicoClaw extension tools, `extensions test`, or archive upgrades and
rollback. Trusted-local tests are not clean-device or protected-runtime
qualification. Use the implemented specification, not the full
[roadmap](docs/extension_plan.md), as the current API contract.

## Raspberry Pi appliance

Native setup is a **system-changing path for a dedicated Linux device**, not
the laptop/Docker installer. From a checkout, with a compatible PicoClaw on PATH:

```bash
./scripts/setup_hosaka.sh
```

Read the [setup script](scripts/setup_hosaka.sh) and
[native installer](scripts/install_hosaka.sh) before running them. They provision
the runtime and system services; graphical mode requires a working display
session. Boot choices are `kiosk`, `headless`, or `console`. A graphical appliance
defaults to **TUI + Menu**, preserving saved display/session choices on updates:

```bash
hosaka tui           # bare terminal, including over SSH
hosaka gui           # graphical TUI + Menu
hosaka display show
hosaka display gui   # graphical-login preference
hosaka display tui   # opt into a bare-TUI launcher
```

Use `hosaka mode device --persist` for an SSH/build-oriented device, and
`hosaka mode console --persist` to restore the graphical host.
See [modes](docs/modes.md), [Wi-Fi](docs/wifi.md),
[remote operator client](docs/client.md), and [kiosk setup](kiosk/README.md).

### One-command Raspberry Pi updates

```bash
hosaka update
hosaka update logs
hosaka update status
```

On a systemd appliance, updates run as an independent journaled job. They
fast-forward the clean checkout, build/deploy, restore services and the selected
display mode, and verify backend health and the served frontend stamp.
Disconnecting SSH does not cancel the job; check status for the actual outcome.
Updates refuse local changes, including untracked files.

For an older installed CLI that lacks this update worker, bootstrap once from
your actual clean checkout:

```bash
cd ~/Hosaka
git pull --ff-only origin main
bash scripts/hosaka update
```

**Update commands differ by installation:** Docker `hosaka update` refreshes
the image (re-run its installer to refresh the launcher); source
`hosaka update` fast-forwards the checkout and re-runs its installer; appliance
`hosaka update` builds and deploys system services. Do not replace an appliance
CLI with the Docker installer.

## Paths and diagnostics

```bash
hosaka paths --json
hosaka doctor --offline --json
hosaka doctor --offline --strict
hosaka migrate --dry-run --json
```

Use resolved paths, not guessed operator homes. `HOSAKA_DATA_DIR` overrides the
native data root; `HOSAKA_OPERATOR` selects an existing account. The versioned
`installation.json` record is nonsecret. Extensions keep replaceable code
separate from `extension-data/ID` and bounded metadata logs.

The new path layout **does not consolidate every legacy credential, PicoClaw,
log, or state location**. Migration is read-only inventory, not an apply command:
it reports sources/conflicts without exposing key values or moving files.
Do not infer completed provider migration from the paths report.
Docker diagnostics inspect container storage, not host PicoClaw configuration.
See [doctor](docs/doctor.md) for online profiles and structured reports.

## Development and agent navigation

Read [AGENTS.md](AGENTS.md) first. For nontrivial core work, follow
[issue tracking](docs/issue-tracking.md), reuse existing helpers, and run focused
tests. Do not automatically approve extensions, migrate credentials, deploy,
or commit on the operator's behalf.

For local GUI development after `bash install.sh --gui`:

```bash
hosaka dev          # backend + Vite + Electron; reuses a responsive session
hosaka dev --web    # browser-only host for UI debugging
hosaka down         # stop the local dev session
```

`hosaka dev -fresh` explicitly restarts the local backend/frontend pair and can
disconnect an active TUI. For an existing manually provisioned checkout,
[install-local-cli.sh](scripts/install-local-cli.sh) installs only the launcher;
it is not a replacement for dependency setup.

| Surface | Source / contract |
| --- | --- |
| Canonical terminal and command dispatch | [hosaka/main_console.py](hosaka/main_console.py) |
| Native/source CLI; Docker client | [scripts/hosaka](scripts/hosaka), [install/](install/) |
| Provider setup and agent routing | [llm_setup.py](hosaka/llm_setup.py), [PicoClaw adapter](hosaka/llm/picoclaw_adapter.py) |
| Native paths and migration inventory | [paths.py](hosaka/paths.py), [migration.py](hosaka/migration.py) |
| TUI + Menu host and native PTY | [frontend/src/](frontend/src/), [kiosk/](kiosk/), [tui_ws.py](hosaka/web/tui_ws.py) |
| Extension runtime, API, and views | [hosaka/extensions/](hosaka/extensions/), [extensions_api.py](hosaka/web/extensions_api.py), [extension renderer](frontend/src/extensions/) |
| Runtime identity, task policy, and skills | [identity/](identity/), [manager/](manager/), [skills/](skills/), [runtime generator](scripts/bootstrap_picoclaw_runtime.py) |
| Feature metadata and generated references | [feature catalog](docs/hosaka.features.yaml), [agent context](docs/agent_context.json), [OpenAPI](docs/openapi.json) |
| Focused validation | [tests/](tests/), [extension test guide](docs/extensions/TESTING.md), [native host tests](kiosk/tests/) |

The feature catalog owns core feature metadata. Regenerate its derived docs
with `PY=.hosakavenv/bin/python bash scripts/gen_docs.sh` (substitute `.venv`
if that is your checkout's environment); do not hand-edit generated files.
See the [API reference](docs/api.md) and [user manual](docs/manual/index.md).
The [published documentation](https://barkbarkbarkbarkbarkbarkbark.github.io/Hosaka/)
can lag source; check the [docs workflow](https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/actions/workflows/docs.yml).

### Hosted terminal is a separate deployment

The [hosted wrapper](https://github.com/BarkBarkBarkBarkBarkBarkBark/hosaka-field-terminal)
owns [terminal.hosaka.xyz](https://terminal.hosaka.xyz), copying this repository's
frontend at build time. The
[marketing site](https://github.com/BarkBarkBarkBarkBarkBarkBark/cyber_deck)
embeds it; neither is a second canonical terminal implementation.

The hosted design runs the real TUI behind an access-code gate in disposable
per-session Machines with bounded model access and no persistent workspace or
deck hardware. Its release/deployment does not automatically follow this repo.

**Keep the native `/ws/tui` loopback-only and disabled in public mode.**
Hosted builds select a separate `VITE_HOSAKA_TUI_URL` gateway; never loosen the
native PTY policy to serve a public terminal. Hosted isolation and credential
boundaries belong to the wrapper, not a shared host shell.
