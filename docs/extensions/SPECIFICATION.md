# Implemented extension contract v1

Authoring, trusted-local execution and generic declarative Menu views are
implemented. Trusted-local approval is explicit and digest-bound; it is **not an
OS sandbox**. Root/public execution is refused. Packages remain disabled and
unapproved after installation.

## Version and identity

The sole manifest is `extension.yaml`. The old `plugin.yaml` was an
unimplemented proposal and is not a compatibility alias.
`schema_version: 1` and `requires.hosaka_api: 1` are integers; other versions
are rejected. IDs/action names are non-reserved lowercase kebab-case, at most
64 characters. Package versions use `major.minor.patch`.

See the complete [reference manifest](../../examples/extensions/reference-extension/extension.yaml).
Required fields: `schema_version`, `id`, `name`, `version`, `description`,
`requires`, `type: view`, `category`, `entrypoint`, `actions`, `ui`,
`permissions`, `menu`, `limits`. Unknown fields and duplicate YAML keys fail.

- `entrypoint`: relative Python `file` and a simple identifier `callable`.
  Validation checks the file, not the existence/executability of the callable.
  No package code is imported.
- `actions`: 1–32 named records with `description`, `input_schema` and
  `output_schema`, referencing local JSON files.
- `ui`: `mode: declarative` and a relative `file`.
- `permissions`: boolean `network`, `subprocess: false`,
  `filesystem: data-only`, `data-directory` or `none`. These are requests. The context enforces its
  own data capability, but arbitrary trusted Python retains user privileges;
  network/subprocess/host filesystem restrictions are NOT OS-enforced.
- `menu`: bounded `label`, optional `icon` (`puzzle`, `file`, `tool`, `book`),
  optional integer `order` (0–10000). Enabled entries appear dynamically in Menu.
- `limits`: integer `timeout_seconds` (1–60) and `max_output_bytes`
  (1024–1048576). Enforced for worker wall time and combined stdout/stderr bytes.
  Optional `max_file_bytes` defaults to 2 MiB, bounded at 1 GiB.
- Optional `background: {action, interval_seconds}` declares a periodic action
  and 15-86400-second host interval; its action must appear in `actions`.
  See [persistent capabilities](PERSISTENCE.md) for explicit grants and lifecycle.

References cannot be absolute, contain `..`/backslashes or escape via symlinks.
Referenced files must exist. Registration/copy rejects all package symlinks and
special files; source digest excludes `.git`, `.venv`, `__pycache__` and
`.pytest_cache`. Registration source is bounded to 4096 files/32 MiB;
individual manifest/UI/schema documents to 256 KiB.

## Source import

`hosaka extensions install SOURCE` accepts a local package directory or a public
HTTPS Git repository URL. The local Menu Extensions panel exposes the same
operation through `POST /api/v1/extensions/install`, with a JSON `source` string
of at most 2048 characters and an 8 KiB request-body limit. Browser import requires
a loopback client and loopback origin, existing write authorization and a
non-public backend. Root import is refused.

Source is staged and validated without importing package code, installing
dependencies or running package tests. Git is invoked without a shell, with a
60-second timeout, shallow single-branch fetch, isolated HOME/configuration,
disabled hooks/credential helpers and no submodules. Only HTTPS transport is
allowed; URL credentials, queries and fragments are rejected. Private repositories
must be checked out separately and imported by local path. Clone downloads have
no separate disk/network quota; the validated source retains the normal package
file-count/size limits.

The manifest ID selects `paths.extensions/ID`. Existing registrations and
destinations are refused, not upgraded or replaced. Imported snapshots omit Git
metadata and start disabled, without approval or grants. Source directories and
extension data are untouched. `extensions link PATH` still registers an external
working copy in place for development. No automatic update/rollback is provided.

## Action schemas

JSON Schema draft 2020-12 objects are validated using `jsonschema`.
Only local `#`/`#/...` references are accepted and must point to schemas in the
same document. `$id`, `$dynamicRef`, `$recursiveRef` and network/file references
are unsupported. Schema traversal is bounded. Validation never fetches schemas.
Input/output instances are validated by core before/after each invocation.
Parameters are JSON objects of at most 16 KiB; action request bodies at most 32 KiB.

The callable is `run(action, params, context) -> dict`, loaded only inside a
supervised worker. Results must satisfy their schema and include boolean
`success`, string `message`, and optional text/null `error`. Additional declared
fields such as `rows` are allowed. Controlled `success: false` is not host success.

## Trusted-local execution

```sh
hosaka extensions trust reference-extension --trusted-local --allow-storage
hosaka extensions enable reference-extension
hosaka extensions run reference-extension echo --params '{"message":"Hello"}'
hosaka extensions revoke reference-extension
hosaka extensions safe-mode on
hosaka extensions safe-mode off
```

Trust approves the current source digest and optional `storage:self` grant. It
does not enable a package. Source edits require inspection/reapproval. Approval,
grants and enablement survive bootstrap; bootstrap never approves new code.
No web endpoint can grant trust or enable packages.

Invocation snapshots must match the approved digest. Core launches an isolated
Python interpreter (`-I -S -B`) with a fixed bridge and argument vector, no shell,
fresh temporary HOME/TMPDIR and an allowlisted environment without provider
credentials. The first runtime supports stdlib-only packages; it does not install
dependencies into the core environment.

One JSON request goes over stdin; one response over stdout includes protocol
version 1, invocation UUID, result/error and bounded event metadata. Package prints
go to bounded stderr. Core checks exit status before accepting JSON. Public/root,
disabled/unregistered/unapproved packages, missing grants, changed code and safe
mode prevent execution. `HOSAKA_EXTENSIONS_SAFE_MODE=1` overrides persisted mode.

At most two invocations run on the host and one per extension, enforced across
processes by locks. Wall time, combined output, CPU time, file descriptors and
file size are bounded; Linux workers additionally have a 256 MiB address-space
limit. Normal descendants share a process group killed on every exit, timeout or
cancellation. Trusted code can bypass same-user controls or create detached
processes: this is not adversarial OS containment or an enforced process-count
limit. Linux protected execution remains a separate release gate.

Disable, removal, revoke, grant changes and safe mode cancel active jobs through
registry checks. Disable operates directly on registration, without validating
package source, so a broken manifest cannot prevent stopping a running package.
It returns registration-state confirmation rather than a freshly loaded view.
Explicit cancellation uses
`hosaka extensions cancel ID INVOCATION_UUID` or the UI Cancel action. API client
disconnect signals cancellation. A cancellation request does not undo completed
storage operations; invocation failure reports the actual outcome.

### Production context

- `read_data(name) -> str | None`, `write_data(name, text)`, `delete_data(name)`:
  require `storage:self` and `filesystem: data-only` or `data-directory`; plain filenames only, no
  symlink/path escape. Private atomic text writes, maximum 64 KiB/file and
  128 files through this capability. Data lives under `extension-data/ID`.
- `data_path(relative) -> str` requires `filesystem: data-directory` and the
  separate `storage:directory` grant; rejects absolute/traversing/symlinked
  paths and uses the host's canonical extension-data resolver. SQLite and managed
  objects/configuration can persist here without the text-file size limit.
- `require_network()` requires a requested `network: true` plus `network:self`.
  This optional grant is checked when used; offline actions can run without it.
  Trusted-local Python is still not OS-confined.
- `log(event, metadata)`: bounded event names and metadata field names are
  recorded; metadata **values**, params, results, stderr and exception text are
  deliberately not persisted. This privacy rule is part of the API.
- Core logs timestamp, invocation/action identity, mode, duration, outcome/error
  code and event metadata under `logs/extensions/ID.jsonl`, rotated to one
  previous file at 256 KiB each. Log failures are explicit invocation errors.

Context path checks scope these methods; they do not prevent approved Python
from accessing other user-readable files through ordinary Python APIs.

## Declarative UI document

Top level is exactly `version: 1` and `view`. Components:

| Type | Required fields | Optional fields |
| --- | --- | --- |
| Stack | children (nonempty component list) | none |
| Navigation | pages (1-12 unique labeled `{label, view}` records, root only) | page `load: {action, params}` |
| Details | label, children (nonempty component list) | none |
| Heading, Text | text | none |
| Button | label, action (declared action name) | params (property-to-input binding map) |
| TextInput, NumberInput, Checkbox | id, label | correctly typed default |
| FileInput | id, filename_id, label | none |
| Files | bind (validated object-name/label list) | none |
| LookupInput | id, selection_id, label, action, query_param, label_field, value_field, max_length (1-2048) | description_field, params (context-input bindings) |
| Select | id, label, options (unique string list) | default from options |
| Result, Error, Status | bind | none |
| Table | bind, columns (field identifiers) | none |

All nodes require `type`. Unknown fields fail. Input IDs are unique lowercase
identifiers; bindings are only `params.<input_id>` or `result.<field>`.
Input references must exist. No expression evaluation, raw HTML, arbitrary
CSS/JavaScript, user modules or remote widgets. Limits: 128 components,
12 nesting levels. The host owns all React elements and styling. Text is rendered
as text, never HTML; terminal/control characters are escaped for display.

`Button.params: {message: params.message}` maps fields explicitly. For older
buttons without a map, the renderer projects inputs onto the action schema's
top-level `properties`. Complex schemas without top-level properties require
explicit bindings. Inputs persist across actions; results/errors/status/table
update from validated output. Closing a view discards transient input state,
not stored data or the canonical terminal.

`Navigation` is an additive host-owned v1 component for application subpanels.
The first page is the default; the app menu shows the other page labels. Every
page and closed `Details` group is validated, counted against the same global
component/depth bounds, and included when initializing globally unique inputs.
Navigating preserves draft inputs and clears the previous action's result/error.
An optional page `load` invokes its declared action once per visit using explicit
input bindings; use read-only queries to populate tables without another click.
It uses normal busy/cancellation/error handling and the same approval checks,
not a background scheduler or a discovery hook. Pages without `load` execute
nothing on navigation. Navigation is disabled during an
invocation; cancellation remains available. `Details` starts collapsed. Hidden
controls are excluded from the dialog's keyboard focus loop. These new components
require an updated host; older v1 views retain their existing behavior.

`LookupInput` keeps free text in `params.<id>` and a selected row's identity in
`params.<selection_id>`. Both IDs are globally unique input IDs, initially empty.
Editing the text clears the selection. Typing debounces a declared lookup action
with `{query_param: text}` through the same digest-approved authenticated worker;
use a read-only search action, not a mutation. Suggestions must be validated output
`rows` with nonempty string `label_field`/`value_field` properties and unique
values. Labels fit `max_length`. At most eight matches display, with an explicit
truncation hint. Keyboard arrows/Enter select a row; Escape closes the dropdown
before leaving the application. No match requires no selection: the submit
action decides whether/how to create an entity from free text.
Optional `description_field` supplies a bounded human-readable detail (up to
2048 characters) under each suggestion and the selection, so users can
distinguish records without reading opaque values. Optional `params` adds
`params.<input_id>` context bindings, such as a status filter, but cannot replace
the query parameter. Changing context clears a prior selection. Focusing a
selected lookup searches again so a fresh record can be chosen.

Lookup and button requests are serialized per open view, with at most eight
pending requests. Obsolete queued lookups are skipped, in-flight lookups finish
before a mutation starts, and closing the view aborts outstanding requests.
Lookup errors are displayed explicitly, never converted to empty-success matches.
All existing permissions, schemas, source approvals and safe-mode/public checks
apply equally to lookup actions. The host cannot infer read-only domain semantics.

The native Menu contains one generic Extensions section. It polls metadata for
enabled entries; disable/removal removes navigation and aborts its active view.
Selecting an extension opens a full-window host-owned view with a Back to Hosaka
button. The canonical terminal remains mounted and paused for input, not restarted.
Escape closes an open app menu first, then returns to the terminal. No per-package
frontend build/router edit is needed.

## Generic API

`GET /api/v1/extensions`, `GET /api/v1/extensions/ID/view`,
`POST /api/v1/extensions/ID/actions/ACTION`,
`POST /api/v1/extensions/ID/cancel/INVOCATION_UUID`.
Managed packages additionally use `POST /api/v1/extensions/ID/files` (raw body,
current `X-Extension-Digest`, URL-encoded `X-Extension-Filename`) and
`GET /api/v1/extensions/ID/files/NAME`. These require the same authentication,
origin/public policy, enablement and matching source approval, plus directory
grant. Uploads are bounded to 10 MiB/30 seconds and normal worker slots; files
stage under `uploads/`, downloads are confined to `files/`. SQLite and private
root configuration cannot be downloaded through this surface.
All use the stricter existing write-auth policy even for metadata: loopback or
valid bearer token. Public mode, cross-site origins and local DNS-rebinding Host
names are denied. Same-origin and the native Vite loopback port 5173 are accepted.
There is no LAN-anonymous metadata endpoint or trust/grant mutation endpoint.

Action bodies contain `invocation_id`, source `digest` from the view and `params`.
Stale views cannot invoke newly approved code. Responses explicitly label
`execution_mode: trusted-local`, `sandboxed: false`, `ok`, `result` and structured
`error`. Policy/input/process failures use non-success HTTP codes; controlled
action failures return their validated structured result with `ok: false`.

## Discovery and registration

Discovery reads immediate child directories of canonical `extensions/` plus
explicit registry links, validates metadata and diagnoses invalid packages.
It does not import code, run hooks/tests or install dependencies.
Duplicate IDs are all rejected; unrelated valid packages remain visible.

`extensions.lock.json` is private, atomic schema version 1 metadata:
ID to absolute source path, registered version, SHA-256 source digest,
enabled state, grants and removal tombstone. A separate transaction lock
serializes manager writes. Reinitialization preserves owner decisions and never
refreshes a stored digest/version silently. `info` reports current versus
registered version and whether source changed. An edit is not an automatic grant.
Optional `approved_digest` and `execution_mode` record explicit owner approval;
registry-level `safe_mode` disables execution without deleting packages.

`remove` unregisters/hides via a tombstone, retaining source/data and grants.
`link` can explicitly restore the same package disabled; no recursive delete.
Duplicate IDs, corrupt registries, escaped directories and unsupported grants
are explicit failures, not empty-success fallbacks.

## Implemented commands

`init`, `list`, `info ID`, `validate ID|PATH`, `create ID [--path PATH]`,
`link PATH`, `enable ID`, `disable ID`, `remove ID`, `doctor`.
Also `trust ID --trusted-local [--allow-storage]`, `revoke ID`,
`run ID ACTION [--params JSON]`, `cancel ID UUID`, `safe-mode on|off|status`.
Each accepts `--json`; current output is structured JSON in either mode.
The same commands are available after `/extensions` in the TUI.
Unknown or unsupported commands fail without exiting the TUI.

Bootstrap copies the reference only if absent, validates it and discovers the
installed package. Owner-modified versions are reported and preserved.
Unrelated invalid packages produce structured diagnostics and an explicit stderr
warning without blocking bootstrap of the valid reference or core startup.
`list`/`doctor` still return nonzero for those diagnostics. A corrupt registry or
invalid reference itself remains a bootstrap failure, never an automatic reset.
Source/appliance/Docker installers call this routine; source setup remains
Python-only unless `--gui` is selected.

## Still pending

OS-enforced isolation and process/network/filesystem confinement, per-package
dependency environments, a general privileged capability broker, dedicated
PicoClaw tool dispatch, archive installation/upgrades/rollback, an extension test
runner command, and full external Halloween/clean-device proof.
