# Extension authoring guide for agents

## Begin here

Read [SPECIFICATION.md](SPECIFICATION.md) and [SECURITY.md](SECURITY.md), then
inspect the [reference package](../../examples/extensions/reference-extension/).
This guide describes authoring, explicitly approved **trusted-local execution**
and declarative Menu views. It does not claim OS isolation. Do not edit core to
implement an ordinary extension.
If the requested application requires a missing host capability, report the gap
and request an explicitly tracked platform upgrade.

## Locate the actual runtime

```sh
hosaka paths --json
hosaka extensions doctor --json
hosaka extensions init --json
hosaka extensions list --json
hosaka extensions info reference-extension --json
```

`paths.data`, `paths.extensions`, `paths.extension_data` and
`paths.extension_lock` are canonical. `HOSAKA_DATA_DIR` may override them.
Docker commands operate inside the container; use its host-mounted storage or a
shared project mount when editing. Do not assume a container path exists on the
host. Initialization never invokes extension code or downloads dependencies.

## Create independent source

Use the default external packages directory, or choose a new independent working
copy outside the core checkout/deployment:

```sh
hosaka extensions create my-extension --json
# Or, instead of the command above:
hosaka extensions create my-extension --path /absolute/path/to/my-extension --json
```

Never overwrite an existing folder or reuse another package's ID. Existing
independent packages can be registered with
`hosaka extensions link /absolute/path/to/package --json`. A link is a registry
reference, not a symlink, copy, import, install script or dependency installation.

## Edit the contract and implementation

1. Edit `extension.yaml`: unique ID, version, explicit actions, relative input
   and output JSON Schema files, Python file/callable, declarative UI and
   requested permissions. Unknown fields/permissions are errors.
2. Edit `ui.yaml` using only the validated components and bindings. The native
   Menu renderer handles state, action binding and validated results dynamically.
   For an app with several tools, use root `Navigation` pages: keep the primary
   workflow first, place tables/settings in labeled subpanels, and use `Details`
   for secondary controls. Inputs initialize across all pages and persist while
   navigating; results clear on panel changes. Every hidden control still counts
   toward validation bounds. These components need an updated host.
   Use `LookupInput` for inline read-only search and identity selection rather
   than making users copy UUIDs between panels. Its text and selection IDs are
   separate bindings; free-text creation belongs in the extension's transactional
   submit action, not in the renderer or lookup action.
   Persistent database/file applications may explicitly request the generic
   [managed data and background capabilities](PERSISTENCE.md). Keep all schema,
   migration, authentication and replication code in the independent package.
   `FileInput` stages bounded binary uploads; `Files` links only private managed
   objects, never root configuration or arbitrary filesystem paths.
   Give lookup options human-readable `description_field` details rather than
   making people distinguish UUIDs. Opaque selected values may carry an expected
   revision checked by the extension; they are not public authorization tokens.
   A page's explicit read-only `load` action can populate a table on entry.
   Arbitrary HTML, CSS, JavaScript and expressions are not accepted.
3. Implement `run(action, params, context)` without importing Hosaka internals.
   The reference actions demonstrate echo, local persistence and a structured
   controlled failure. Validate inputs and do not put user data in package source.
4. The production context implements `read_data`, `write_data`, `delete_data`
   and `log`. Data methods require the separate `storage:self` grant and plain
   filenames. Persist values only in the supplied data capability, not source.
   Logs keep bounded event names/field names, not input/result/metadata values.
   The standalone test context is a fixture, not an OS sandbox.
5. Add package-local tests and use the published validator.

## Validate and test deliberately

```sh
hosaka extensions validate /absolute/path/to/my-extension --json
hosaka extensions validate my-extension --json
```

For a source checkout, use its actual Python environment (`.hosakavenv` or
`.venv`) and set `PYTHONPATH` to the checkout:

```sh
PYTHONPATH=/absolute/path/to/Hosaka \
  /absolute/path/to/Hosaka/.hosakavenv/bin/python -m unittest discover \
  -s /absolute/path/to/my-extension/tests -v
```

This **executes code as your user**. Inspect/trust the package first.
Discovery, validation, bootstrap and core startup never run these tests.
There is no `hosaka extensions test` command yet. Never run arbitrary package
tests during discovery or boot.

Platform compatibility tests are `python -m pytest -q tests/extensions` using
the checkout's Python environment. [TESTING.md](TESTING.md) describes the
second-package and preservation checks.

## Lifecycle and diagnosis

Ask the owner to inspect and approve the source before enabling execution:

```sh
hosaka extensions trust my-extension --trusted-local --allow-storage
hosaka extensions enable my-extension
hosaka extensions run my-extension echo --params '{"message":"Hello"}'
```

Do not silently approve code on the owner's behalf. Trusted-local Python runs
with the user's privileges, not a sandbox. Source changes invalidate approval.
Only the owner CLI/TUI exposes approval/grants; the API cannot grant them.
`--allow-storage` is needed for `filesystem: data-only`. Stdlib-only packages are
currently supported; dependency installation into core is not supported.

Open **Menu → Extensions → your package**. `Button.params` maps action properties
to `params.<input_id>`; legacy buttons project onto schema top-level properties.
Results, errors, status and tables bind to validated output; HTML is never
injected. No core UI edits or rebuild are needed for a second package.

`disable`, `revoke` and `safe-mode on` block/cancel jobs.
`remove ID` unregisters and hides the package while
retaining source and data. Bootstrap respects removal. An explicit `link PATH`
can restore it, disabled. There is no data purge or archive updater yet.

`doctor` reports invalid/missing packages and directories. `list` diagnoses a bad
package without hiding unrelated good ones; duplicate IDs have no winner.
Exit 1 means an operation/validation error; inspect stderr or structured errors.
`init` reports a modified/different reference rather than replacing it.
Registry corruption requires explicit repair or a protected backup restore,
never deleting the lock file as an automatic recovery.

## Prove extension-only development

Record `git -C /absolute/path/to/Hosaka status --porcelain` before and after.
Existing unrelated core changes must remain identical; on a clean baseline the
status remains empty. Only the independent package, its local tests and allowed
data may change. Never modify `hosaka/`, `frontend/src/`, `kiosk/`, installed core,
provider files, upstream PicoClaw, other extensions or permission grants to make
an ordinary application work.

Report the package path, ID/version, validation and actual test results,
installation/link/approval instructions, and the trusted-local security boundary.
Never describe sanitized environment variables as hiding host credential files.
