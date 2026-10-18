#!/usr/bin/env bash
# install_hosaka_lean.sh — apply all the "lean & mode" bits onto an
# already-installed Hosaka Pi. Idempotent. Run this once after pulling
# new commits:
#
#   sudo $REPO/scripts/install_hosaka_lean.sh
#
# What it does:
#   1. Installs CLIs:        hosaka, hosaka-device-dashboard, hosakactl
#   2. Installs systemd:     hosaka-webserver.service, picoclaw-gateway.service,
#                            hosaka-device-dashboard.service
#   3. SSH OOM drop-in:      /etc/systemd/system/ssh.service.d/oom-protection.conf
#                            (sshd is the LAST thing the OOM killer touches)
#   4. Enables persistent journal so we keep crash evidence across reboots
#   5. Masks ALSA on this headless Pi (no sound card)
#   6. Fixes /var/lib/hosaka ownership so `hosaka mode` works as operator
#   7. Refreshes ~operator/.config/openbox/autostart and ~/.profile
#
# Doesn't touch: Node, Chromium, the Python venv, or the SPA build.
# Use install_hosaka.sh for those, or `hosaka deploy` for the SPA.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUDO="sudo"
[[ "$(id -u)" == "0" ]] && SUDO=""
TARGET_USER="${HOSAKA_OPERATOR:-${SUDO_USER:-$(id -un)}}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ "$TARGET_HOME" == /* ]] || { echo "Cannot find home for operator $TARGET_USER." >&2; exit 1; }
TARGET_GROUP="$(id -gn "$TARGET_USER")"
DISPLAY_PREFERENCE="${XDG_CONFIG_HOME:-$TARGET_HOME/.config}/hosaka/display-mode"
if [[ -z "${HOSAKA_DISPLAY_MODE:-}" ]]; then
  if [[ -f "$DISPLAY_PREFERENCE" ]]; then
    HOSAKA_DISPLAY_MODE="$(cat "$DISPLAY_PREFERENCE")"
  else
    HOSAKA_DISPLAY_MODE=gui
  fi
fi
[[ "$HOSAKA_DISPLAY_MODE" =~ ^(tui|gui)$ ]] || { echo "HOSAKA_DISPLAY_MODE must be tui or gui" >&2; exit 1; }

say() { printf '[hosaka-lean] %s\n' "$*"; }

# ── 1. CLIs ───────────────────────────────────────────────────────────────────
say "installing CLIs to /usr/local/bin"
$SUDO install -m 0755 "$REPO_ROOT/scripts/hosaka"                  /usr/local/bin/hosaka
$SUDO install -m 0755 "$REPO_ROOT/scripts/hosaka-device-dashboard" /usr/local/bin/hosaka-device-dashboard
$SUDO install -m 0755 "$REPO_ROOT/scripts/hosakactl"               /usr/local/bin/hosakactl
$SUDO install -m 0755 "$REPO_ROOT/scripts/kiosk-electron.sh"       /usr/local/bin/hosaka-kiosk-electron
$SUDO install -m 0755 "$REPO_ROOT/scripts/kiosk-chromium.sh"       /usr/local/bin/hosaka-kiosk-chromium

# ── 1b. API token for /api/v1/* (read by api_v1.py and hosakactl) ─────────────
# /etc/hosaka/api-token is the bearer credential for LAN clients. Loopback
# (the kiosk SPA, the TTY dashboard) bypasses it. The Pi reads it as root via
# the webserver, but we want the operator to be able to `cat` it without sudo
# so they can paste it into hosakactl on their laptop.
TOKEN_PATH=/etc/hosaka/api-token
if [[ ! -s "$TOKEN_PATH" ]]; then
  say "generating $TOKEN_PATH (32 bytes hex)"
  $SUDO install -d -m 0755 /etc/hosaka
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32 | $SUDO tee "$TOKEN_PATH" >/dev/null
  else
    head -c 32 /dev/urandom | xxd -p -c 32 | $SUDO tee "$TOKEN_PATH" >/dev/null
  fi
  $SUDO chown root:"$TARGET_USER" "$TOKEN_PATH"
  $SUDO chmod 0640 "$TOKEN_PATH"
else
  say "$TOKEN_PATH already exists — leaving in place"
fi

# ── 2. systemd units ──────────────────────────────────────────────────────────
say "installing systemd units"
for unit in \
    hosaka-device-dashboard.service \
    hosaka-webserver.service \
    hosaka-kiosk.service \
    picoclaw-gateway.service \
; do
  if [[ -f "$REPO_ROOT/systemd/$unit" ]]; then
    $SUDO install -m 0644 "$REPO_ROOT/systemd/$unit" "/etc/systemd/system/$unit"
  fi
done

# Patch hosaka-kiosk.service to the actual operator user (install-time rewrite
# so the same unit file works on laptops, dev Pis, and appliance Pis).
if [[ -f /etc/systemd/system/hosaka-kiosk.service ]]; then
  $SUDO sed -i \
    -e "s/^User=.*/User=${TARGET_USER}/" \
    -e "s/^Group=.*/Group=${TARGET_GROUP}/" \
    -e "s|^Environment=XAUTHORITY=.*|Environment=XAUTHORITY=${TARGET_HOME}/.Xauthority|" \
    /etc/systemd/system/hosaka-kiosk.service
fi

# ── 2b. stage the electron kiosk into /opt ────────────────────────────────────
# kiosk/ needs to live alongside /opt/hosaka-field-terminal/hosaka/web/ui so
# the Electron main process can find the built SPA via its ../hosaka/web/ui
# path (when HOSAKA_KIOSK_NO_LOOPBACK=1 is set for demos). At boot, though,
# we prefer http://127.0.0.1:8421 so /api is same-origin — see main.js.
KIOSK_SRC="$REPO_ROOT/kiosk"
KIOSK_DEST="/opt/hosaka-field-terminal/kiosk"
if [[ -d "$KIOSK_SRC" ]]; then
  say "staging electron kiosk into $KIOSK_DEST"
  $SUDO install -d -o "$TARGET_USER" -g "$TARGET_USER" -m 0755 "$KIOSK_DEST"
  # Exclude node_modules from the rsync; we'll rebuild it in-place so the
  # native electron binary matches this host's arch (arm64 on a Pi, not
  # darwin-arm64 from whoever committed it last).
  $SUDO rsync -a --delete \
    --exclude node_modules --exclude out --exclude dist \
    "$KIOSK_SRC/" "$KIOSK_DEST/"
  $SUDO chown -R "$TARGET_USER:$TARGET_USER" "$KIOSK_DEST"
  if [[ "$HOSAKA_DISPLAY_MODE" == "tui" ]]; then
    say "TUI boot selected — not installing Electron"
  elif command -v npm >/dev/null 2>&1; then
    say "running npm install in $KIOSK_DEST (pulls native electron for $(uname -m))"
    # Run as the operator user so the resulting node_modules is owned by
    # them — otherwise `hosaka deploy` can't blow it away later.
    if [[ "$(id -un)" == "$TARGET_USER" ]]; then
      ( cd "$KIOSK_DEST" && npm install --no-fund --no-audit --loglevel error )
    else
      # If we're already root (bare install), sudo is a no-op var; use `runuser`
      # so we drop privs unconditionally and don't end up running postinstall
      # scripts as root (which chown the cache to root too).
      runuser -u "$TARGET_USER" -- bash -lc \
        "cd '$KIOSK_DEST' && npm install --no-fund --no-audit --loglevel error"
    fi
  else
    say "WARNING: npm not on PATH — skipping kiosk npm install"
    say "         install Node 20 (curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -) and rerun."
  fi
else
  say "no kiosk/ in repo — skipping electron kiosk staging"
fi

# ── 3. SSH OOM protection drop-in ─────────────────────────────────────────────
# sshd is the LAST process the OOM killer should touch. Without this drop-in
# we lose the SSH session every time npm build starts swapping.
say "installing SSH oom-protection drop-in"
$SUDO install -d -m 0755 /etc/systemd/system/ssh.service.d
$SUDO install -m 0644 \
    "$REPO_ROOT/systemd/dropins/ssh.service.d/oom-protection.conf" \
    /etc/systemd/system/ssh.service.d/oom-protection.conf

# ── 4. persistent journal ─────────────────────────────────────────────────────
# Without this the journal lives on tmpfs and disappears on reboot — meaning
# every crash investigation starts blind. Cap the on-disk size at 64 MiB.
say "enabling persistent journal (64 MiB cap)"
$SUDO install -d -m 02755 /var/log/journal
$SUDO install -d -m 0755 /etc/systemd/journald.conf.d
$SUDO install -m 0644 "$REPO_ROOT/systemd/journald-hosaka.conf" \
    /etc/systemd/journald.conf.d/hosaka.conf
$SUDO systemd-tmpfiles --create --prefix /var/log/journal 2>/dev/null || true

# ── 5. mask ALSA on this headless Pi ──────────────────────────────────────────
say "masking ALSA units (no sound card on this Pi)"
for unit in alsa-restore.service alsa-state.service; do
  $SUDO systemctl mask "$unit" 2>/dev/null || true
done

# ── 6. /var/lib/hosaka ownership ──────────────────────────────────────────────
say "ensuring /var/lib/hosaka is operator-writable"
$SUDO install -d -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" /var/lib/hosaka
if [[ -f /var/lib/hosaka/mode ]]; then
  $SUDO chown "$TARGET_USER:$TARGET_USER" /var/lib/hosaka/mode || true
fi
$SUDO /opt/hosaka-field-terminal/.venv/bin/python \
  "$REPO_ROOT/scripts/bootstrap_picoclaw_runtime.py" --appliance-user "$TARGET_USER"

say "staging extension authoring support and validating preserved packages"
$SUDO rsync -a --delete "$REPO_ROOT/hosaka/extensions/" /opt/hosaka-field-terminal/hosaka/extensions/
$SUDO rsync -a --delete "$REPO_ROOT/examples/" /opt/hosaka-field-terminal/examples/
$SUDO /opt/hosaka-field-terminal/.venv/bin/python -m pip install -r "$REPO_ROOT/requirements-hosaka.txt"
$SUDO runuser -u "$TARGET_USER" -- env \
  HOSAKA_OPERATOR="$TARGET_USER" HOSAKA_DATA_DIR="${HOSAKA_DATA_DIR:-$TARGET_HOME/.hosaka}" \
  PYTHONPATH=/opt/hosaka-field-terminal \
  /opt/hosaka-field-terminal/.venv/bin/python -m hosaka.extensions init

# ── 7. operator-side config files ─────────────────────────────────────────────
$SUDO install -d -m 0755 -o "$TARGET_USER" -g "$TARGET_GROUP" "$(dirname "$DISPLAY_PREFERENCE")"
printf '%s\n' "$HOSAKA_DISPLAY_MODE" | $SUDO tee "$DISPLAY_PREFERENCE" >/dev/null
$SUDO chown "$TARGET_USER:$TARGET_GROUP" "$DISPLAY_PREFERENCE"
if [[ -f "$TARGET_HOME/.xinitrc" && ! -e "$TARGET_HOME/.xinitrc.pre-hosaka" ]]; then
  $SUDO cp -p "$TARGET_HOME/.xinitrc" "$TARGET_HOME/.xinitrc.pre-hosaka"
fi
$SUDO install -D -m 0755 -o "$TARGET_USER" -g "$TARGET_GROUP" \
  "$REPO_ROOT/dotfiles/xinitrc" "$TARGET_HOME/.xinitrc"
$SUDO install -D -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" \
  "$REPO_ROOT/scripts/hosaka-lxqt-kiosk.sh" /usr/local/bin/hosaka-lxqt-kiosk
for name in hosaka-ui-session hosaka-ui-switch hosaka-tui-term; do
  $SUDO install -D -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" \
    "$REPO_ROOT/scripts/$name" "$TARGET_HOME/bin/$name"
done
$SUDO install -D -m 0644 -o "$TARGET_USER" -g "$TARGET_USER" \
  "$REPO_ROOT/dotfiles/autostart/hosaka-tui.desktop" "$TARGET_HOME/.config/autostart/hosaka-tui.desktop"
# Only install the shared supervisor entry point, not an older competing loop.
SRC_AUTOSTART="$REPO_ROOT/dotfiles/openbox/autostart"
SRC_PROFILE="$REPO_ROOT/dotfiles/profile"
DST_AUTOSTART="$TARGET_HOME/.config/openbox/autostart"
DST_PROFILE="$TARGET_HOME/.profile"

# If the dotfiles aren't in the repo (older checkout) but the running system
# has a newer one, leave it alone. Otherwise sync.
if [[ -f "$SRC_AUTOSTART" ]] && grep -qF '/usr/local/bin/hosaka-lxqt-kiosk' "$SRC_AUTOSTART"; then
  $SUDO install -D -m 0755 -o "$TARGET_USER" -g "$TARGET_GROUP" "$SRC_AUTOSTART" "$DST_AUTOSTART"
  say "refreshed $DST_AUTOSTART"
fi
if [[ -f "$SRC_PROFILE" ]] && grep -q "tty1 boot dispatcher" "$SRC_PROFILE"; then
  install -m 0644 "$SRC_PROFILE" "$DST_PROFILE"
  say "refreshed $DST_PROFILE"
fi

# ── 8. sudoers whitelist for `hosaka mode` and the oom-guard ──────────────────
# Without this, `hosaka mode device` blocks on a sudo password prompt — which
# is exactly when you DON'T have time to type one. Visudo-validates first
# so a bad edit can't lock you out.
say "installing /etc/sudoers.d/hosaka (whitelisted NOPASSWD)"
TMP_SUDO="$(mktemp)"
cp "$REPO_ROOT/systemd/sudoers/hosaka" "$TMP_SUDO"
if $SUDO visudo -cf "$TMP_SUDO" >/dev/null; then
  $SUDO install -m 0440 -o root -g root "$TMP_SUDO" /etc/sudoers.d/hosaka
else
  say "WARNING: sudoers file failed visudo check, NOT installed"
fi
rm -f "$TMP_SUDO"

# ── 9. logrotate + log dir for snapshots ──────────────────────────────────────
say "installing /etc/logrotate.d/hosaka and /var/log/hosaka"
$SUDO install -d -m 0755 -o root -g adm /var/log/hosaka
$SUDO install -m 0644 "$REPO_ROOT/systemd/logrotate-hosaka" /etc/logrotate.d/hosaka

# ── 10. sysctl: stop using SD-card swap as a working surface ──────────────────
# Default vm.swappiness=60 is what causes the mmc_rescan deadlocks. 10 means
# "only swap when truly out of options".
say "applying sysctl tuning (swappiness=10)"
$SUDO install -m 0644 "$REPO_ROOT/systemd/sysctl-hosaka.conf" /etc/sysctl.d/60-hosaka.conf
$SUDO sysctl --system >/dev/null 2>&1 || true

# ── 11. systemd reload + enables ──────────────────────────────────────────────
say "reloading systemd"
$SUDO systemctl daemon-reload
$SUDO systemctl enable hosaka-webserver.service picoclaw-gateway.service 2>/dev/null || true
# Enable the kiosk only if we actually have a working electron on disk —
# otherwise systemd will restart-loop forever. The openbox autostart still
# provides a Chromium fallback in that case.
if [[ "$HOSAKA_DISPLAY_MODE" == "tui" ]]; then
  $SUDO systemctl disable hosaka-kiosk.service
  say "TUI boot selected — kiosk service disabled"
elif [[ -x "$KIOSK_DEST/node_modules/electron/dist/electron" ]]; then
  $SUDO systemctl enable hosaka-kiosk.service 2>/dev/null || true
  say "hosaka-kiosk.service enabled"
else
  say "electron not present in $KIOSK_DEST/node_modules/electron/dist — not enabling hosaka-kiosk.service"
  say "  re-run this script once npm install has completed successfully."
fi
$SUDO systemctl restart systemd-journald.service 2>/dev/null || true
$SUDO systemctl restart ssh.service 2>/dev/null || true
$SUDO systemctl restart hosaka-webserver.service 2>/dev/null || true
$SUDO systemctl restart picoclaw-gateway.service 2>/dev/null || true

say "done. try: hosaka status   |   journalctl -u hosaka-webserver -f"
say "          systemctl restart hosaka-kiosk   (to cycle the electron kiosk)"
