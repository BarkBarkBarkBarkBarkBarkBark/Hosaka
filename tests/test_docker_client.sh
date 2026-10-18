#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
mkdir -p "$temp/bin" "$temp/project with spaces"
cat >"$temp/bin/docker" <<'SH'
#!/bin/bash
printf 'CALL\n' >>"$TEST_LOG"
printf '%s\n' "$@" >>"$TEST_LOG"
if [[ "$1" == inspect ]]; then echo "${TEST_RUNNING:-false}"; fi
SH
chmod +x "$temp/bin/docker"
export TEST_LOG="$temp/log" HOSAKA_HOME="$temp/home with spaces"
export PATH="$temp/bin:/usr/bin:/bin"
cli() { bash "$root/install/bin/hosaka" "$@"; }
cli workspace "$temp/project with spaces"
test -d "$HOSAKA_HOME/runtime/extensions"
test -d "$HOSAKA_HOME/runtime/extension-data"
shared="$(cd "$temp/project with spaces" && pwd -P)"
cli tui </dev/null
grep -qF "src=$shared,dst=/workspace,readonly" "$TEST_LOG"
grep -qFx tui "$TEST_LOG"
grep -qFx -- --initialize-only "$TEST_LOG"
grep -qFx /root/.picoclaw < <(sed 's/.*dst=//' "$TEST_LOG")
if grep -qFx -- --boot "$TEST_LOG"; then exit 1; fi
cli workspace "$temp/project with spaces" --read-write
: >"$TEST_LOG"
cli secrets set EXAMPLE_KEY </dev/null
grep -qFx -- --no-mirror "$TEST_LOG"
if grep -q 'readonly' "$TEST_LOG"; then exit 1; fi
export TEST_RUNNING=true
: >"$TEST_LOG"
cli tui </dev/null
grep -qFx exec "$TEST_LOG"
grep -qFx /workspace "$TEST_LOG"
if cli workspace clear; then echo "Changed mount on a running node" >&2; exit 1; fi
unset TEST_RUNNING
cli workspace clear
test ! -f "$HOSAKA_HOME/workspace.conf"
: >"$TEST_LOG"
cli configure llm --provider anthropic --model claude-example </dev/null
grep -qFx hosaka.llm_setup "$TEST_LOG"
grep -qFx claude-example "$TEST_LOG"
: >"$TEST_LOG"
cli paths --json </dev/null
grep -qFx hosaka.paths "$TEST_LOG"
: >"$TEST_LOG"
cli extensions list --json </dev/null
grep -qFx hosaka.extensions "$TEST_LOG"
: >"$TEST_LOG"
cli migrate --dry-run --json </dev/null
grep -qFx hosaka.migration "$TEST_LOG"
grep -qFx -- --read-only "$TEST_LOG"
grep -qFx -- --pull=never "$TEST_LOG"
grep -qFx none "$TEST_LOG"
grep -qFx "type=bind,src=$HOSAKA_HOME/runtime,dst=/root/.hosaka,readonly" "$TEST_LOG"
if grep -qFx -- --initialize-only "$TEST_LOG"; then exit 1; fi
export TEST_RUNNING=true
: >"$TEST_LOG"
cli migrate --dry-run --json </dev/null
grep -qFx exec "$TEST_LOG"
if grep -qFx -- --initialize-only "$TEST_LOG"; then exit 1; fi
unset TEST_RUNNING
original_home="$HOSAKA_HOME"
export HOSAKA_HOME="$temp/absent-runtime"
cli migrate --dry-run --json </dev/null
test ! -e "$HOSAKA_HOME"
export HOSAKA_HOME="$original_home"
echo "Docker client regression tests passed"
