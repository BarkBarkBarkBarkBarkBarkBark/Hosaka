#!/usr/bin/env bash
# hosaka-canary.sh — phase 11 canary control.
#
# Subcommands:
#   status                   show current git ref + stage marker
#   pin <ref>                record this ref as the device's "good" ref
#   rollback                 git checkout the previous good ref + restart services
#   promote <stage>          stage marker bookkeeping (stage_0_local|stage_1_ring|stage_2_fleet)
#
# This script never touches other devices. Promotion across the fleet is a
# manual decision recorded as an event for audit.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${HOSAKA_CANARY_DIR:-$REPO_ROOT/runtime/canary}"
mkdir -p "$STATE_DIR"
GOOD_REF_FILE="$STATE_DIR/good_ref"
PREV_REF_FILE="$STATE_DIR/prev_ref"
STAGE_FILE="$STATE_DIR/stage"

cmd="${1:-status}"
shift || true

current_ref() { git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown"; }

emit_event() {
    local event="$1" status="$2" payload="${3:-{}}"
    python - "$event" "$status" "$payload" <<'PY' || true
import json, sys
sys.path.insert(0, ".")
try:
    from hosaka.obs import emit
    event, status, payload = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        payload_obj = json.loads(payload)
    except Exception:
        payload_obj = {"raw": payload}
    emit(event, kind="recovery", source="scripts/hosaka-canary.sh",
         level="info", status=status, payload=payload_obj)
except Exception as exc:
    print(f"[canary] obs emit skipped: {exc}", file=sys.stderr)
PY
}

case "$cmd" in
    status)
        echo "current_ref: $(current_ref)"
        echo "good_ref:    $(cat "$GOOD_REF_FILE" 2>/dev/null || echo none)"
        echo "prev_ref:    $(cat "$PREV_REF_FILE" 2>/dev/null || echo none)"
        echo "stage:       $(cat "$STAGE_FILE" 2>/dev/null || echo stage_0_local)"
        ;;
    pin)
        ref="${1:-$(current_ref)}"
        if [ -f "$GOOD_REF_FILE" ]; then
            mv "$GOOD_REF_FILE" "$PREV_REF_FILE"
        fi
        echo "$ref" > "$GOOD_REF_FILE"
        echo "pinned good_ref to $ref"
        emit_event "CANARY_PINNED" "ok" "{\"ref\":\"$ref\"}"
        ;;
    rollback)
        if [ ! -f "$PREV_REF_FILE" ]; then
            echo "no prev_ref recorded; nothing to rollback to" >&2
            emit_event "CANARY_ROLLBACK" "failed" '{"reason":"no_prev_ref"}'
            exit 2
        fi
        target="$(cat "$PREV_REF_FILE")"
        echo "rolling back to $target"
        git -C "$REPO_ROOT" fetch --all --tags --quiet || true
        git -C "$REPO_ROOT" checkout "$target"
        emit_event "STATE_RECOVERED" "ok" "{\"ref\":\"$target\",\"action\":\"rollback\"}"
        echo "ok. restart services manually if needed (e.g. systemctl restart hosaka-webserver)."
        ;;
    promote)
        stage="${1:-stage_0_local}"
        case "$stage" in
            stage_0_local|stage_1_ring|stage_2_fleet) ;;
            *) echo "unknown stage: $stage" >&2; exit 2 ;;
        esac
        echo "$stage" > "$STAGE_FILE"
        echo "stage set to $stage"
        emit_event "CANARY_PROMOTED" "ok" "{\"stage\":\"$stage\"}"
        ;;
    *)
        echo "usage: $0 {status|pin [ref]|rollback|promote <stage>}" >&2
        exit 2
        ;;
esac
