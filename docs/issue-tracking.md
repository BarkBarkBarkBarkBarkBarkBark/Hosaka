# Issue tracking

Hosaka tracks development through GitHub Issues. One persistent backlog
serves both the human operator and any agent acting on the codebase.
The contract is short:

> **No issue, no work.**
>
> Any non-trivial bug, feature, UX problem, hardware integration,
> install path, or agent-discovered task becomes a tracked issue
> *before* code changes. Progress and verification go in comments.
> Issues close only after evidence of a fix.

## Why Hosaka uses persistent issues

- Durable memory across sessions, machines, and operators.
- Same surface for humans and agents — fewer "where did we leave off?"
  conversations.
- Issues are the unit of work that survives appliance reinstalls,
  Docker rebuilds, and laptop swaps.
- GitHub already runs the API, search, notifications, and access control.
  We do not need to host another tracker yet.

The wrapper lives at [`hosaka/issues/`](../hosaka/issues/) and exposes a
small CLI: `hosaka issue ...`. Behind it is a pluggable
`IssueBackend` ABC so we can swap in `git-bug`, Taskwarrior, or Forgejo's
`tea` later without changing operator muscle memory.

## Setup

1. Install GitHub CLI (`gh`):

   ```bash
   sudo apt install gh        # Debian / Raspberry Pi OS
   ```

2. Authenticate once per machine:

   ```bash
   gh auth login
   ```

   Tokens are owned by `gh` (stored under `~/.config/gh/`). Hosaka never
   reads or persists them.

3. Bootstrap the Hosaka label set in the repo (one-time, idempotent):

   ```bash
   ./scripts/bootstrap_issue_labels.sh
   ```

4. Verify everything end-to-end:

   ```bash
   hosaka issue doctor
   ```

   You should see four `[ok]` checks and the detected `OWNER/NAME`.

## Daily workflow

```bash
hosaka issue list                                    # what is on the backlog
hosaka issue new "Fix /api/gemini body shape"        # open a new tracked task
hosaka issue start 12                                # mark in-progress
hosaka issue note 12 "Reproduced on Pi 5, see log."  # add context as you go
hosaka issue done 12 "Fixed in commit abc1234; smoke passed."
```

Commit messages can close issues automatically:

```bash
git commit -m "Fix /api/gemini body shape. Closes #12"
```

## Agent workflow

The agent contract follows the same rule, in order:

1. `hosaka issue doctor` — fail fast if gh/auth/repo is broken.
2. `hosaka issue list` — search for a matching open issue before
   creating a duplicate.
3. If no match, `hosaka issue new` with a clear title and the right
   template (`-t bug | feature | default`).
4. `hosaka issue start <n>` and `hosaka issue note <n> "..."` as work
   progresses. Comment meaningful findings, blockers, verification
   evidence, and any commands that produced them.
5. Run tests / smoke verification. Comment the result.
6. `hosaka issue done <n> "..."` only after the issue is actually
   resolved with evidence.

Safety guardrails:

- The CLI refuses to close without a comment unless `--force` is passed.
- Every backend call uses `subprocess.run` with an argv array; never
  `shell=True`.
- No GitHub tokens live in repo files.
- Label-missing is non-fatal — issues still create, the missing label
  is silently dropped.

## Command reference

```text
hosaka issue doctor                check gh install/auth/repo detection
hosaka issue new "TITLE" [-b BODY] [-t default|bug|feature] [-l LABEL]
                                   create an issue (`hosaka`+`agent` auto-applied)
hosaka issue list [--state open|closed|all]
                                   list issues, default open
hosaka issue show N                full details for one issue
hosaka issue note N "TEXT"         add a comment
hosaka issue start N               mark in-progress (label or comment)
hosaka issue done N "CLOSING"      close with a final comment

Global flags:
  --repo OWNER/NAME                override repo (default: infer from git remote)
  --json                           machine-readable output for agents
```

Labels seeded by `bootstrap_issue_labels.sh`:

| label         | meaning                                                    |
|---------------|------------------------------------------------------------|
| `hosaka`      | tracked by the Hosaka workflow (default on every new issue)|
| `agent`       | created or worked by an automated agent                    |
| `bug`         | something is broken                                        |
| `feature`     | new capability or enhancement                              |
| `hardware`    | Pi, peripherals, voice, kiosk display                      |
| `install`     | install / setup / bootstrap path                           |
| `ux`          | UX, copy, or interaction design                            |
| `in-progress` | actively being worked on                                   |
| `blocked`     | blocked on external dependency or decision                 |
| `needs-human` | cannot be safely completed by an agent alone               |
| `audit-seed`  | seeded from `docs/` audits during the rollout              |

## Troubleshooting

`hosaka issue doctor` is the first stop for any failure. Common cases:

- **`gh installed FAIL`** — install via `sudo apt install gh`.
- **`gh authed FAIL`** — `gh auth login`. Pick HTTPS + browser auth.
  Token must have at least the `repo` scope.
- **`inside git repo FAIL`** — `cd` into the Hosaka checkout, or pass
  `--repo OWNER/NAME` explicitly.
- **`repo detected FAIL`** — your `origin` remote is unparseable. Either
  fix the remote (`git remote set-url origin git@github.com:OWNER/NAME.git`)
  or always pass `--repo`.

If `hosaka issue new` fails with a label error, the label probably does
not exist yet on the repo. Re-run `scripts/bootstrap_issue_labels.sh` —
the wrapper retries once without labels as a safety net, so the issue
still lands.

## Future backends

The `IssueBackend` ABC in [`hosaka/issues/backend.py`](../hosaka/issues/backend.py)
exists so we can layer in alternatives without changing the CLI:

- **`git-bug`** — distributed/offline-first tracker embedded in the
  git object database. Useful when Hosaka is deployed off-grid and
  GitHub is not reachable. Issues sync back when connectivity returns.
- **Taskwarrior** — local personal daily task queue, separate from
  cross-team backlog. Useful as an operator-private layer.
- **Forgejo / Gitea `tea`** — if Hosaka self-hosts git later, the same
  CLI surface keeps working.

These are intentionally not implemented yet — the YAML spec at
[`docs/issue_tracker.yaml`](./issue_tracker.yaml) is the source of truth
for the planned shape.
