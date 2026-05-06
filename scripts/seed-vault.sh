#!/usr/bin/env bash
# Seed ~/Vault with a friendly markdown welcome page so Obsidian (or
# Apostrophe on aarch64) opens onto something instead of an empty dir.
#
# Convention: ~/Vault is the canonical writing surface for the operator.
# - Obsidian opens it as a vault.
# - Apostrophe can browse files inside it.
# - Future: agent /api/v1/vault/* endpoints will scope here.
#
# Usage:
#   bash scripts/seed-vault.sh                # seed ~/Vault
#   VAULT_DIR=/data/vault bash scripts/seed-vault.sh
#
# Idempotent: never overwrites existing files.

set -euo pipefail

DEST="${VAULT_DIR:-$HOME/Vault}"
mkdir -p "$DEST/daily" "$DEST/inbox" "$DEST/lore"

cyan()  { printf '\033[0;36m%s\033[0m' "$*"; }
green() { printf '\033[0;32m%s\033[0m' "$*"; }

write_if_missing() {
  local path="$1"
  local body="$2"
  if [[ -e "$path" ]]; then
    echo "  · $(green skip) ${path#$DEST/} — exists"
    return
  fi
  printf '%s\n' "$body" > "$path"
  echo "  · wrote $(green new) ${path#$DEST/}"
}

echo "$(cyan "[seed-vault]") destination: $DEST"

write_if_missing "$DEST/welcome.md" "# welcome to your vault

this folder is your writing surface. obsidian opens it as a vault on
x86_64 hosts; on the pi (aarch64) use **apostrophe** for the same job.

## conventions

- \`daily/\` — one file per day, named \`YYYY-MM-DD.md\`
- \`inbox/\` — quick captures, triage later
- \`lore/\` — long-form story material, hosaka-adjacent

agents may read this folder in a future release, scoped to a sandboxed
\`/api/v1/vault/*\` endpoint. nothing here is uploaded today.

## first steps

- press \`ctrl+n\` in obsidian to start a new note
- drag images into a note to embed them
- backlinks live in the right sidebar
"

write_if_missing "$DEST/daily/$(date +%Y-%m-%d).md" "# $(date '+%A, %B %d, %Y')

## signal

-

## loops

-

## notes

-
"

write_if_missing "$DEST/inbox/.gitkeep" ""
write_if_missing "$DEST/lore/.gitkeep" ""

cat <<EOF

$(green "[seed-vault] done.") vault laid out at:
  $DEST

open it with whichever editor your host supports:
  flatpak run md.obsidian.Obsidian "$DEST"                          # x86_64 only
  flatpak run org.gnome.gitlab.somas.Apostrophe "$DEST/welcome.md"  # aarch64 + x86_64

EOF
