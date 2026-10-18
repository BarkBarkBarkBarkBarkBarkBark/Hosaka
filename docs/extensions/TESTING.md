# Extension authoring tests

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
unavailable execution. It scaffolds a second working copy outside core, validates
it, verifies core-source hashes and executes its real standalone unittest suite.

The source installer check uses isolated fixture paths and mocked package/tool
installation, but real extension bootstrap/validation. It does not qualify a
clean physical device install.

Run the reference's local tests explicitly after inspecting/trusting its code:

```sh
PYTHONPATH="$PWD" .hosakavenv/bin/python -B -m unittest discover \
  -s examples/extensions/reference-extension/tests -v
```

This is standalone execution, not a host/sandbox test. It proves callable
echo/persistence/error/log-event behavior with a test fixture. UI is validated,
not rendered. Tests do not prove network/filesystem containment or safe execution
of untrusted code. Those acceptance gates require the later runner and real
negative access tests.

For the current image, `HOSAKA_IMAGE=local-image bash
tests/test_container_runtime.sh` checks real container startup/persistence and
the installed reference metadata. Native Windows, Pi reboot, RetroArch/Foliate,
real providers, extension rendering and protected execution remain separate gates.
