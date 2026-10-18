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

**Current boundary:** Hosaka seeds this package disabled. UI rendering, hosted
execution, enforced permissions and production context methods are not yet
implemented. The test context is not a sandbox, real host adapter, or permission
broker. Its logs are in-memory test events, not persistent platform logs.
No Node build, provider key or network request is required.

Persistent values belong in the separately supplied extension data directory,
never this source folder. See the core `docs/extensions/AGENT_GUIDE.md` for
authoring, installation, lifecycle and remaining platform gates.
