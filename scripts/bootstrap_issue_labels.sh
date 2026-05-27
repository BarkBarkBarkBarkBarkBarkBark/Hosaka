#!/usr/bin/env bash
# bootstrap_issue_labels.sh — create / update the Hosaka GitHub label set.
#
# Idempotent: uses `gh label create --force` so re-runs only update colour
# + description for labels that already exist. Honours $HOSAKA_REPO if set,
# otherwise lets `gh` infer the repo from the git remote.
#
# Usage:
#   ./scripts/bootstrap_issue_labels.sh
#   HOSAKA_REPO=owner/name ./scripts/bootstrap_issue_labels.sh

set -euo pipefail

REPO_ARGS=()
if [[ -n "${HOSAKA_REPO:-}" ]]; then
  REPO_ARGS=(--repo "$HOSAKA_REPO")
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI not on PATH. Install: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated. Run: gh auth login" >&2
  exit 1
fi

# Label set mirrors docs/issue_tracker.yaml labels.preferred. Colours are
# stable so reruns don't churn the UI. Format: name|color|description
LABELS=(
  "hosaka|5319e7|Issue tracked by the Hosaka workflow"
  "agent|0e8a16|Created or worked by an automated agent"
  "bug|d73a4a|Something is broken"
  "feature|a2eeef|New capability or enhancement"
  "hardware|fbca04|Pi, peripherals, voice, kiosk display"
  "install|c2e0c6|Install / setup / bootstrap path"
  "ux|d4c5f9|UX, copy, or interaction design"
  "in-progress|fef2c0|Actively being worked on"
  "blocked|b60205|Blocked on external dependency or decision"
  "needs-human|e99695|Cannot be safely completed by an agent alone"
  "audit-seed|cccccc|Seeded from docs audits (CLAIMS_AUDIT, app_framework_progress, etc.)"
)

echo "bootstrapping ${#LABELS[@]} labels on ${HOSAKA_REPO:-<inferred>}..."
for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color desc <<<"$entry"
  if gh label create "$name" \
       --color "$color" \
       --description "$desc" \
       --force \
       "${REPO_ARGS[@]}" >/dev/null 2>&1; then
    printf '  [ok]   %s\n' "$name"
  else
    printf '  [warn] %s (skipped)\n' "$name"
  fi
done
echo "done."
