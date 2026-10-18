# HOSAKA — Extensible Application Platform
## Implementation handoff for autonomous coding agents

**Target branch:** `dev`  
**Repository:** `BarkBarkBarkBarkBarkBarkBark/Hosaka`  
**Objective:** Implement a stable, self-documenting extension platform that enables future coding agents to build and deploy new Hosaka functionality entirely through standalone extension packages.

**Primary constraint:** After this infrastructure task is complete, ordinary application development must not require modifying Hosaka core source files.

## Reconciled implementation checkpoint — 2026-10-18

This document is the extension-platform roadmap. Its full definition of done is
not a claim that all phases have shipped. Track the first authoring slice in #32;
#31 owns the native replication foundation. Execution and Menu views are #33.

### Current execution/UI checkpoint

Authoring is now committed at `0baf7a99` on `dev`. Following explicit operator
approval, #33 adds **trusted-local** execution and declarative Menu views together.
This mode requires per-package code-digest approval, a separate storage grant
and enablement; new installations remain disabled/unapproved. Root/public
execution is refused. The operator explicitly accepted that this is NOT an
OS sandbox; Linux protected execution remains a separate release requirement.

The shared runner validates inputs/outputs, snapshots approved source, supervises
bounded stdlib workers and records private bounded metadata logs. Safe mode,
disable/removal/revoke and caller cancellation stop active invocations. One
guarded API supplies enabled views and actions to the host-owned renderer;
CLI/TUI use the same runtime. No package-authored HTML/JS or per-package routes.
The canonical terminal stays mounted while Menu views are used.

The following slice-A notes are historical. Their execution/UI-unavailable
statements are superseded by this checkpoint and the implemented specification.
Remaining work includes OS containment, dependency environments, dedicated
PicoClaw tools, archives/upgrades and complete external Halloween/device proof.

Verified locally: 379 focused Python tests, real CLI/TUI/API dispatch, source and
client regressions, frontend type-check/build, rebuilt/live Docker integration,
real non-root Linux workers, and browser echo/persistence/error/cancellation.
A second package appeared and executed without rebuilding the frontend or
changing core; disable removed navigation without remounting the terminal.
The native backend was restarted only after explicit operator approval; the
updated Menu is available on port 8421. Native packages remain unapproved and
disabled. These execution/UI changes are uncommitted and are not a protected
runtime or physical-device release qualification.

Current source baseline is `dev` at `5f254629`: shared paths/installation
records, CLI/TUI path diagnostics, read-only migration inventory, and graphical
TUI + Menu supervision are committed. No extension loader or runner existed at
that baseline. Runtime provider ownership is still transitional.

### Authority and compatibility

- The Python TUI remains canonical. React/Electron remain its thin TUI + Menu
  host. A declarative extension view will be an optional host-owned surface,
  not a resurrection of the retired desktop/arcade or a second chat application.
- This newer plan supersedes the older brief's **unimplemented** `plugin.yaml`
  proposal: the canonical filename is `extension.yaml`, with schema version 1
  and `requires.hosaka_api: 1`. Do not maintain two competing loaders.
- The callable `run(action, params, context)` describes the package interface,
  not permission to import package code into core. Execution must use a
  supervised process and versioned JSON stdin/stdout protocol.
- Add explicit `actions` with package-relative JSON input/output schema files,
  and bounded `limits`, to the manifest shown below. Declarative button actions
  must name one of these actions. Bindings are simple `params.<input-id>` or
  `result.<field>` references, never executable expressions.
- Keep the Flatpak launcher and native RetroArch ROM subsystem independent.
  Use `hosaka.paths`; preserve packages, data, enabled state and grants on rerun.
- `scientific_workstation.md` is a separate proposed Neurodeck extraction
  charter, not Hosaka implementation status. No monorepo extraction, SAW
  service runtime, Postgres, webview embedding or capture service is part of
  this extension milestone. Its historical desktop/router assumptions must
  not override the actual TUI/PicoClaw architecture.
- Standalone upstream `~/.picoclaw` is not an extension workspace. No provider
  import is required for offline scaffolding/validation; credential containment
  remains a prerequisite to claiming protected extension execution.

### Reviewable delivery slices

| Slice | Deliverable | Explicit boundary |
| --- | --- | --- |
| A — authoring foundation (#32) | Strict manifest/action-schema/declarative-UI validation; no-import discovery; private registration metadata; init/create/link/list/info/validate/enable/disable/remove/doctor; reference source and standalone tests; shared bootstrap and agent guide | Packages can be authored and validated. No host invocation, renderer, permission enforcement or extension test runner is claimed. New packages are disabled with no grants. |
| B — supervised execution | Versioned request/result protocol, narrow data/log context, input/output validation, bounded subprocesses, cancellation, safe mode and explicit platform policy | A subprocess is not an OS sandbox. Do not silently fall back to unrestricted execution. |
| C — generic surfaces | Authenticated generic API, dynamic declarative Menu views, action/result rendering and shared PicoClaw dispatch | Preserve hosted restrictions and existing terminal state; no per-extension core edits. |
| D — end-to-end proof | Reference demonstrates every supported host capability; separate Halloween package plus a second extension; update/rollback and clean-install/device qualification | Only this evidence can satisfy the complete definition of done below. |

Sections 4, 8 and 14 describe the completed platform. During slice A the reference
has real standalone echo/persistence/error actions and local tests, but is seeded
disabled and is **not executable through Hosaka**. Bootstrap validates manifests
and discovery without importing code or running package tests. `extensions test`,
`run`, UI menus, grants, safe mode and install/update-from-archive are not
advertised as working until their respective implementations exist.

### Slice A result

Implemented on 2026-10-18 and committed as `0baf7a99`: the authoring
commands in slice A, strict metadata validation, standalone reference and shared
source/appliance/Docker bootstrap. The native reference is now installed under
the resolved extensions root, disabled with no grants; native `extensions doctor`
passes. Existing installation/provider/PicoClaw bytes and modes were unchanged.

Verification: 284 focused Python tests passed, including reference/scaffolded
second-package standalone suites. Source-install preservation/failure checks,
Bash/PowerShell client checks (PowerShell on Linux), Docker build with frontend
type-check/build, live container reference/persistence/provider regressions and
public bootstrap/management-denial checks passed. Pylance diagnostics and shell
syntax checks passed. Context-hub validation is recorded with the handoff.

The full definition of done below is still **not complete**. The subsequent
trusted-local execution/UI slice is described above; OS containment and full
external proof remain separate gates.

Use [extensions/AGENT_GUIDE.md](extensions/AGENT_GUIDE.md) and
[extensions/SPECIFICATION.md](extensions/SPECIFICATION.md) for the implemented
contract. The older market brief remains the appliance/release gate reference.

---

# 1. Project philosophy

Hosaka should operate as an extensible application platform rather than a monolithic application.

The platform is divided into two layers:

**Hosaka Core**
- Owns the application shell, navigation, styling, API infrastructure, security, configuration, installation, extension management, and lifecycle.
- Provides stable interfaces that extensions can use.
- Must remain functional when extensions are absent, invalid, disabled, or crashing.

**Hosaka Extensions**
- Own all optional, user-facing functionality.
- Are independently discoverable, executable, testable, and removable.
- Must not directly import, alter, or patch the core UI.
- Must not require changes to central route-registration or menu-registration files.
- Must use the documented extension interfaces for all interaction with Hosaka.

The goal is to support a development workflow in which a user describes desired functionality in natural language and an AI agent creates an extension that implements it.

The developer should not need to understand the entire Hosaka codebase.

**Design rule: If adding an ordinary extension requires editing `hosaka/`, `frontend/src/`, or `kiosk/`, the extension platform is incomplete.**

The exception is an explicitly authorized platform/API upgrade, which must have its own tests and compatibility considerations.

# 2. Inspect and preserve the existing architecture

Before implementation:

1. Inspect the current `dev` branch.
2. Identify existing installation modes, runtime paths, UI components, API authentication, application catalogs, games, and PicoClaw integration.
3. Review the existing `hosaka/paths.py` and its canonical data directories.
4. Review the root `install.sh` as well as other installation entrypoints.
5. Examine existing tests and preserve their behavior.

Do not replace working architecture unnecessarily.

Hosaka already defines directories resembling:

- `extensions/`
- `extension-data/`
- `state/`
- `logs/`
- `extensions.lock.json`

Reuse the canonical path resolver.

Do not create a competing path-discovery mechanism or assume every installation lives at a particular hardcoded location.

Do not confuse the existing Flatpak application registry with this new extension platform. The Flatpak system may continue to operate independently.

# 3. Target directory architecture

Maintain a clear separation between source-controlled examples, locally installed extensions, and persistent application data.

Repository structure:

```text
Hosaka/
├── hosaka/
│   └── extensions/
│       ├── discovery.py
│       ├── manifest.py
│       ├── manager.py
│       ├── runner.py
│       └── permissions.py
│
├── frontend/
│   └── src/
│       └── extensions/
│           ├── ExtensionHost.tsx
│           ├── ExtensionMenu.tsx
│           └── ExtensionRenderer.tsx
│
├── examples/
│   └── extensions/
│       └── reference-extension/
│           ├── extension.yaml
│           ├── main.py
│           ├── ui.yaml
│           ├── README.md
│           ├── AGENT_CONTEXT.md
│           └── tests/
│
├── docs/
│   └── extensions/
│       ├── README.md
│       ├── AGENT_GUIDE.md
│       ├── SPECIFICATION.md
│       ├── SECURITY.md
│       └── TESTING.md
│
├── tests/
│   └── extensions/
│
└── install.sh
```

Installed structure, relative to the canonical Hosaka data directory:

```text
~/.hosaka/
├── extensions/
│   ├── reference-extension/
│   │   ├── extension.yaml
│   │   ├── main.py
│   │   ├── ui.yaml
│   │   ├── README.md
│   │   ├── AGENT_CONTEXT.md
│   │   └── tests/
│   │
│   └── custom-extension/
│       ├── extension.yaml
│       ├── main.py
│       └── ui.yaml
│
├── extension-data/
│   ├── reference-extension/
│   └── custom-extension/
│
├── state/
├── logs/
└── extensions.lock.json
```

`~/.hosaka/` is illustrative, not a hardcoded path.

The canonical path resolver determines actual locations.

The repository's example is the canonical, version-controlled template. The installed example is a usable copy.

Persistent extension data must never live inside the extension source directory.

# 4. Installation and upgrade behavior

**Updating `install.sh` is a mandatory deliverable, not an optional follow-up.**

Update the root installer so every successful source installation includes extension initialization.

Required behavior:

1. Resolve the canonical Hosaka data directory.
2. Create the extensions directory.
3. Create the extension-data directory.
4. Create required state and log directories.
5. Initialize extension registration metadata if absent.
6. Seed a fully working reference extension.
7. Validate the seeded extension.
8. Verify that the extension manager can discover it.
9. Report initialization and validation results.

Implement this as an idempotent bootstrap routine that can also be called independently from the installer.

For example:

```text
hosaka extensions init
hosaka extensions validate
hosaka extensions list
hosaka extensions doctor
```

The same bootstrap routine must be reusable by other supported installers rather than duplicated across shell scripts.

## Critical installation rules

- Never delete the existing extensions directory during installation.
- Never overwrite user-modified extensions.
- Never delete extension data during core upgrades.
- Never reset user permission grants or enablement choices.
- Never copy secrets into extensions.
- Never confuse repository source paths with installed runtime paths.
- Never silently report installation success when extension initialization fails.

If the reference extension already exists, preserve it.

If its installed version differs from the packaged reference, report the difference. Do not silently overwrite local modifications.

If a fresh canonical example is needed after upgrading, provide a separate explicit reset or install-example operation with safe conflict handling.

Ensure compatibility with source installations, appliance installations, and any other installer modes currently supported by the repository. Do not break existing CLI-only installations or require Node.js where it was not previously required.

# 5. Extension manifest specification

Every extension must include a machine-readable `extension.yaml`.

Define a versioned, validated manifest schema.

Minimum reference:

```yaml
schema_version: 1

id: reference-extension
name: Reference Extension
version: 1.0.0
description: Demonstrates the Hosaka extension API
requires:
  hosaka_api: 1

type: view
category: examples

entrypoint:
  file: main.py
  callable: run

actions:
  echo:
    description: Return the supplied message
    input_schema: schemas/echo.input.json
    output_schema: schemas/result.output.json

limits:
  timeout_seconds: 10
  max_output_bytes: 65536

ui:
  mode: declarative
  file: ui.yaml

permissions:
  network: false
  filesystem: data-only
  subprocess: false

menu:
  label: Reference Extension
  icon: puzzle
  order: 100
```

Required behavior:

- Reject malformed manifests.
- Validate IDs, versions, entrypoint references, and UI document structure.
- Reject duplicate canonical extension IDs.
- Reject paths that escape the extension directory.
- Validate referenced files before activation.
- Support extension enablement and disablement.
- Include a compatibility mechanism for future manifest versions.
- Return actionable validation errors.

Do not dynamically import arbitrary Python modules into the long-lived Hosaka server process.

The manifest schema must be documented and enforced by actual runtime validation.

# 6. Extension execution contract

Use a stable execution interface independent of the internal implementation.

Recommended Python signature:

```python
def run(action: str, params: dict, context) -> dict:
    ...
```

The framework is responsible for:

- Finding the requested extension.
- Validating the requested action and parameters.
- Checking permissions.
- Starting its execution environment.
- Passing the request.
- Capturing results.
- Returning structured errors.
- Enforcing runtime limits.
- Recording execution logs.

The context interface should expose narrow, documented capabilities such as:

```python
context.log(...)
context.read_data(...)
context.write_data(...)
context.emit_event(...)
```

Every exposed capability must have a concrete implementation and meaningful tests.

Do not pass a raw, unrestricted application context or global credentials to extensions.

Use structured JSON-compatible request and response data.

An extension failure must never terminate the main application.

## Execution isolation

Use a separate process for Python extension execution.

Implement reasonable timeouts, output limits, process cleanup, and failure handling.

A subprocess alone is not a security sandbox. If the platform claims to enforce filesystem or network restrictions, use mechanisms that actually enforce them at the operating-system level.

Until a permission can be enforced, mark it as unsupported or trusted-only rather than claiming an unenforced restriction is safe.

Do not inherit PicoClaw API keys, provider tokens, or other unrelated secrets by default.

# 7. Declarative UI architecture

**This is a critical requirement.**

Extensions must be able to create useful interfaces without writing React code.

Define a versioned declarative UI format rendered by Hosaka-owned components.

Initial supported components:

- Stack / container
- Heading
- Text
- Button
- Text input
- Number input
- Dropdown / select
- Checkbox
- Result panel
- Error message
- Status indicator
- Simple data table

Each component must be validated before rendering.

The host renderer must use Hosaka's existing styling system.

Do not allow extensions to inject arbitrary HTML, CSS, or JavaScript into the main application's DOM.

Do not interpret arbitrary user-supplied JavaScript expressions as UI bindings.

Implement a restricted, documented action and binding model.

Example:

```yaml
version: 1

view:
  type: Stack
  children:
    - type: Heading
      text: Reference Extension

    - type: Select
      id: selection
      label: Select an option
      options:
        - Option A
        - Option B

    - type: Button
      label: Execute
      action: execute_example

    - type: Result
      bind: result.message
```

The frontend must discover extension menu entries dynamically.

Do not add a hardcoded menu item for each extension.

Opening an extension must not require edits to `TerminalGui.tsx`.

Executing an extension must not require inserting another explicit router into the central web server.

Instead, implement one generic, authenticated extension API router with strict ID and action validation, enabled-state checks, and permission enforcement.

If advanced custom web interfaces are supported later, isolate them using a sandboxed iframe and restricted communication bridge rather than direct core DOM access.

# 8. The reference extension

**The reference extension is the most important developer-facing artifact in this project.**

It must be installed automatically on fresh installations and must execute successfully.

It must not be a placeholder containing only example YAML.

It must demonstrate every feature supported by the initial extension platform.

Implement the following reference behaviors:

### A. Basic interface rendering

Render headings, explanatory text, buttons, input fields, selectors, checkboxes, and result displays.

Demonstrate host-owned styling.

### B. Simple action execution

Provide a button that calls a backend function and displays a successful structured result.

For example, an echo operation.

### C. Parameterized actions

Pass user-selected values into backend functions.

Validate their types and reject invalid inputs.

### D. State management

Demonstrate transient UI state and state updates after an action.

### E. Persistent data

Create, read, update, and delete a harmless example value using the extension's dedicated persistent data directory.

Verify that this data survives application restarts and extension upgrades.

### F. Structured error handling

Provide an explicit test action that returns a controlled error.

Demonstrate that the extension host renders a useful error message without crashing.

### G. Logging

Emit a structured log event and demonstrate where that event is recorded.

### H. Permissions

Demonstrate declared permissions and expose their status.

Include automated tests for denied operations.

Do not attempt destructive operations merely to prove restrictions.

### I. Lifecycle behavior

Verify extension discovery, loading, disabling, enabling, and removal from navigation.

### J. Automated validation

Include an extension-local test suite covering its actions, manifest, UI contract, persistence, and failure handling.

The reference extension must serve as a continuously tested example of how developers should write their own applications.

Every supported extension-platform capability must have a functioning example or an explicitly documented reason for exclusion.

# 9. Agent documentation and self-discovery

Create a prominent developer document:

`docs/extensions/AGENT_GUIDE.md`

It should be sufficient for an AI agent with no previous Hosaka knowledge to create and test an extension.

Required contents:

1. Where extensions live.
2. How to discover the runtime data path.
3. How to inspect the reference extension.
4. How to create an extension folder.
5. How to construct its manifest.
6. How to create its UI.
7. How to implement actions.
8. How to persist data.
9. How to declare and test permissions.
10. How to validate an extension.
11. How to run its tests.
12. How to diagnose failed installations or execution.
13. Which directories must never be modified during ordinary extension work.
14. How to request a platform upgrade when an existing API is insufficient.

Add a short pointer to this guide in the repository's existing agent-facing instructions, or create a root `AGENTS.md` if the repository does not already have suitable guidance.

The agent entrypoint should direct future agents to the extension platform before they start modifying the UI.

## Mandatory workflow for future extension agents

When a user requests a new Hosaka application:

1. Read `docs/extensions/AGENT_GUIDE.md`.
2. Inspect the current extension specification.
3. Inspect the reference extension.
4. Inspect existing extensions for reusable validated patterns.
5. Create a new extension directory.
6. Implement functionality using supported APIs.
7. Validate the manifest and UI.
8. Run extension-local tests.
9. Run the extension platform's compatibility tests.
10. Verify that no core source files were modified.
11. Report the extension's installation instructions, test results, and known limitations.

**Do not modify Hosaka core to implement ordinary application functionality.**

If a requested feature is unsupported, document the missing platform capability. Do not silently hack around the extension contract.

# 10. Extension developer CLI

Implement or integrate the following commands into Hosaka's existing CLI conventions:

```text
hosaka extensions init
hosaka extensions list
hosaka extensions create <id>
hosaka extensions validate <id>
hosaka extensions test <id>
hosaka extensions enable <id>
hosaka extensions disable <id>
hosaka extensions doctor
```

`create` must use the validated reference template to scaffold a new extension.

It must never overwrite an existing extension.

`validate` must return nonzero exit status on failure.

`test` must execute real automated tests, not merely recheck manifest syntax.

`doctor` must diagnose missing directories, invalid manifests, runtime failures, incorrect data paths, and permission configuration problems.

Commands must be discoverable through normal CLI help.

Do not advertise functionality that has no working implementation.

# 11. Extension compatibility and upgrades

Use independent version numbers for Hosaka core and extension manifests.

Define an extension API version.

At minimum:

- Reject unsupported major API versions.
- Preserve installed extension data.
- Avoid silent breaking changes to manifest fields.
- Record installed extension identity and version in registration metadata.
- Keep generated lock metadata separate from extension source.
- Make upgrade and rollback behavior explicit.

Core upgrades must not require rebuilding individual extensions unless an intentionally documented compatibility boundary changes.

An invalid extension should be skipped and diagnosed rather than blocking unrelated extensions from loading.

# 12. Automated testing requirements

Add platform-level tests verifying:

- Fresh installation creates the required directories.
- Repeated installation is idempotent.
- Existing extension code is preserved.
- Existing extension data is preserved.
- The reference extension is seeded correctly.
- The reference extension can actually execute actions.
- Extension discovery works.
- Duplicate IDs are rejected.
- Invalid manifests are rejected.
- Manifest path traversal is rejected.
- Invalid UI documents are rejected.
- Invalid input parameters are rejected.
- Disabled extensions cannot execute.
- Unauthorized actions are rejected.
- Extension crashes do not crash Hosaka.
- Extension timeouts terminate execution.
- Extension menu entries appear dynamically.
- Removing or disabling an extension removes its navigation entry.
- Runtime errors produce actionable diagnostics.
- Secret values are not unnecessarily exposed to the extension runner.

For claimed filesystem or network isolation, include genuine adversarial integration tests that confirm unauthorized access is blocked.

Mocked tests alone are insufficient for security guarantees.

## Core source protection

Add a test or CI check that supports extension-only development.

When a task is labeled extension-only, verify that modifications are confined to approved extension and extension-test paths.

Do not globally prohibit authorized maintenance of the core platform.

A future coding agent should be able to prove that its extension did not require modifying Hosaka source.

# 13. Suggested implementation sequence

Complete work in this order:

**Phase 1 — Architecture and specification**
- Inspect existing Hosaka code.
- Formalize extension lifecycle and manifest contract.
- Identify canonical install paths.
- Define security and compatibility boundaries.

**Phase 2 — Backend extension platform**
- Implement discovery.
- Implement validation.
- Implement execution.
- Implement storage and state interfaces.
- Implement generic API dispatch.
- Implement CLI commands.

**Phase 3 — Frontend extension host**
- Implement declarative UI rendering.
- Implement dynamic extension navigation.
- Implement action dispatch and result display.
- Implement error handling.

**Phase 4 — Reference extension**
- Implement all supported example behaviors.
- Implement extension-local tests.
- Write detailed developer instructions.

**Phase 5 — Installer integration**
- Integrate bootstrap with root `install.sh`.
- Reuse bootstrap across other installation modes.
- Seed and validate the reference extension.
- Test fresh installs and repeated installs.

**Phase 6 — End-to-end verification**
- Perform clean-install tests.
- Perform upgrade-preservation tests.
- Execute the reference extension.
- Create a second extension using only the published guide and reference example.
- Confirm that the second extension needs no core source changes.
- Run the full applicable regression suite.

This final second-extension test is mandatory because it demonstrates that the platform works for its intended users.

# 14. Definition of done

This task is complete only when all of the following are true:

- A fresh Hosaka installation creates the canonical extension directories.
- A fresh installation contains a working reference extension.
- The reference extension demonstrates all initially supported platform features.
- The example is discoverable through Hosaka's interface and CLI.
- Its actions execute through a documented runtime contract.
- Its interface renders without extension-authored core React code.
- Data persists in a dedicated extension data directory.
- Reinstallation preserves existing extensions and their data.
- A new application can be created without modifying Hosaka core.
- Invalid or crashing extensions do not compromise application availability.
- Validation and execution tests produce meaningful results.
- Developer documentation is sufficient for a new coding agent to work without external repositories or undocumented context.
- Existing Hosaka features remain operational.

## Required final agent report

After implementation, report:

1. Files created and modified.
2. Architectural decisions.
3. CLI commands implemented.
4. Exact installation and upgrade behavior.
5. Reference extension features demonstrated.
6. Tests executed and their results.
7. Security boundaries actually enforced.
8. Remaining limitations.
9. Example instructions for creating a new extension.
10. Confirmation that future extensions can be developed without core modifications.

Do not claim successful testing without running the tests.

Do not silently omit incomplete requirements.

---

# 15. Future agent operating contract

Once this platform is complete, ordinary development prompts may be as simple as:

"Create a Hosaka extension that generates funny Halloween citations."

The coding agent must automatically:

- Discover the extension guide.
- Inspect functioning examples.
- Choose the appropriate extension type.
- Create a new extension folder.
- Implement the interface and functionality.
- Use canonical storage and runtime APIs.
- Execute validation and tests.
- Confirm that core files remain unchanged.

The user's request should describe **what the application does**, not explain how Hosaka works.

That knowledge belongs in the repository.

**Final architectural principle: Hosaka is the stable platform. Extensions are replaceable capabilities. The core should not need to know what an extension does in order to host it.**
