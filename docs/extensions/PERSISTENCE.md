# Opt-in persistent and background capabilities

Existing API v1 text-only packages retain their original defaults. The owner
separately authorized these reusable capabilities for persistent applications:

- `filesystem: data-directory` requests `storage:directory` in addition to
  `storage:self`. `context.data_path(relative)` returns a path beneath the
  canonical `extension-data/ID` selected by Hosaka's resolver. Relative paths
  reject traversal, absolute names and symlink components. SQLite, objects and
  application configuration belong here, never in source.
- `network: true` requests the optional `network:self` grant.
  `context.require_network()` checks it before an application initiates HTTPS.
  Omitting the grant does not disable offline local actions.
- Optional `background: {action, interval_seconds}` requests `background:self`.
  While the native web backend runs, a supervisor invokes that declared action.
  Scheduling does not depend on a browser tab. Intervals are 15-86400 seconds;
  an extension may additionally honor its own persisted configuration interval.
- Background jobs use a separate per-extension lock and one global background
  slot, leaving a foreground worker slot available. Applications must use
  transactional databases and avoid holding write locks across network calls.
- `limits.max_file_bytes` defaults to the existing 2 MiB, with a 1 GiB ceiling.
  Applications requesting larger persistent files must explicitly declare it.

Owner CLI: `extensions trust ID --trusted-local --allow-storage
--allow-managed-data [--allow-network] [--allow-background]`. Installation,
updates, APIs and schedulers never grant these permissions automatically.
Revocation, changed source, disable/removal, root/public mode and safe mode retain
their existing checks, including cancellation of active background workers.
These controls are **trusted-local, not an OS sandbox**. Approved Python retains
the user's privileges. HTTPS verification, application authentication, data
schemas, secrets and synchronization are application responsibilities.

SQLite schema, migrations, seeds, replication and evidence policies must be
extension-owned. The host has no database-engine switch or application schema.
