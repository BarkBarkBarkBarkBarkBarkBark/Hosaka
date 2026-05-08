#!/usr/bin/env bash
# gen_docs.sh — regenerate every artifact from docs/hosaka.features.yaml.
#
# This is the ONE command. CI runs it, you run it, the rabbit runs it.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python}"
echo "== gen_user_manual"
"$PY" scripts/gen_user_manual.py
echo "== gen_agent_context"
"$PY" scripts/gen_agent_context.py
echo "== gen_openapi_overlay (best-effort; needs docs/openapi.json)"
"$PY" scripts/gen_openapi_overlay.py || true
echo "done."
