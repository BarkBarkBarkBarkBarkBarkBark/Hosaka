#!/usr/bin/env sh
# shellcheck disable=SC2039,SC3043
#
# hosaka — one-line installer for mac + linux
#
#   curl -fsSL https://install.hosaka.xyz | sh
#
# What this does:
#   1. Detects OS + arch.
#   2. Makes sure Docker is present (prints the right install hint if not).
#   3. Drops the `hosaka` launcher into /usr/local/bin (or $HOSAKA_PREFIX/bin).
#   4. Pulls the latest container image in the background.
#   5. Prints next steps.
#
# Env overrides:
#   HOSAKA_PREFIX     install prefix (default: /usr/local)
#   HOSAKA_VERSION    launcher version to install (default: latest)
#   HOSAKA_IMAGE      container image (default: ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest)
#   HOSAKA_NO_PULL    set to 1 to skip the background docker pull
#
# Signal steady. No wrong way.

set -eu

# ── style ────────────────────────────────────────────────────────────────────
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    C_DIM="$(tput dim)"; C_CYAN="$(tput setaf 6)"; C_GREEN="$(tput setaf 2)"
    C_AMBER="$(tput setaf 3)"; C_RED="$(tput setaf 1)"; C_RESET="$(tput sgr0)"
else
    C_DIM=""; C_CYAN=""; C_GREEN=""; C_AMBER=""; C_RED=""; C_RESET=""
fi
note() { printf '  %s›%s %s\n' "$C_CYAN" "$C_RESET" "$*"; }
ok()   { printf '  %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '  %s!%s %s\n' "$C_AMBER" "$C_RESET" "$*"; }
die()  { printf '  %s✗%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

# ── preflight ────────────────────────────────────────────────────────────────
HOSAKA_PREFIX="${HOSAKA_PREFIX:-/usr/local}"
HOSAKA_VERSION="${HOSAKA_VERSION:-latest}"
HOSAKA_IMAGE="${HOSAKA_IMAGE:-ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest}"
LAUNCHER_URL="https://install.hosaka.xyz/bin/hosaka"
[ "$HOSAKA_VERSION" != "latest" ] && LAUNCHER_URL="https://install.hosaka.xyz/bin/hosaka@${HOSAKA_VERSION}"

UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
UNAME_M="$(uname -m 2>/dev/null || echo unknown)"
case "$UNAME_S" in
    Darwin)  OS="mac" ;;
    Linux)   OS="linux" ;;
    MINGW*|MSYS*|CYGWIN*) die "windows: use the PowerShell installer — iwr https://install.hosaka.xyz/windows | iex" ;;
    *)       die "unsupported OS: $UNAME_S" ;;
esac
case "$UNAME_M" in
    x86_64|amd64)   ARCH="amd64" ;;
    arm64|aarch64)  ARCH="arm64" ;;
    *)              die "unsupported arch: $UNAME_M" ;;
esac

printf '\n'
printf '  %shosaka%s client installer %s(%s/%s)%s\n' "$C_CYAN" "$C_RESET" "$C_DIM" "$OS" "$ARCH" "$C_RESET"
printf '\n'

# ── docker check ─────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    warn "docker not found — hosaka needs it as the runtime"
    case "$OS" in
        mac)
            printf '    install with:  %sbrew install --cask docker%s\n' "$C_CYAN" "$C_RESET"
            printf '           or:    https://www.docker.com/products/docker-desktop\n'
            ;;
        linux)
            printf '    install with:  %scurl -fsSL https://get.docker.com | sh%s\n' "$C_CYAN" "$C_RESET"
            ;;
    esac
    printf '\n    re-run this installer after docker is on PATH.\n\n'
    exit 1
fi
ok "docker present: $(docker --version 2>/dev/null | head -1)"

if ! docker info >/dev/null 2>&1; then
    warn "docker is installed but the daemon isn't running"
    case "$OS" in
        mac)   printf '    start Docker Desktop, then re-run this installer.\n\n' ;;
        linux) printf '    try: %ssudo systemctl start docker%s\n\n' "$C_CYAN" "$C_RESET" ;;
    esac
    exit 1
fi

# ── tailscale check (optional, informational) ────────────────────────────────
if command -v tailscale >/dev/null 2>&1; then
    ok "tailscale present — you can link to a remote hosaka with: hosaka link <hostname>"
else
    note "tailscale not detected (optional) — install from https://tailscale.com/download to link clients"
fi

# ── install launcher ─────────────────────────────────────────────────────────
BIN_DIR="$HOSAKA_PREFIX/bin"
TARGET="$BIN_DIR/hosaka"
TMP="$(mktemp -t hosaka.XXXXXX)"

note "fetching launcher from $LAUNCHER_URL"
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$LAUNCHER_URL" -o "$TMP" || die "download failed"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP" "$LAUNCHER_URL" || die "download failed"
else
    die "need curl or wget"
fi
chmod +x "$TMP"

SUDO=""
if [ ! -w "$BIN_DIR" ] && [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
        note "writing to $TARGET (needs sudo)"
    else
        die "cannot write $TARGET and no sudo available — set HOSAKA_PREFIX=\$HOME/.local"
    fi
fi

$SUDO mkdir -p "$BIN_DIR"
$SUDO mv "$TMP" "$TARGET"
$SUDO chmod +x "$TARGET"
ok "installed $TARGET"

# ── background pull (non-blocking) ───────────────────────────────────────────
if [ "${HOSAKA_NO_PULL:-0}" != "1" ]; then
    note "warming up container image in the background ($HOSAKA_IMAGE)"
    ( docker pull --quiet "$HOSAKA_IMAGE" >/dev/null 2>&1 & ) >/dev/null 2>&1
fi

# ── path warning ─────────────────────────────────────────────────────────────
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not on your PATH — add it to your shell rc:"
       printf '        %sexport PATH="%s:$PATH"%s\n' "$C_CYAN" "$BIN_DIR" "$C_RESET" ;;
esac

# ── next steps ───────────────────────────────────────────────────────────────
cat <<EOF

  ${C_GREEN}hosaka is ready.${C_RESET}

    ${C_CYAN}hosaka up${C_RESET}          start the local node (web UI on http://127.0.0.1:8421)
    ${C_CYAN}hosaka tui${C_RESET}         drop into the console TUI
    ${C_CYAN}hosaka link HOST${C_RESET}   wire this client to a remote hosaka over your tailnet
    ${C_CYAN}hosaka help${C_RESET}        see everything

  ${C_DIM}signal steady. no wrong way.${C_RESET}

EOF
