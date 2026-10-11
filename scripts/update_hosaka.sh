#!/usr/bin/env bash
# Compatibility entry point; all updates use the operator CLI's single workflow.
set -euo pipefail

REPO_ROOT="${HOSAKA_REPO:-${HOSAKA_REPO_ROOT:-}}"
if [[ -z "$REPO_ROOT" && -f /etc/hosaka/repo_root ]]; then
  REPO_ROOT="$(cat /etc/hosaka/repo_root)"
fi
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  [[ -e "$REPO_ROOT/.git" ]] || REPO_ROOT="/home/operator/Hosaka"
fi
[[ -f "$REPO_ROOT/scripts/hosaka" ]] || { echo "Hosaka checkout not found; set HOSAKA_REPO." >&2; exit 1; }

if (( $# )) && [[ "$1" != -* && "$1" != "source" && "$1" != "local" && "$1" != "logs" && "$1" != "status" && "$1" != "help" ]]; then
  branch="$1"
  shift
  set -- --branch "$branch" "$@"
fi
exec env HOSAKA_REPO="$REPO_ROOT" bash "$REPO_ROOT/scripts/hosaka" update "$@"
