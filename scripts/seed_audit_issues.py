"""One-shot seeder for the Hosaka audit-derived backlog.

Reads a hardcoded list of (title, template, labels, body) entries and
calls ``hosaka.issues.cli`` to file each. Idempotency is best-effort —
re-running will create duplicates because the MVP does not implement
search-by-title (see seeded issue #2). Run once, then delete or move
under ``scripts/archive/``.

Usage:
    python scripts/seed_audit_issues.py            # files all
    python scripts/seed_audit_issues.py --dry-run  # just print titles
    python scripts/seed_audit_issues.py --limit 3  # smoke test first 3
    python scripts/seed_audit_issues.py --start 12 # resume from index 12
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running as `python scripts/seed_audit_issues.py` from the repo root
# without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hosaka.issues.cli import main as issue_cli_main


@dataclass
class Seed:
    title: str
    template: str  # "default" | "bug" | "feature"
    labels: list[str]  # extra labels beyond hosaka,agent,audit-seed
    body: str


SEEDS: list[Seed] = [
    Seed(
        title="Adopt 'no issue, no work' contract repo-wide",
        template="feature",
        labels=["ux"],
        body=(
            "Roll out the contract from docs/issue_tracker.yaml: every non-trivial "
            "change starts with an issue. This issue is the rollout announcement; "
            "link it from README and from any CONTRIBUTING / agent contract files. "
            "Reference: docs/issue-tracking.md (new), docs/issue_tracker.yaml core_rule."
        ),
    ),
    Seed(
        title="Add duplicate-title detection to `hosaka issue new`",
        template="feature",
        labels=[],
        body=(
            "MVP creates duplicates silently. Before filing, search open+closed by "
            "title fragment via `gh issue list --search` and warn / require --force. "
            "Reference: docs/issue_tracker.yaml mvp_acceptance_criteria.nice_to_have."
        ),
    ),
    Seed(
        title="Wire `hosaka issue start` to a real `in-progress` label and richer `show --json`",
        template="feature",
        labels=[],
        body=(
            "Current `start` falls back to a comment if the label is missing. With the "
            "label bootstrapped repo-wide, ensure `start` always applies it and that "
            "`show --json` returns the same body/comments shape as the GitHub REST view. "
            "Reference: docs/issue_tracker.yaml nice_to_have."
        ),
    ),
    Seed(
        title="Fix `/api/gemini` body/parse mismatch with frontend/src/llm/gemini.ts",
        template="bug",
        labels=[],
        body=(
            "On the appliance, `/ask` and `/chat` silently fail because the FastAPI "
            "handler reads `contents`/`messages` while the client sends `{ model, "
            "prompt, history, system }` and expects `data.text`, but the server "
            "returns `candidates[].content.parts[].text`. Align either side. "
            "Reference: docs/CLAIMS_AUDIT.md TOP-5 #1 + section '/ask vs Picoclaw'."
        ),
    ),
    Seed(
        title="Implement or remove `!shell` -> `shell_reply` WebSocket path",
        template="bug",
        labels=[],
        body=(
            "`agentClient.runShell` sends `{ type: 'shell', cmd }` over /ws/agent "
            "but the server never returns `shell_reply`, so the client times out "
            "forever. Either implement the path in hosaka/web/server.py or stop "
            "advertising `!shell` on the appliance build. "
            "Reference: docs/CLAIMS_AUDIT.md TOP-5 #2."
        ),
    ),
    Seed(
        title="`setup_hosaka.sh` references nonexistent `hosaka-console.service`",
        template="bug",
        labels=["install"],
        body=(
            "Console boot via setup script is broken: systemd/ ships "
            "`hosaka-field-terminal.service`, but setup enables "
            "`hosaka-console.service`. Either rename in setup or add the missing "
            "unit. Also fix the inconsistent 3/3 vs 3/4 vs 4/4 step counter copy. "
            "Reference: docs/CLAIMS_AUDIT.md TOP-5 #3."
        ),
    ),
    Seed(
        title="README 'What you get' lists commands not in commands.ts",
        template="bug",
        labels=["ux"],
        body=(
            "README advertises `/draw`, `/restart`, `/update`, `/net`, `/ping`, "
            "`/dns`, `/scan`, `/code` but the shell dispatcher does not implement "
            "them. Either implement, drop, or relabel as aspirational. Likely fix: "
            "regenerate the README list from `getCommands()`. "
            "Reference: docs/CLAIMS_AUDIT.md TOP-5 #4 + section 'What you get'."
        ),
    ),
    Seed(
        title="`docker/dev.sh status` curls `/progress` but app exposes `/setup/progress`",
        template="bug",
        labels=[],
        body=(
            "One-line URL fix. Today `./docker/dev.sh status` always 404s. "
            "Reference: docs/CLAIMS_AUDIT.md section 'Docker'."
        ),
    ),
    Seed(
        title="Unify Python TUI vs SPA plant models (or document the split)",
        template="bug",
        labels=["ux"],
        body=(
            "Python TUI persists plant state to `~/.hosaka/plant.json` with decay "
            "and birth counter; the SPA only renders `plantTicks` in memory with "
            "no storage and no decay. README implies one global plant. Pick one: "
            "share state via API, or split copy. "
            "Reference: docs/CLAIMS_AUDIT.md section 'Plant'."
        ),
    ),
    Seed(
        title="Persist SPA plant state across reboots",
        template="feature",
        labels=["ux"],
        body=(
            "Closely related to the plant-unify issue: the SPA plant should at "
            "minimum localStorage its tick count and (ideally) round-trip with the "
            "Python TUI plant state through an API. "
            "Reference: docs/claims.md open-work #4."
        ),
    ),
    Seed(
        title="`/netscan` should use installed arp-scan/nmap, not synthetic traffic",
        template="bug",
        labels=[],
        body=(
            "install_hosaka.sh installs both, but the shell command uses synthetic "
            "`generatePacket` + optional `ss` via agent. Pipe through a backend "
            "endpoint that shells out to arp-scan/nmap on the appliance. "
            "Reference: docs/CLAIMS_AUDIT.md section '/netscan'."
        ),
    ),
    Seed(
        title="`/messages` webhook flow needs server-side relay for CORS-restricted endpoints",
        template="feature",
        labels=[],
        body=(
            "Today `MessagesPanel.tsx` fetches webhooks directly from the browser; "
            "Discord/Slack often block browser POSTs. Add a small Hosaka backend "
            "relay so 'no backend required' can finally be true. "
            "Reference: docs/CLAIMS_AUDIT.md section '/messages'."
        ),
    ),
    Seed(
        title="`/agent off` cannot persist across reload (`loadAgentConfig` forces enabled=true)",
        template="bug",
        labels=[],
        body=(
            "Even after `/agent off`, a reload re-enables the agent. Stop forcing "
            "`enabled: true` in `loadAgentConfig`, or split runtime defaults from "
            "persisted state. "
            "Reference: docs/CLAIMS_AUDIT.md section 'slash commands'."
        ),
    ),
    Seed(
        title="README HOSAKA_BOOT_MODE table says `web`; scripts use `headless`",
        template="bug",
        labels=["install"],
        body=(
            "Docs/code drift. Pick one name and align: scripts/setup_hosaka.sh + "
            "scripts/switch_boot_mode.sh use `headless`; README config table says "
            "`web`. "
            "Reference: docs/CLAIMS_AUDIT.md section 'boot modes'."
        ),
    ),
    Seed(
        title="Add AP-fallback Wi-Fi mode (hostapd + captive portal) for fresh installs",
        template="feature",
        labels=["install", "hardware"],
        body=(
            "Fresh Pi with no network can't get past first-boot. Bring up an AP and "
            "captive-portal page so the operator can pick a network from a phone. "
            "Reference: docs/claims.md open-work #1."
        ),
    ),
    Seed(
        title="Tailscale auto-join during install (avoid manual `tailscale up`)",
        template="feature",
        labels=["install"],
        body=(
            "Today the operator must manually `tailscale up` after install. "
            "Generate or accept an auth key during setup and run tailscale up "
            "non-interactively. Document key storage in hosaka secrets. "
            "Reference: docs/claims.md open-work #5."
        ),
    ),
    Seed(
        title="Picoclaw model selection round-trip in kiosk Settings drawer",
        template="feature",
        labels=["ux"],
        body=(
            "Settings drawer should be able to read the current Picoclaw model + "
            "write a new one and have it stick across restarts. Today the "
            "round-trip is broken. "
            "Reference: docs/claims.md open-work #3."
        ),
    ),
    Seed(
        title="Implement `hosaka radio` (local + Wikimedia public-domain playback)",
        template="feature",
        labels=[],
        body=(
            "The app registry models `hosaka radio` but nothing launches. First "
            "milestone: local-files + Wikimedia public-domain recordings with "
            "background playback. AM/FM/wideband later. "
            "Reference: docs/app_framework_progress.md near-term #4 + 'hosaka radio direction'."
        ),
    ),
    Seed(
        title="Electron launch bridges for external apps (Spotify, Kindle, Discord)",
        template="feature",
        labels=[],
        body=(
            "Registry advertises these but nothing actually launches. Add Electron "
            "shell handoff that respects host capability + install policy. "
            "Reference: docs/app_framework_progress.md near-term #1, #5."
        ),
    ),
    Seed(
        title="Add capability detection for installed external apps",
        template="feature",
        labels=[],
        body=(
            "Before showing launch UI for Spotify/Kindle/etc., detect whether the "
            "app is actually installed on the host. Surface a clear install hint "
            "when missing. "
            "Reference: docs/app_framework_progress.md near-term #2."
        ),
    ),
    Seed(
        title="Enforce `disable-for-web` policy in runtime code, not only metadata",
        template="bug",
        labels=[],
        body=(
            "appRegistry.ts marks apps with policy, but runtime code does not "
            "consistently honor it. Public web deployments should be unable to "
            "trigger Electron-only flows even if the UI button is rendered. "
            "Reference: docs/app_framework_progress.md near-term #3."
        ),
    ),
    Seed(
        title="Persist voice agent-lane jobs beyond process memory",
        template="feature",
        labels=[],
        body=(
            "Today the voice job store is in-memory; a webserver restart loses "
            "every queued/running job. Move to a small on-disk store under "
            "`~/.hosaka/voice/jobs/` so history and recovery work. "
            "Reference: docs/voice.md 'concrete tasks for future self'."
        ),
    ),
    Seed(
        title="Add visible cancel action for a running local voice job",
        template="feature",
        labels=["ux"],
        body=(
            "Once you press-to-talk you cannot cancel a long-running job without "
            "reloading. Expose a cancel control in the orb drawer that hits a new "
            "cancel endpoint on /api/voice/. "
            "Reference: docs/voice.md 'concrete tasks for future self'."
        ),
    ),
    Seed(
        title="Replace voice job status polling with WebSocket/SSE push",
        template="feature",
        labels=[],
        body=(
            "The frontend currently polls job status. Move to WebSocket or SSE so "
            "transcript progress updates flow without polling churn. "
            "Reference: docs/voice.md medium-term #1, 'progress is polling, not push'."
        ),
    ),
    Seed(
        title="Add tests around voice_api.py job lifecycle and public-mode restrictions",
        template="feature",
        labels=[],
        body=(
            "voice_api.py currently has no direct tests. Cover: job create/transition/"
            "complete, public-mode tool restrictions, and the realtime token mint "
            "path. "
            "Reference: docs/voice.md 'concrete tasks for future self'."
        ),
    ),
    Seed(
        title="Unify todo stores (~/.hosaka_todos.json and ~/.hosaka/voice_todos.jsonl)",
        template="feature",
        labels=[],
        body=(
            "Two parallel todo stores exist today, which makes sharing/sync hard "
            "(see Telegram share script). Pick one canonical store + migrate, then "
            "let the voice tooling and main_console.py both read/write it. "
            "Reference: docs/agent_self_audit_2026-04-24.md section 'Recommended next improvements'."
        ),
    ),
]


def _file_one(seed: Seed) -> int:
    argv = [
        "new",
        seed.title,
        "--template", seed.template,
        "--body", seed.body,
        "--label", "audit-seed",
    ]
    for lab in seed.labels:
        argv += ["--label", lab]
    return issue_cli_main(argv)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Hosaka backlog from audit docs.")
    parser.add_argument("--dry-run", action="store_true", help="Print titles only")
    parser.add_argument("--limit", type=int, default=0, help="Only file the first N (0 = all)")
    parser.add_argument("--start", type=int, default=1, help="Start at 1-based index N (default 1)")
    args = parser.parse_args()

    start_idx = max(1, args.start) - 1
    seeds = SEEDS[start_idx:]
    if args.limit:
        seeds = seeds[: args.limit]
    failures = 0
    for i, seed in enumerate(seeds, start_idx + 1):
        if args.dry_run:
            extra = ",".join(["audit-seed", *seed.labels])
            print(f"{i:2d}. [{seed.template:<7}] ({extra}) {seed.title}")
            continue
        print(f"\n[{i}/{len(SEEDS)}] filing: {seed.title}")
        rc = _file_one(seed)
        if rc != 0:
            failures += 1
            print(f"  -> rc={rc}", file=sys.stderr)
    if failures:
        print(f"\ndone with {failures} failure(s)")
        return 1
    print(f"\ndone — {len(seeds)} issue(s) filed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
