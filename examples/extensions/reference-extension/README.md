# Extension authoring reference

This independent source package demonstrates callable echo, local value
save/load/delete, structured failure and metadata-only log events. It imports no
Hosaka code in its implementation.

The manifest and declarative view can be validated with
`hosaka extensions validate /absolute/path/to/this/package`.

For source development, use the Hosaka Python environment and run:

```sh
PYTHONPATH=/absolute/path/to/Hosaka \
  /absolute/path/to/Hosaka/.hosakavenv/bin/python -m unittest discover \
  -s /absolute/path/to/this/package/tests -v
```

Use `.venv` instead if that is the installed environment. Package action tests
use the standard library; the contract test uses the installed Hosaka validator.
Running tests executes package code with your user permissions: inspect and
trust the source first. Never run unfamiliar tests as part of discovery or boot.

Hosaka seeds this package disabled and unapproved. After inspecting its source:

```sh
hosaka extensions trust reference-extension --trusted-local --allow-storage
hosaka extensions enable reference-extension
hosaka extensions run reference-extension echo --params '{"message":"Hello"}'
```

Then open **Menu → Extensions → Reference Extension**. Inputs/results/errors and
tables are rendered by the host. Echo/save use explicit parameter bindings;
load/delete/fail use empty parameter objects. Other inputs preview transient UI
state. No per-package Node build, provider key or network request is required.

The production context persists text in this extension's data directory and
records bounded event/field names in the runtime log. The test context remains
an in-memory fixture. **Trusted-local is not an OS sandbox:** approved Python
retains user privileges. Root/public execution is refused; OS confinement remains
pending. Source changes require reapproval. Reinstall preserves older or
owner-modified reference copies rather than overwriting them.

Persistent values belong in the separately supplied extension data directory,
never this source folder. See the core `docs/extensions/AGENT_GUIDE.md` for
authoring, installation, lifecycle and remaining platform gates.
