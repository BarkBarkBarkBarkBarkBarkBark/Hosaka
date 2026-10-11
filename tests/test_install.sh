#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
mkdir -p "$temp/bin" "$temp/tmp"

cat >"$temp/bin/docker" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >>"$HOSAKA_TEST_LOG"
case "$1" in
  info) exit "${HOSAKA_TEST_DAEMON_EXIT:-0}" ;;
  pull) exit "${HOSAKA_TEST_PULL_EXIT:-0}" ;;
  --version) echo "Docker test" ;;
esac
SH
cat >"$temp/bin/curl" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >>"$HOSAKA_TEST_LOG"
if [ "${HOSAKA_TEST_DOWNLOAD_EXIT:-0}" != 0 ]; then exit 22; fi
if [ "${HOSAKA_TEST_BAD_DOWNLOAD:-0}" = 1 ]; then
  printf '<html>not a launcher</html>\n' >"$4"
elif [ "${HOSAKA_TEST_BAD_SYNTAX:-0}" = 1 ]; then
  printf '#!/bin/bash\n# thin desktop client\nif\n' >"$4"
else
  cp "$HOSAKA_TEST_SOURCE" "$4"
fi
SH
cat >"$temp/bin/uname" <<'SH'
#!/bin/sh
case "$1" in
  -s) echo Linux ;;
  -m) echo x86_64 ;;
esac
SH
chmod +x "$temp/bin/"*
export PATH="$temp/bin:/usr/bin:/bin"
export TMPDIR="$temp/tmp"
export HOSAKA_TEST_SOURCE="$root/install/bin/hosaka"
export HOSAKA_TEST_LOG="$temp/log"
export HOSAKA_INSTALL_BASE="https://example.invalid/test"
export HOSAKA_PREFIX="$temp/prefix"
unset HOSAKA_VERSION HOSAKA_IMAGE HOSAKA_NO_PULL

run() {
  : >"$HOSAKA_TEST_LOG"
  if sh "$root/install/install.sh" </dev/null >"$temp/output" 2>&1; then
    result=0
  else
    result=$?
  fi
  if [[ "$result" != "$1" ]]; then
    cat "$temp/output"
    echo "Expected exit $1, got $result" >&2
    exit 1
  fi
  [[ -z "$(ls -A "$TMPDIR")" ]]
}

run 0
test -x "$HOSAKA_PREFIX/bin/hosaka"
cmp "$HOSAKA_TEST_SOURCE" "$HOSAKA_PREFIX/bin/hosaka"
grep -q 'https://example.invalid/test/bin/hosaka' "$HOSAKA_TEST_LOG"
grep -q '^pull ghcr.io/' "$HOSAKA_TEST_LOG"
grep -q 'not on your PATH' "$temp/output"
cp "$HOSAKA_PREFIX/bin/hosaka" "$temp/original"

export HOSAKA_TEST_PULL_EXIT=1
run 1
cmp "$temp/original" "$HOSAKA_PREFIX/bin/hosaka"
grep -q 'image download failed' "$temp/output"
unset HOSAKA_TEST_PULL_EXIT

export HOSAKA_TEST_DOWNLOAD_EXIT=1
run 1
cmp "$temp/original" "$HOSAKA_PREFIX/bin/hosaka"
unset HOSAKA_TEST_DOWNLOAD_EXIT

export HOSAKA_TEST_BAD_DOWNLOAD=1
run 1
cmp "$temp/original" "$HOSAKA_PREFIX/bin/hosaka"
unset HOSAKA_TEST_BAD_DOWNLOAD

export HOSAKA_TEST_BAD_SYNTAX=1
run 1
cmp "$temp/original" "$HOSAKA_PREFIX/bin/hosaka"
unset HOSAKA_TEST_BAD_SYNTAX

export HOSAKA_TEST_DAEMON_EXIT=1
run 1
if grep -q '^pull ' "$HOSAKA_TEST_LOG"; then exit 1; fi
unset HOSAKA_TEST_DAEMON_EXIT

export HOSAKA_NO_PULL=1
run 0
if grep -q '^pull ' "$HOSAKA_TEST_LOG"; then exit 1; fi
unset HOSAKA_NO_PULL

printf '#!/bin/sh\n# Native Hosaka\n' >"$temp/bin/hosaka"
chmod +x "$temp/bin/hosaka"
run 1
grep -q 'existing non-Docker Hosaka' "$temp/output"
cmp "$temp/original" "$HOSAKA_PREFIX/bin/hosaka"
rm "$temp/bin/hosaka"

printf '#!/bin/sh\n# Native Hosaka\n' >"$HOSAKA_PREFIX/bin/hosaka"
run 1
grep -q 'refusing to overwrite' "$temp/output"
grep -q 'Native Hosaka' "$HOSAKA_PREFIX/bin/hosaka"

echo "Unix installer regression tests passed"
