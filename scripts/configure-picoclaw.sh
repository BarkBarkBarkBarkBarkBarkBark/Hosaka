#!/usr/bin/env bash
# Configure Picoclaw for Hosaka with one command.
#
# Goals:
# - If Picoclaw is missing, detect OS/arch and install the right release.
# - Bootstrap Hosaka's Picoclaw workspace.
# - If Picoclaw has no model/API key, import OPENAI_API_KEY from the current
#   environment, Hosaka's llm.json, or a local .env file without printing it.
# - Run interactive `picoclaw onboard` only when a real TTY is available;
#   otherwise print the exact next command and keep the non-interactive path
#   working for Hosaka's browser terminal.

set -euo pipefail

PREFIX="${PICOCLAW_PREFIX:-$HOME/.local}"
MODEL="${PICOCLAW_MODEL:-gpt-4o-mini}"
API_BASE="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
RUN_ONBOARD="auto"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<USAGE
configure-picoclaw.sh — install + configure Picoclaw for Hosaka

Usage:
  scripts/configure-picoclaw.sh [--onboard|--no-onboard] [--model MODEL] [--api-base URL]

Options:
  --onboard       run interactive 'picoclaw onboard' after install/config if TTY is available
  --no-onboard    skip interactive onboarding; use non-interactive model setup only
  --model MODEL   model id/alias to set for Picoclaw (default: gpt-4o-mini)
  --api-base URL  OpenAI-compatible API base (default: https://api.openai.com/v1)

This command is safe to run from Hosaka's browser terminal. If an interactive
TTY is required, it prints the exact follow-up command instead of hanging.
USAGE
}

while (( $# )); do
  case "$1" in
    --onboard)
      RUN_ONBOARD="yes"
      shift
      ;;
    --no-onboard)
      RUN_ONBOARD="no"
      shift
      ;;
    --model)
      [[ $# -ge 2 ]] || { echo "--model needs a value" >&2; exit 2; }
      MODEL="$2"
      shift 2
      ;;
    --model=*)
      MODEL="${1#*=}"
      shift
      ;;
    --api-base)
      [[ $# -ge 2 ]] || { echo "--api-base needs a value" >&2; exit 2; }
      API_BASE="$2"
      shift 2
      ;;
    --api-base=*)
      API_BASE="${1#*=}"
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

note() { printf '› %s\n' "$*"; }
ok() { printf '✓ %s\n' "$*"; }
warn() { printf '! %s\n' "$*"; }

discover_picoclaw() {
  if [[ -n "${PICOCLAW_BIN:-}" && -x "${PICOCLAW_BIN:-}" ]]; then
    printf '%s\n' "$PICOCLAW_BIN"
    return 0
  fi
  if command -v picoclaw >/dev/null 2>&1; then
    command -v picoclaw
    return 0
  fi
  if [[ -x "$PREFIX/bin/picoclaw" ]]; then
    printf '%s\n' "$PREFIX/bin/picoclaw"
    return 0
  fi
  return 1
}

install_if_missing() {
  local bin=""
  if bin="$(discover_picoclaw 2>/dev/null)"; then
    ok "picoclaw found at $bin"
    PICOCLAW_BIN="$bin"
    export PICOCLAW_BIN
    return 0
  fi

  note "picoclaw not found — installing for $(uname -s) $(uname -m)"
  bash "$REPO_ROOT/scripts/install-picoclaw.sh" --no-runtime
  bin="$(discover_picoclaw)"
  PICOCLAW_BIN="$bin"
  export PICOCLAW_BIN
  ok "picoclaw installed at $PICOCLAW_BIN"
}

bootstrap_runtime() {
  local py="${PYTHON:-python3}"
  if [[ -x "$REPO_ROOT/../.venv/bin/python" ]]; then
    py="$REPO_ROOT/../.venv/bin/python"
  elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    py="$REPO_ROOT/.venv/bin/python"
  fi
  note "bootstrapping Hosaka runtime into ~/.picoclaw/workspace"
  "$py" "$REPO_ROOT/scripts/bootstrap_picoclaw_runtime.py" --home "$HOME"
  ok "runtime ready"
}

read_openai_key() {
  # Prints the key to stdout for command substitution only. Callers must not log it.
  python3 - "$REPO_ROOT" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

repo = Path(sys.argv[1])

for name in ("OPENAI_API_KEY", "HOSAKA_OPENAI_API_KEY"):
    value = os.environ.get(name, "").strip().strip('"').strip("'")
    if value:
        print(value)
        raise SystemExit(0)

paths = []
state_path = os.environ.get("HOSAKA_STATE_PATH", "").strip()
if state_path:
    paths.append(Path(state_path).expanduser().parent / "llm.json")
paths.extend([
    Path.home() / ".hosaka" / "llm.json",
    Path("/var/lib/hosaka/llm.json"),
])
for path in paths:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    value = str(data.get("api_key") or "").strip()
    if value:
        print(value)
        raise SystemExit(0)

for env_path in (repo / ".env", Path.home() / ".hosaka" / ".env"):
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        continue
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "OPENAI_API_KEY":
            continue
        try:
            parts = shlex.split(value, comments=False, posix=True)
            value = parts[0] if parts else ""
        except Exception:
            value = value.strip().strip('"').strip("'")
        if value:
            print(value)
            raise SystemExit(0)
PY
}

picoclaw_status() {
  "$PICOCLAW_BIN" --no-color status 2>&1 || true
}

has_openai_key_in_picoclaw() {
  picoclaw_status | grep -Eiq 'OpenAI API:[[:space:]]*(set|✓)'
}

configure_model_from_key() {
  local key="$1"
  if [[ -z "$key" ]]; then
    return 1
  fi
  note "importing OpenAI key into Picoclaw model config (key hidden)"
  set +x
  set +e
  "$PICOCLAW_BIN" --no-color model add \
    --api-base "$API_BASE" \
    --api-key "$key" \
    --model "$MODEL" \
    --name "$MODEL" >/tmp/hosaka-picoclaw-model-add.log 2>&1
  local rc=$?
  set -e
  if (( rc != 0 )); then
    warn "picoclaw model setup failed; last output:"
    sed -n '1,80p' /tmp/hosaka-picoclaw-model-add.log
    return "$rc"
  fi
  ok "Picoclaw model '$MODEL' configured"
  save_key_into_hosaka_secrets "$key" || true
}

# Mirror the same key into the Hosaka-native secrets store so the voice
# daemon and webserver can resolve it without poking at picoclaw internals.
# Failure here is non-fatal — picoclaw still has the key as a fallback.
save_key_into_hosaka_secrets() {
  local key="$1"
  [[ -n "$key" ]] || return 0

  local py=""
  for candidate in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/.hosakavenv/bin/python" python python3; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      py="$candidate"
      break
    fi
  done
  if [[ -z "$py" ]]; then
    warn "no python found to mirror key into Hosaka secrets store"
    return 0
  fi

  note "mirroring key into Hosaka secrets store (~/.hosaka/secrets.json)"
  local extra_path=""
  [[ -d "$REPO_ROOT/hosaka" ]] && extra_path="$REPO_ROOT"
  if ! PYTHONPATH="$extra_path${PYTHONPATH:+:$PYTHONPATH}" \
       "$py" -m hosaka.secrets set OPENAI_API_KEY "$key" --no-mirror \
       >/tmp/hosaka-secrets-import.log 2>&1; then
    warn "could not write Hosaka secrets store; see /tmp/hosaka-secrets-import.log"
    return 0
  fi

  if command -v sudo >/dev/null 2>&1; then
    note "mirroring secrets to /etc/hosaka/env (requires sudo)"
    if ! sudo -E env "PYTHONPATH=$extra_path${PYTHONPATH:+:$PYTHONPATH}" \
         "$py" -m hosaka.secrets mirror >/tmp/hosaka-secrets-mirror.log 2>&1; then
      warn "could not mirror to /etc/hosaka/env; see /tmp/hosaka-secrets-mirror.log"
      warn "rerun: sudo -E $py -m hosaka.secrets mirror"
    else
      ok "/etc/hosaka/env updated"
    fi
  else
    warn "sudo not present; run later: $py -m hosaka.secrets mirror"
  fi
}

harden_picoclaw_config() {
  python3 - "$REPO_ROOT" "$HOME" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
home = Path(sys.argv[2]).expanduser().resolve()
path = home / ".picoclaw" / "config.json"
if not path.exists():
    raise SystemExit(0)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

workspace = str(home / ".picoclaw" / "workspace")
defaults = data.setdefault("agents", {}).setdefault("defaults", {})
defaults["workspace"] = workspace
defaults["restrict_to_workspace"] = False
defaults["allow_read_outside_workspace"] = True
defaults.setdefault("model_name", "gpt-4o-mini")
defaults["max_tokens"] = 4096
defaults.setdefault("max_tool_iterations", 50)

tools = data.setdefault("tools", {})
tools["allow_read_paths"] = ["/"]
write_paths = tools.get("allow_write_paths")
if not isinstance(write_paths, list):
    write_paths = []
for candidate in (str(home), str(repo), "/tmp"):
    if candidate not in write_paths:
        write_paths.append(candidate)
tools["allow_write_paths"] = write_paths

# Picoclaw 0.2.8 may prefer OpenAI's native web_search_preview tool for OpenAI
# models. Some chat-compatible paths reject that tool type. Hosaka works better
# with Picoclaw's normal tool layer unless the operator explicitly opts in.
web = tools.setdefault("web", {})
web["prefer_native"] = False

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

maybe_onboard() {
  if [[ "$RUN_ONBOARD" == "no" ]]; then
    return 0
  fi
  if [[ "$RUN_ONBOARD" == "auto" && -f "$HOME/.picoclaw/config.json" ]]; then
    return 0
  fi
  if [[ -t 0 && -t 1 ]]; then
    note "starting interactive Picoclaw onboarding"
    "$PICOCLAW_BIN" onboard
    return 0
  fi
  warn "interactive onboarding needs a real TTY"
  echo "  Open Hosaka's host terminal, or run this from SSH/macOS Terminal:"
  echo "  $PICOCLAW_BIN onboard"
  echo "  If you already configured the model key above, onboarding can be skipped for local Hosaka chat."
}

main() {
  echo "Hosaka Picoclaw configure"
  echo "signal steady"
  echo

  install_if_missing
  bootstrap_runtime

  echo
  note "checking Picoclaw status"
  picoclaw_status | sed -n '1,80p'

  if has_openai_key_in_picoclaw; then
    ok "Picoclaw config exists; checking model setup is complete enough to run"
  else
    local key=""
    key="$(read_openai_key || true)"
    if [[ -n "$key" ]]; then
      configure_model_from_key "$key"
    else
      warn "no OpenAI key found in env, Hosaka llm.json, or local .env"
      echo "  In Hosaka, use /settings or the inline key prompt first."
      echo "  Then rerun: hosaka configure picoclaw"
    fi
  fi

  harden_picoclaw_config

  maybe_onboard

  echo
  note "final status"
  picoclaw_status | sed -n '1,120p'
  echo
  echo "next: restart local dev so the backend inherits PATH/config: hosaka dev -fresh"
}

main "$@"
