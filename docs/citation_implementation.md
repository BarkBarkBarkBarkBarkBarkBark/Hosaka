# Implementation handoff: Hosaka Halloween Citations

**Target:** Hosaka `dev` branch  
**Extension ID:** `halloween-citations`  
**Project type:** Offline-first citation management application, with optional remote PostgreSQL synchronization and public discussion.

## Project objective

Build a humorous Halloween party citation system.

Organizers should be able to issue fictional citations to partygoers for offenses including:

- Attending without a costume
- Insufficient Halloween spirit
- Excessive seriousness
- Failure to participate in festivities
- Suspiciously normal behavior
- Violations added by the organizer

Each citation may specify a remedy, such as putting on a costume, performing a silly dance, or delivering a dramatic apology.

Despite the humorous concept, the application should behave as reliable record-management software.

The application must function completely offline, provide local persistence, and optionally synchronize with a remote PostgreSQL database.

A later stage should permit guests to view and comment on citations through a web interface.

All functionality, storage, and application code should be extension-owned.

---

# Phase 0 — Inspect existing infrastructure

Before writing application code, inspect:

- `install.sh`
- `hosaka/paths.py`
- `hosaka/extensions/`
- `hosaka/web/extensions_api.py`
- `docs/extensions/AGENT_GUIDE.md`
- `docs/extensions/SPECIFICATION.md`
- `docs/extensions/SECURITY.md`
- `examples/extensions/reference-extension/`

The currently inspected Hosaka platform provides:

- Versioned extension manifests
- Strict validation
- Dynamic menu discovery
- JSON-schema-backed actions
- Declarative interfaces
- Explicit trusted-local approvals
- Digest-based source verification
- Per-extension data directories
- Limited file-based persistence
- Synchronous Python execution

Recognize these existing limitations:

1. Extension manifests currently prohibit network and subprocess access.
2. The host context supports small text files, not general database/file capabilities.
3. Action execution is limited to 60 seconds.
4. The extension runner is trusted-local and not OS-sandboxed.
5. Arbitrary custom React or JavaScript interfaces are not supported.
6. The public extension API is disabled.
7. The platform has no native attachment uploader or background service manager.

Do not circumvent these limitations through direct imports of internal Hosaka modules, undocumented filesystem access, credential leakage, or arbitrary server modifications.

## Phase 0 deliverable

Produce a capability-gap report separating:

- Features implementable through the current extension API.
- Features requiring an explicit Hosaka platform upgrade.
- Features implementable in a separately running extension-owned service.

Do not begin the network/sync integration until this boundary is documented.

### Acceptance criteria

- Current runtime architecture is documented.
- Existing reference-extension tests pass.
- Canonical installation and extension-data paths are verified.
- No unnecessary core modifications are proposed.

---

# Phase 1 — Canonical data schema and offline repository

Build the citation domain model before the interface.

Use SQLite for local persistence.

SQLite must be the primary write target while offline.

All domain rows should use UUIDs generated locally, except for human-readable citation numbers, which are display identifiers and must not be synchronization keys.

## Canonical entities

### persons

Fields:

- `id`: UUID primary key
- `display_name`: required text
- `email`: optional text
- `phone`: optional text, E.164 when normalized
- `created_at`: UTC timestamp
- `updated_at`: UTC timestamp
- `deleted_at`: optional UTC timestamp

Person contact information must remain optional.

Do not require partygoers to disclose an email address or telephone number.

### violation_types

Fields:

- `id`: UUID primary key
- `code`: unique machine-readable identifier
- `title`: human-readable offense
- `description`: optional text
- `default_remedy`: optional text
- `default_resolution_seconds`: positive integer or null
- `severity`: integer, recommended 1–5
- `active`: boolean
- `created_at`
- `updated_at`

The organizer may create custom violation types.

### citations

Fields:

- `id`: UUID primary key
- `citation_number`: unique human-readable identifier
- `person_id`: foreign key
- `violation_type_id`: foreign key
- `issued_at`: UTC timestamp
- `issued_by`: optional actor identifier
- `description`: optional narrative
- `first_offense`: boolean snapshot
- `status`: enum
- `resolution_duration_seconds`: positive integer or null
- `due_at`: UTC timestamp or null
- `resolved_at`: UTC timestamp or null
- `resolved_by`: optional actor identifier
- `resolution_notes`: optional text
- `created_at`
- `updated_at`
- `revision`: nonnegative integer
- `deleted_at`: optional tombstone timestamp

Allowed statuses:

- `open`
- `resolved`
- `void`

Do not make `overdue` a canonical mutable status. Derive it from `status = open` and `due_at` being in the past.

A voided citation remains in history but is excluded from active offense counts.

### remedies

Fields:

- `id`: UUID
- `citation_id`: foreign key
- `description`: required text
- `required`: boolean
- `completed`: boolean
- `completed_at`: UTC timestamp or null
- `completed_by`: optional actor
- `completion_notes`: optional text
- `position`: integer
- `created_at`
- `updated_at`
- `deleted_at`

A citation may have multiple remedies.

### attachments

Fields:

- `id`: UUID
- `citation_id`: foreign key
- `uploaded_by`: optional actor
- `original_filename`: text
- `mime_type`: text
- `size_bytes`: integer
- `sha256`: content digest
- `local_storage_key`: nullable relative object key
- `remote_storage_key`: nullable object key
- `sync_status`: enum
- `created_at`
- `deleted_at`

Store files outside SQLite.

Never store arbitrary absolute filesystem paths supplied by clients.

Use generated storage keys and validate file types, size, and actual content.

### comments

Fields:

- `id`: UUID
- `citation_id`: foreign key
- `author_id`: optional actor identifier
- `author_display_name`: text
- `body`: text
- `visibility`: `public` or `organizer`
- `moderation_status`: `visible`, `pending`, or `hidden`
- `created_at`
- `updated_at`
- `deleted_at`

Comments must never modify citation records.

### citation_events

Fields:

- `id`: UUID
- `citation_id`: foreign key
- `actor_id`: optional actor
- `event_type`: text
- `event_payload`: JSON
- `created_at`: UTC timestamp

Record events for citation creation, edits, remedy completion, resolution, reopening, voiding, and evidence changes.

Treat the event history as append-only.

### notifications

Fields:

- `id`: UUID
- `citation_id`: foreign key
- `type`: notification category
- `channel`: `in_app`, `email`, or `sms`
- `scheduled_at`
- `sent_at`
- `status`: `pending`, `sent`, `failed`, or `cancelled`
- `attempts`: integer
- `last_error`: optional text
- `idempotency_key`: unique text

Only in-app reminders are required initially.

Email and SMS are optional later integrations that require appropriate provider capabilities and recipient consent.

### sync_outbox

Fields:

- `id`: UUID
- `entity_type`: text
- `entity_id`: UUID
- `operation`: `upsert` or `delete`
- `payload`: JSON
- `base_revision`: nullable integer
- `created_at`
- `attempts`
- `next_attempt_at`
- `last_error`
- `delivered_at`

### sync_checkpoints

Fields:

- `remote_id`: text primary key
- `cursor`: remote synchronization position
- `updated_at`

## Data constraints

- Use explicit foreign keys.
- Enable SQLite foreign-key enforcement.
- Store all timestamps in UTC ISO 8601 format locally.
- Store UUIDs as canonical lowercase strings in SQLite and native UUIDs in PostgreSQL.
- Use integer durations instead of floating-point hours.
- Use schema migrations from day one.
- Use transactions for citation creation, updates, and event recording.
- Enforce uniqueness on citation numbers and violation codes.
- Use tombstones for synchronized deletions.
- Never use timestamps alone for conflict resolution.
- Do not use `REPLACE INTO` for updates that should preserve related rows.

Provide PostgreSQL migrations implementing equivalent domain semantics.

## First-offense calculation

A citation is a first offense if there are no earlier non-void citations for the same person and violation type.

Determine the value transactionally when the citation is issued.

Preserve it as an immutable historical snapshot unless the organizer explicitly performs a correction.

## Required offline operations

Implement:

- Create person
- Search persons
- Create violation type
- List violation types
- Issue citation
- Search/filter citations
- Retrieve citation details
- Edit citation
- Add/edit remedies
- Complete remedy
- Resolve citation
- Reopen citation
- Void citation
- Retrieve overdue citations
- Retrieve event history

Separate the domain and repository layers from transport and UI logic.

### Acceptance criteria

- SQLite operates without any network connection.
- Database initialization is repeatable.
- Migration tests pass against empty and existing databases.
- Citation UUIDs and human-readable numbers are unique.
- First-offense calculations are correct.
- Resolution and reopening generate events.
- Invalid state transitions are rejected.
- Unit tests cover all repository operations.
- Local transactions prevent partial writes.

---

# Phase 2 — Extension-owned local application

Create the application package using the installed reference extension as a starting point.

All ordinary application code must live inside the independent `halloween-citations` extension directory.

Recommended internal layout:

```text
halloween-citations/
├── extension.yaml
├── main.py
├── ui.yaml
├── README.md
├── AGENT_CONTEXT.md
├── schemas/
├── citations/
│   ├── models.py
│   ├── repository.py
│   ├── service.py
│   ├── validation.py
│   └── migrations/
├── tests/
└── web/
```

Runtime data must live in the extension's dedicated persistent data directory:

```text
extension-data/halloween-citations/
├── citations.sqlite3
├── evidence/
├── sync/
└── exports/
```

## Current-platform implementation

Start with compatible JSON-schema-backed extension actions.

Support:

- Issue citation
- List/search citations
- Retrieve citation by number
- Mark remedy completed
- Resolve citation
- Reopen citation
- List overdue citations

Use the existing declarative UI primitives where practical.

Do not introduce unsupported UI component names into `ui.yaml`.

If the current 64 KiB context storage limitation prevents SQLite, implement a narrow proof-of-concept using supported storage, then proceed through the explicit platform upgrade in Phase 3. Do not treat that proof-of-concept as the production database.

## Application presentation

Use a humorous Halloween theme while retaining readable form controls.

Suggested citation format:

**OFFICIAL HALLOWEEN VIOLATION NOTICE**

- Citation number
- Offender
- Violation
- Date and time
- Severity
- First-time offense
- Required remedy
- Resolution deadline
- Status
- Evidence
- Organizer signature

Provide a printable citation layout.

### Acceptance criteria

- The initial application is discovered through Hosaka's Extensions menu.
- Existing reference-extension functionality remains unaffected.
- Basic forms run through the supported extension API.
- Citation actions pass schema validation.
- The core is not modified to accommodate individual citation features.

---

# Phase 3 — Service-backed extension platform capability

This phase is a separately authorized Hosaka infrastructure task.

The existing extension runner is not designed to host a long-running database-backed web service or accept file uploads.

Implement a general, reusable service-backed extension capability only after documenting its security model.

Do not hardcode Halloween-specific functionality into Hosaka core.

## Required host capabilities

The platform should support:

1. Registering an extension-owned backend service.
2. Starting and stopping it independently of individual action invocations.
3. Health checks and restart policy.
4. Controlled persistent data directories.
5. Separately managed dependencies.
6. File upload/download capability.
7. Bounded and authenticated service communication.
8. Extension-specific configuration and secrets references.
9. Clear lifecycle diagnostics.
10. Explicit permissions and trust grants.

A platform manifest revision may introduce a `service` extension type, but should preserve backwards compatibility with v1 `view` extensions.

Use manifest validation and capability grants rather than accepting arbitrary process commands from an untrusted package.

For Linux appliances, prefer a genuinely isolated runtime such as an appropriately constrained system service or container.

If protected execution cannot be implemented, retain trusted-local semantics and do not present it as a sandbox.

## Service and UI boundaries

The extension service owns its data API.

Hosaka owns the integration point and navigation.

For richer interfaces, permit a sandboxed application panel or iframe with a documented bridge.

Do not give arbitrary extension JavaScript access to the parent Hosaka DOM, tokens, or APIs.

Keep organizer operations authenticated independently of public read/comment functionality.

### Acceptance criteria

- A dummy service-backed extension can start, stop, and restart.
- Its service appears through generic Hosaka discovery.
- Invalid service configuration fails safely.
- Service crashes do not crash Hosaka.
- Runtime data survives service restarts.
- Host secrets are not exposed unnecessarily.
- Existing v1 extensions continue working.
- Public routes never expose extension administration capabilities.
- No Halloween-specific code exists inside core.

---

# Phase 4 — Full citation management interface

Implement a local web application or enhanced extension UI using Phase 3 capabilities.

## Required screens

**Dashboard**
- Open citation count
- Resolved citation count
- Overdue citation count
- Recently issued citations
- Citations requiring immediate attention

**Issue citation**
- Select or create person
- Select or create violation
- Record incident time
- Select first-offense override only with a documented correction reason
- Describe incident
- Specify remedy
- Set time allowed to resolve
- Add optional contact information
- Attach evidence
- Submit and preview citation

**Citation details**
- Citation number and status
- Person information
- Violation and narrative
- Issue timestamp and deadline
- Remedy checklist
- Evidence gallery
- History
- Comments
- Resolve/reopen controls

**Citation search**
- Person
- Violation
- Status
- First-time/repeat offense
- Date
- Overdue flag
- Citation number

**Settings**
- Violation templates
- Party timezone
- Notification preferences
- Sync configuration
- Data export

## Resolution workflow

Resolving a citation must:

1. Verify organizer authorization.
2. Check whether required remedies are complete.
3. Require an explicit override reason if resolving despite incomplete required remedies.
4. Record resolved timestamp and actor.
5. Append a resolution event.
6. Cancel or supersede outstanding overdue notifications.
7. Queue the change for synchronization.

Reopening must preserve the prior resolution event.

### Acceptance criteria

- An organizer can issue, investigate, and resolve a citation using the interface.
- All status changes persist across restart.
- Required remedies are visible and actionable.
- Overdue status updates correctly without manual intervention.
- Public-facing views exclude private contact information.
- The UI is usable on a phone-sized screen.

---

# Phase 5 — Evidence attachments

Support image and optional document attachments.

Recommended initial permitted types:

- JPEG
- PNG
- WebP
- PDF

Use configurable file limits, with a reasonable default such as 10 MiB per attachment.

Do not initially support videos.

Store attachment binary data in managed local files, not directly in citation rows.

Each uploaded file must have:

- Generated storage key
- Validated MIME type
- Validated size
- SHA-256 checksum
- Attachment metadata row
- Associated citation
- Access-control rule

Use content inspection where practical rather than trusting filename extensions.

Strip image metadata where possible, or warn the organizer about metadata exposure before public sharing.

The original evidence should not automatically become publicly visible.

Require explicit publication approval.

Use opaque download identifiers and authenticated file-serving routes. Prevent path traversal, arbitrary file reads, and unrestricted uploads.

### Acceptance criteria

- Attachments survive application restarts.
- Citation deletion/voiding does not silently orphan evidence.
- Invalid uploads are rejected.
- File hashes match stored content.
- Files cannot be retrieved through guessed local filesystem paths.
- Public users cannot access private evidence.
- Attachment metadata and binary files are covered by backup/export procedures.

---

# Phase 6 — PostgreSQL synchronization

Implement offline-first synchronization.

SQLite remains the immediate local write target.

Remote PostgreSQL acts as the shared replica and coordination service.

## Connection configuration

Support a standard PostgreSQL connection URI through an extension-owned secret configuration reference.

Never store a database password in:

- `extension.yaml`
- Git-tracked configuration
- The browser
- API responses
- Diagnostic logs
- Citation records

Use TLS with certificate verification.

For Supabase, obtain a suitable connection string from the project dashboard. A persistent backend on an IPv4-only network can use the session pooler.

The PostgreSQL driver must run in the extension-owned service environment, not be installed globally into Hosaka's core environment.

## Synchronization architecture

Use an explicit outbox.

Local mutation transaction:

1. Apply the domain change to SQLite.
2. Increment entity revision.
3. Append citation event if applicable.
4. Append corresponding outbox operation.
5. Commit atomically.

Synchronization worker:

1. Read pending outbox entries.
2. Send idempotent operations to remote PostgreSQL.
3. Check expected remote revision.
4. Record successful acknowledgments.
5. Pull remote changes using a durable server-issued change cursor.
6. Apply remote updates transactionally.
7. Record synchronization checkpoints.
8. Retry failures with bounded exponential backoff.

Do not use local device timestamps as the sole source of ordering.

## Multi-device conflict rules

- Distinct citation IDs may be created independently.
- Use globally unique UUIDs.
- Display numbers must be assigned in a way that avoids cross-device collisions.
- Updates should use expected revisions or equivalent optimistic concurrency.
- Conflicting concurrent edits must be surfaced for organizer reconciliation.
- Citation resolution must not silently overwrite a concurrent reopening.
- Comments are independently append-only.
- Attachment objects are immutable once uploaded.
- Deletions use tombstones.

Do not implement last-write-wins as the default conflict policy.

The system should tolerate duplicate deliveries, network interruptions, and process crashes.

## Remote access design

A local trusted service may connect to PostgreSQL using narrowly scoped credentials.

Browsers must not receive raw PostgreSQL credentials.

If public comments and viewing are hosted remotely, use an authenticated API with separate guest permissions.

Do not expose unrestricted SQL or a database administration credential to public clients.

### Acceptance criteria

- Creating a citation offline succeeds.
- Reconnecting pushes pending citations.
- Remote changes are pulled correctly.
- Repeated sync does not duplicate records.
- Interrupted sync resumes safely.
- Two clients editing the same citation do not silently lose data.
- A failed remote write does not delete the local record.
- Database credentials never appear in frontend bundles or logs.
- Local operations remain available during a remote outage.

---

# Phase 7 — Notification and overdue system

Implement a local notification evaluator.

Initial functionality:

- Due soon
- Overdue
- Recently resolved
- Newly commented
- Unresolved required remedies

Notifications must be derived from persisted records.

Do not rely on a browser tab remaining open.

Use the approved service-backed scheduler or another explicitly managed execution mechanism.

Ensure jobs are idempotent.

Default alert channels:

- In-application notifications
- Organizer dashboard badges

Optional later integrations:

- Email
- SMS

Do not automatically contact partygoers merely because their information is stored.

External notifications require an opt-in workflow and a verified notification provider.

### Acceptance criteria

- Overdue items are detected after restart.
- Completed citations stop producing overdue reminders.
- Reopening a citation restores appropriate reminders.
- Repeated scheduler runs do not duplicate notifications.
- Offline alerts continue without PostgreSQL connectivity.

---

# Phase 8 — Virgozone and guest comments

Locate and inspect the existing Virgozone repository before beginning integration.

Determine:

- Its backend framework
- Authentication model
- Comment data model
- File upload capabilities
- Existing frontend components
- Service startup mechanism
- Dependencies
- Whether its current deployment exposes unsafe public administration routes

Do not assume compatibility.

Prefer reuse through an explicit adapter rather than copying unrelated framework internals.

## Guest experience

A guest should be able to:

- Open a citation-specific URL or QR code.
- Read public citation details.
- See the listed remedies.
- See whether the citation is resolved.
- View approved evidence.
- Add a comment or humorous appeal.
- Read approved comments.

Guests must not be able to:

- View private email addresses or phone numbers.
- Change remedies.
- Modify citation status.
- Retrieve unapproved evidence.
- Access organizer-only activity logs.
- Access PostgreSQL credentials.

## Comment moderation

Provide organizer controls to:

- Hide comments.
- Remove inappropriate content.
- Review pending submissions.
- Disable comments per citation.
- Rate-limit anonymous submissions.

All comments must be sanitized and rendered as text rather than executable HTML.

The public web interface must work independently of access to Hosaka's private administrative API.

### Acceptance criteria

- Citation pages are reachable through a controlled guest URL.
- Anonymous users cannot modify citation records.
- Private contact fields never appear in public API responses.
- Guest comments persist and synchronize.
- Abuse controls are effective.
- Virgozone integration can be disabled without breaking citation management.

---

# Phase 9 — Deployment and installation

Use the existing Hosaka extension installation contract.

The root `install.sh` must continue bootstrapping the generic extension framework.

Do not hardcode the Halloween application into the core installer.

Instead, provide a self-contained extension installation path using existing Hosaka lifecycle commands.

Any required service-backed extension host upgrade must be implemented as a separate platform change and covered by Hosaka installer tests.

For Halloween Citations:

- Store source in the canonical extension package location.
- Store SQLite, attachments, and runtime state in extension-data.
- Keep remote configuration separate from source.
- Preserve data on update and reinstall.
- Never enable or trust newly installed executable code automatically.
- Provide an explicit data backup/restore command or documented equivalent.
- Support a clean uninstall that preserves data unless explicit purge is requested.

## Acceptance criteria

- Fresh Hosaka installs continue to work.
- Halloween Citations can be installed without application-specific core changes.
- The extension can initialize its own database.
- Existing citation data survives an extension update.
- A reinstall does not silently erase attachments or sync state.
- A second clean machine can install the extension using its documentation.

---

# Phase 10 — Final end-to-end validation

Build an automated scenario representing the Halloween event.

Required fixture:

- 12 fictional attendees
- 8 violation types
- 30 citations
- Mix of first-time and repeat offenses
- Mix of open, resolved, void, and overdue citations
- Several remedies
- Several attachments
- Multiple comments
- Two simulated clients

Run the following workflow:

1. Create citations offline.
2. Restart the application.
3. Retrieve and verify records.
4. Resolve several remedies.
5. Reopen a citation.
6. Introduce conflicting edits.
7. Restore network access.
8. Synchronize with a disposable PostgreSQL instance.
9. Confirm convergence or explicitly surfaced conflicts.
10. Verify public/private field separation.
11. Restart the server and recover pending notifications.
12. Confirm that the main Hosaka application remains operational.

Use test data only. Never point automated destructive tests at a production database.

## Definition of done

The implementation is complete when an organizer can:

- Issue a citation.
- Identify the cited person.
- Record the offense.
- Specify a remedy and deadline.
- Attach evidence.
- Retrieve the citation.
- Track first/repeat offenses.
- Receive overdue alerts.
- Mark remedies completed.
- Resolve or reopen the citation.
- Use the application offline.
- Synchronize data with PostgreSQL.
- Allow guests to view and comment through a restricted public interface.

All functionality must be packaged independently of Hosaka core, except for explicitly approved, reusable platform capabilities.

## Agent operating instructions

Execute stages sequentially.

For each stage:

1. Inspect the current repository state.
2. Identify dependencies and platform limitations.
3. Implement only that stage's scope.
4. Add automated tests.
5. Run them.
6. Report actual pass/fail results.
7. Report changed files and any core modifications.
8. Commit the completed stage separately when repository workflow permits.

Do not skip ahead to implement the full web application before the data model is stable.

Do not falsely claim sandboxing, successful synchronization, or passing tests.

Do not put private database credentials in Git.

Do not rewrite existing working Hosaka infrastructure to solve a single application-specific problem.

**Architectural goal: Halloween Citations should become a reference implementation for sophisticated, persistent, service-backed Hosaka extensions—not a special feature embedded in the Hosaka core.**
