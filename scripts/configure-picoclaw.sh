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
MODEL="${PICOCLAW_MODEL:-qwen2.5}"
MODEL_TARGET="${PICOCLAW_MODEL_TARGET:-qwen2.5:0.5b}"
API_BASE="${OPENAI_BASE_URL:-${HOSAKA_OLLAMA_BASE_URL:-http://100.78.174.79:11434/v1}}"
RUN_ONBOARD="auto"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_HOME="${PICOCLAW_ACCOUNT_HOME:-}"
if [[ -z "$TARGET_HOME" && -n "${PICOCLAW_HOME:-}" ]]; then
  case "$PICOCLAW_HOME" in
    */.picoclaw) TARGET_HOME="${PICOCLAW_HOME%/.picoclaw}" ;;
  esac
fi
TARGET_HOME="${TARGET_HOME:-$HOME}"
PICOCLAW_HOME="${PICOCLAW_HOME:-$TARGET_HOME/.picoclaw}"
export PICOCLAW_HOME

usage() {
  cat <<USAGE
configure-picoclaw.sh — install + configure Picoclaw for Hosaka

Usage:
  scripts/configure-picoclaw.sh [--onboard|--no-onboard] [--model MODEL] [--api-base URL]

Options:
  --onboard       run interactive 'picoclaw onboard' after install/config if TTY is available
  --no-onboard    skip interactive onboarding; use non-interactive model setup only
  --model MODEL   model alias to register with Picoclaw (default: qwen2.5)
  --api-base URL  OpenAI-compatible API base (default: http://100.78.174.79:11434/v1)

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
  local py="${PYTHON:-python}"
  if [[ -x "$REPO_ROOT/../.venv/bin/python" ]]; then
    py="$REPO_ROOT/../.venv/bin/python"
  elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    py="$REPO_ROOT/.venv/bin/python"
  fi
  note "bootstrapping Hosaka runtime into ~/.picoclaw/workspace"
  "$py" "$REPO_ROOT/scripts/bootstrap_picoclaw_runtime.py" --home "$TARGET_HOME"
  ok "runtime ready"
}

read_openai_key() {
  # Prints the key to stdout for command substitution only. Callers must not log it.
  python - "$REPO_ROOT" "$TARGET_HOME" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

repo = Path(sys.argv[1])
target_home = Path(sys.argv[2]).expanduser()

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
  target_home / ".hosaka" / "llm.json",
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

for env_path in (repo / ".env", target_home / ".hosaka" / ".env", Path.home() / ".hosaka" / ".env"):
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
  "$PICOCLAW_BIN" status 2>&1 || true
}

has_openai_key_in_picoclaw() {
  picoclaw_status | grep -Eiq 'OpenAI API:[[:space:]]*(set|✓)'
}

has_picoclaw_model() {
  picoclaw_status | grep -Eiq '^Model:[[:space:]]*[^[:space:]]+'
}

configure_model_from_key() {
  local key="$1"
  if [[ -n "$key" && "$key" != "ollama" ]]; then
    note "importing compatible API key into Hosaka secrets (key hidden)"
    save_key_into_hosaka_secrets "$key" || true
    # Picoclaw v2: write the actual credential into ~/.picoclaw/.security.yml
    # rather than letting `picoclaw model` stash it into config.json.
    write_picoclaw_security_key "$MODEL" "$key" || true
  fi

  set +x
  set +e
  HOME="$TARGET_HOME" PICOCLAW_HOME="$PICOCLAW_HOME" \
    "$PICOCLAW_BIN" model "$MODEL" >/tmp/hosaka-picoclaw-model-add.log 2>&1
  local rc=$?
  set -e
  if (( rc != 0 )); then
    warn "picoclaw model select failed; last output:"
    sed -n '1,80p' /tmp/hosaka-picoclaw-model-add.log
    return "$rc"
  fi
  ok "Picoclaw model '$MODEL' configured"
}

# Write the provider credential into ~/.picoclaw/.security.yml — the v2
# overlay file. config.json keeps structure/routing only; this file keeps
# secrets and is chmod 0600. Preserves entries for other models so OpenAI
# and Ollama can coexist.
write_picoclaw_security_key() {
  local model_name="$1"
  local key="$2"
  [[ -n "$model_name" && -n "$key" ]] || return 0
  local py=""
  for candidate in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/.hosakavenv/bin/python" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      py="$candidate"
      break
    fi
  done
  [[ -n "$py" ]] || { warn "no python found; cannot write .security.yml"; return 0; }
  note "writing Picoclaw v2 security overlay (~/.picoclaw/.security.yml) — key hidden"
  HOME="$TARGET_HOME" "$py" - "$TARGET_HOME" "$model_name" "$key" <<'PY'
import os, sys
from pathlib import Path

home = Path(sys.argv[1]).expanduser()
model_name = sys.argv[2]
key = sys.argv[3]
path = home / ".picoclaw" / ".security.yml"
path.parent.mkdir(parents=True, exist_ok=True)

data = {}
if path.exists():
    try:
        import yaml  # type: ignore
        with path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}

ml = data.get("model_list")
if not isinstance(ml, dict):
    ml = {}
entry = ml.get(model_name) if isinstance(ml.get(model_name), dict) else {}
keys = entry.get("api_keys") if isinstance(entry.get("api_keys"), list) else []
keys = [k for k in keys if isinstance(k, str) and k and k != key]
keys.insert(0, key)
entry["api_keys"] = keys
ml[model_name] = entry
data["model_list"] = ml

try:
    import yaml  # type: ignore
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
except Exception:
    lines = ["model_list:"]
    for name, ent in (data.get("model_list") or {}).items():
        lines.append(f"  {name}:")
        ks = (ent or {}).get("api_keys") or []
        if ks:
            lines.append("    api_keys:")
            for k in ks:
                lines.append(f"      - {k}")
    text = "\n".join(lines) + "\n"

path.write_text(text, encoding="utf-8")
try:
    os.chmod(path, 0o600)
except Exception:
    pass
PY
}

# Mirror the same key into the Hosaka-native secrets store so the voice
# daemon and webserver can resolve it without poking at picoclaw internals.
# Failure here is non-fatal — picoclaw still has the key as a fallback.
save_key_into_hosaka_secrets() {
  local key="$1"
  [[ -n "$key" ]] || return 0

  local py=""
  for candidate in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/.hosakavenv/bin/python" python; do
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
  if ! HOME="$TARGET_HOME" \
       HOSAKA_SECRETS_PATH="$TARGET_HOME/.hosaka/secrets.json" \
       PYTHONPATH="$extra_path${PYTHONPATH:+:$PYTHONPATH}" \
       "$py" -m hosaka.secrets set OPENAI_API_KEY "$key" --no-mirror \
       >/tmp/hosaka-secrets-import.log 2>&1; then
    warn "could not write Hosaka secrets store; see /tmp/hosaka-secrets-import.log"
    return 0
  fi
  if [[ "$(id -u)" == "0" && -d "$TARGET_HOME/.hosaka" ]]; then
    owner="$(stat -c '%U:%G' "$TARGET_HOME" 2>/dev/null || true)"
    [[ -n "$owner" ]] && chown -R "$owner" "$TARGET_HOME/.hosaka" 2>/dev/null || true
  fi

  if command -v sudo >/dev/null 2>&1; then
    note "mirroring secrets to /etc/hosaka/env (requires sudo)"
    if ! sudo -E env "HOME=$TARGET_HOME" \
         "HOSAKA_SECRETS_PATH=$TARGET_HOME/.hosaka/secrets.json" \
         "PYTHONPATH=$extra_path${PYTHONPATH:+:$PYTHONPATH}" \
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
  python - "$REPO_ROOT" "$TARGET_HOME" "$MODEL" "$API_BASE" "$MODEL_TARGET" <<'PY'
import json
import os
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
home = Path(sys.argv[2]).expanduser().resolve()
model = sys.argv[3]
api_base = sys.argv[4]
model_target = sys.argv[5]
path = home / ".picoclaw" / "config.json"
if not path.exists():
    raise SystemExit(0)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

# ── Picoclaw v2 hard rule: config.json must contain NO secrets. ──
# Any legacy api_key / api_keys field at the model_list level makes
# `picoclaw status` reject the whole config with:
#   "config.json contains unknown field(s): model_list[0].api_key"
# Strip them silently so this migration is idempotent. Real secrets
# live in ~/.picoclaw/.security.yml (an overlay, not a replacement).
_existing_list = data.get("model_list")
if isinstance(_existing_list, list):
    for _entry in _existing_list:
        if isinstance(_entry, dict):
            _entry.pop("api_key", None)
            _entry.pop("api_keys", None)

local_first = os.environ.get("HOSAKA_LOCAL_FIRST", "1").strip().lower() in ("1", "true", "yes", "on")
workspace = str(home / ".picoclaw" / "workspace")
defaults = data.setdefault("agents", {}).setdefault("defaults", {})
defaults["workspace"] = workspace
defaults["restrict_to_workspace"] = False
defaults["allow_read_outside_workspace"] = True
defaults.setdefault("model_name", model)
defaults["max_tokens"] = 4096
defaults.setdefault("max_tool_iterations", 50)

model_list = data.setdefault("model_list", [])
if isinstance(model_list, list):
    if not any(
        isinstance(entry, dict) and entry.get("model_name") == model
        for entry in model_list
    ):
        model_list.insert(0, {
            "model_name": model,
            "model": f"ollama/{model_target}",
            "api_base": api_base,
        })
    if local_first and defaults.get("model_name") != model:
        current = str(defaults.get("model_name") or "")
        target_entry = next(
            (e for e in model_list if isinstance(e, dict) and e.get("model_name") == current),
            None,
        )
        target_model = str((target_entry or {}).get("model") or "")
        if not target_model.startswith("ollama/"):
            defaults["model_name"] = model

    # Per deployment_updates.yaml.known_good_runtime_files.picoclaw_config:
    # config.json should always carry a gpt-4.1-mini OpenAI entry so the
    # operator can switch defaults without re-editing structure. Credential-free.
    if not any(
        isinstance(entry, dict) and entry.get("model_name") == "gpt-4.1-mini"
        for entry in model_list
    ):
        model_list.append({
            "model_name": "gpt-4.1-mini",
            "model": "openai/gpt-4.1-mini",
            "api_base": "https://api.openai.com/v1",
        })

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
  if [[ "$RUN_ONBOARD" == "auto" && -f "$PICOCLAW_HOME/config.json" ]]; then
    return 0
  fi
  if [[ -t 0 && -t 1 ]]; then
    note "starting interactive Picoclaw onboarding"
    HOME="$TARGET_HOME" PICOCLAW_HOME="$PICOCLAW_HOME" "$PICOCLAW_BIN" onboard
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

  local local_first="no"
  if [[ "$API_BASE" != https://api.openai.com* ]]; then
    local_first="yes"
  fi

  if [[ "$local_first" == "yes" ]]; then
    note "local-first mode: pointing Picoclaw at $API_BASE ($MODEL -> ollama/$MODEL_TARGET)"
    harden_picoclaw_config
    configure_model_from_key "ollama"
  elif has_openai_key_in_picoclaw; then
    ok "Picoclaw config exists; checking model setup is complete enough to run"
    harden_picoclaw_config
  else
    local key=""
    key="$(read_openai_key || true)"
    if [[ -n "$key" ]]; then
      if has_picoclaw_model; then
        ok "Hosaka compatible API key is available and Picoclaw already has a default model"
        save_key_into_hosaka_secrets "$key" || true
      else
        configure_model_from_key "$key"
      fi
    else
      warn "no OpenAI key found in env, Hosaka llm.json, or local .env"
      echo "  In Hosaka, use /settings or the inline key prompt first."
      echo "  Then rerun: hosaka configure picoclaw"
    fi
    harden_picoclaw_config
  fi

  # If this script was launched from the root-owned webserver shell, Picoclaw
  # can rewrite /home/operator/.picoclaw/config.json as root. Hand ownership
  # back to the account that owns the target home so the operator service and
  # SSH terminal can read it.
  if [[ "$(id -u)" == "0" && -d "$TARGET_HOME/.picoclaw" ]]; then
    owner="$(stat -c '%U:%G' "$TARGET_HOME" 2>/dev/null || true)"
    if [[ -n "$owner" ]]; then
      chown -R "$owner" "$TARGET_HOME/.picoclaw" 2>/dev/null || true
    fi
  fi

  maybe_onboard

  echo
  note "final status"
  picoclaw_status | sed -n '1,120p'
  echo
  echo "next: restart local dev so the backend inherits PATH/config: hosaka dev -fresh"
}

main "$@"
