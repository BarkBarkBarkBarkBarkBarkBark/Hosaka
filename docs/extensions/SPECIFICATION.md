# Implemented authoring contract v1

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
- `permissions`: `network: false`, `subprocess: false`,
  `filesystem: data-only` or `none`. These are **requests**, not enforcement.
  New registrations are disabled with no grants.
- `menu`: bounded `label`, optional `icon` (`puzzle`, `file`, `tool`, `book`),
  optional integer `order` (0–10000). Metadata only; no navigation renderer yet.
- `limits`: integer `timeout_seconds` (1–60) and `max_output_bytes`
  (1024–1048576). Validated metadata only until a supervised runner exists.

References cannot be absolute, contain `..`/backslashes or escape via symlinks.
Referenced files must exist. Registration/copy rejects all package symlinks and
special files; source digest excludes `.git`, `.venv`, `__pycache__` and
`.pytest_cache`. Registration source is bounded to 4096 files/32 MiB;
individual manifest/UI/schema documents to 256 KiB.

## Action schemas

JSON Schema draft 2020-12 objects are validated using `jsonschema`.
Only local `#`/`#/...` references are accepted and must point to schemas in the
same document. `$id`, `$dynamicRef`, `$recursiveRef` and network/file references
are unsupported. Schema traversal is bounded. Validation never fetches schemas.
Input/output **instances** are not dispatched or validated by a host yet.

The planned callable is `run(action, params, context) -> dict`. The standalone
reference implements this; the future host must invoke it only in a supervised
process with a versioned JSON protocol, never inside the server/TUI process.

## Declarative UI document

Top level is exactly `version: 1` and `view`. Components:

| Type | Required fields | Optional fields |
| --- | --- | --- |
| Stack | children (nonempty component list) | none |
| Heading, Text | text | none |
| Button | label, action (declared action name) | none |
| TextInput, NumberInput, Checkbox | id, label | correctly typed default |
| Select | id, label, options (unique string list) | default from options |
| Result, Error, Status | bind | none |
| Table | bind, columns (field identifiers) | none |

All nodes require `type`. Unknown fields fail. Input IDs are unique lowercase
identifiers; bindings are only `params.<input_id>` or `result.<field>`.
Input references must exist. No expression evaluation, raw HTML, arbitrary
CSS/JavaScript, user modules or remote widgets. Limits: 128 components,
12 nesting levels. State updates and action parameter binding belong to the
future renderer and are not executable through this validator.

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

`remove` unregisters/hides via a tombstone, retaining source/data and grants.
`link` can explicitly restore the same package disabled; no recursive delete.
Duplicate IDs, corrupt registries, escaped directories and unsupported grants
are explicit failures, not empty-success fallbacks.

## Implemented commands

`init`, `list`, `info ID`, `validate ID|PATH`, `create ID [--path PATH]`,
`link PATH`, `enable ID`, `disable ID`, `remove ID`, `doctor`.
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

Host execution, runtime schema enforcement, per-package dependencies, permission
grants/broker, safe mode, isolation, bounded workers/cancellation, persistent
execution logs, authenticated web API, UI renderer/navigation, agent invocation,
archive installation/upgrades/rollback, and full external Halloween proof.
