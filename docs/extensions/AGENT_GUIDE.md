# Extension authoring guide for agents

## Begin here

Read [SPECIFICATION.md](SPECIFICATION.md) and [SECURITY.md](SECURITY.md), then
inspect the [reference package](../../examples/extensions/reference-extension/).
This guide describes the implemented **authoring slice**, not the complete
execution/UI platform. Do not edit core to implement an ordinary extension.
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
2. Edit `ui.yaml` using only the validated components and bindings. Validation
   is implemented; **rendering and host action binding are not yet implemented**.
   Arbitrary HTML, CSS, JavaScript and expressions are not accepted.
3. Implement `run(action, params, context)` without importing Hosaka internals.
   The reference actions demonstrate echo, local persistence and a structured
   controlled failure. Validate inputs and do not put user data in package source.
4. The reference test context implements `read_data`, `write_data`, `delete_data`
   and `log` only for standalone tests. A production capability context and
   persistent host logging are pending. Do not treat that fixture as a sandbox.
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
There is no `hosaka extensions test` or `run` yet. Do not invent a shell or
dynamic-import bypass and describe it as platform execution.

Platform compatibility tests are `python -m pytest -q tests/extensions` using
the checkout's Python environment. [TESTING.md](TESTING.md) describes the
second-package and preservation checks.

## Lifecycle and diagnosis

`enable` and `disable` persist owner intent only; grants stay separate and no
execution is possible. `remove ID` unregisters and hides the package while
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
installation/link instructions, and the explicit current execution/UI limitation.
