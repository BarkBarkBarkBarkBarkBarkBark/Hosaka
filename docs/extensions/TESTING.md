# Extension authoring, runtime and Menu tests

From the source checkout, using its installed Python environment:

```sh
.hosakavenv/bin/python -m pytest -q tests/extensions \
  tests/test_hosaka_main_console.py tests/test_appliance_install.py \
  tests/test_update_deployment.py
TEST_PYTHON="$PWD/.hosakavenv/bin/python" bash tests/test_source_install.sh
```

The authoring suite covers initialization/reruns, source/data/grant preservation,
duplicate and invalid manifests, UI validation, path/symlink escape, local-only
JSON Schema references, registry errors, lifecycle, no-import discovery and
disabled/unapproved execution. It scaffolds a second working copy outside core, validates
it, verifies core-source hashes and executes its real standalone unittest suite.

The source installer check uses isolated fixture paths and mocked package/tool
installation, but real extension bootstrap/validation. It does not qualify a
clean physical device install.

Run the reference's local tests explicitly after inspecting/trusting its code:

```sh
PYTHONPATH="$PWD" .hosakavenv/bin/python -B -m unittest discover \
  -s examples/extensions/reference-extension/tests -v
```

This command is standalone execution, not a host/sandbox test. Runtime tests
in `test_execution.py` execute real workers as a non-root account: persistence,
schema failures, exceptions, exit failures, output floods, wall timeout, process
group cleanup, same-package/global concurrency, environment sanitation,
capability path rejection and live disable/remove/revoke/safe-mode/caller
cancellation. Real execution tests intentionally skip under root, rather than
pretending a mocked UID proves unprivileged behavior.

`test_api.py` exercises real dispatch, generic discovery/views, bounded input,
policy denial, bearer auth, cross-origin/public/Host restrictions and absence of
web trust mutation routes. The native Menu must also be tested in a browser:
form controls, result/error/table rendering, persistence, escaped markup,
cancellation, dynamic entries and unchanged terminal DOM across menu use.

These tests do not prove OS network/filesystem/process confinement. Trusted-local
code retains user privileges. Enforced Linux isolation still requires a separate
runner and real negative access tests.

For the current image, `HOSAKA_IMAGE=local-image bash
tests/test_container_runtime.sh` checks real container startup/persistence and
the installed reference metadata. Native Windows, Pi reboot, RetroArch/Foliate,
real providers and protected execution remain separate gates. Default root-run
Docker images may validate metadata/UI but must refuse trusted-local execution.

## Verification checkpoint — 2026-10-18

- 379 focused Python tests passed: `tests/extensions` plus console, paths,
  migration, source/appliance deployment, registry/docs, PicoClaw/setup,
  terminal GUI and native game suites. This includes exact 64 KiB/128-file
  context boundaries, 256 KiB log rotation and two-worker host concurrency.
  Disabling a running package still works after its manifest becomes invalid.
- Real CLI and TUI commands invoked the same worker; the generic API executed
  reference persistence/errors and cancelled a real running worker.
- `npm run build:check`, source/Bash/PowerShell client checks, live Docker
  startup/persistence integration and strict OpenAPI/catalog coverage passed.
  PowerShell ran in Linux, not native Windows.
- The rebuilt `hosaka:extensions-runtime-20261018` image executed real Linux
  workers as UID 65534, including persistent data and safe-mode denial.
  The default root image continued to bootstrap packages without approving them.
- Browser testing on a disposable full native backend verified input controls,
  escaped markup (no injected script), echo/save/load, controlled errors, tables,
  live cancellation and a dynamically added second package. No frontend rebuild,
  per-package route or core git-status change was needed for that package.
  Disable removed its navigation entry; the canonical terminal DOM stayed the
  same throughout Menu operations.
- After explicit operator approval, the older local backend was restarted on
  port 8421 and the updated native Menu verified. Native packages remain
  disabled/unapproved. Test data/approvals were confined to disposable fixtures.

No provider call, protected OS containment, native Windows, physical Pi reboot or
market-readiness qualification is implied by these results.
