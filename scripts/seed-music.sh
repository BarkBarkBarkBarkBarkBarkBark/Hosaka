#!/usr/bin/env bash
# Seed ~/Music with public-domain jazz and classical from archive.org.
#
# Why the metadata API instead of hardcoded mp3 URLs? IA's deep links
# break whenever a curator renames a file. The /metadata/<item> JSON
# endpoint is stable and lists every file in the item — we pick the
# first .mp3 (or .ogg) and download that. Resilient to filename drift.
#
# Usage:
#   bash scripts/seed-music.sh                # download to ~/Music
#   MUSIC_DIR=/data/music bash scripts/seed-music.sh
#
# Idempotent: skips files that already exist. Total payload ~30-60 MB.

set -euo pipefail

DEST="${MUSIC_DIR:-$HOME/Music}"
mkdir -p "$DEST/jazz" "$DEST/classical"

cyan()  { printf '\033[0;36m%s\033[0m' "$*"; }
green() { printf '\033[0;32m%s\033[0m' "$*"; }
red()   { printf '\033[0;31m%s\033[0m' "$*"; }

echo "$(cyan "[seed-music]") destination: $DEST"

# Format: "<subdir>|<output-prefix>|<archive.org item id>|<label>"
ITEMS=(
  # ── classical ──
  "classical|bach-brandenburg-3|BrandenburgConcertoNo.3InGMajorBwv1048|Bach — Brandenburg No. 3"
  "classical|debussy-clair-de-lune|ClairDeLune_555|Debussy — Clair de Lune"
  "classical|beethoven-moonlight|MoonlightSonata_201310|Beethoven — Moonlight Sonata"
  "classical|mozart-eine-kleine|EineKleineNachtmusik_201310|Mozart — Eine kleine Nachtmusik"
  # ── jazz (78rpm, pre-1929 = public domain in the US) ──
  "jazz|armstrong-west-end-blues|78_west-end-blues_louis-armstrong-and-his-hot-five-clarence-williams_gbia0010289b|Louis Armstrong — West End Blues"
  "jazz|ellington-east-st-louis|78_east-st.-louis-toodle-oo_duke-ellington-and-his-orchestra-bub-miller-tricky_gbia0011093|Duke Ellington — East St. Louis Toodle-Oo"
  "jazz|jelly-roll-morton-black-bottom|78_black-bottom-stomp_jelly-roll-morton-and-his-red-hot-peppers-jelly-roll-morto_gbia0011085|Jelly Roll Morton — Black Bottom Stomp"
  "jazz|bix-beiderbecke-singin-the-blues|78_singin-the-blues_frankie-trumbauer-and-his-orchestra-bix-beiderbecke-jimmy-do_gbia0011096|Bix Beiderbecke — Singin' the Blues"
)

# Pick the first audio file (.mp3 preferred, .ogg fallback) from the
# IA metadata JSON. python3 to avoid a jq dependency on the Pi.
pick_audio_file() {
  local item="$1"
  curl -fsSL --max-time 30 "https://archive.org/metadata/${item}" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
files = d.get('files', []) or []
def score(f):
    name = (f.get('name') or '').lower()
    fmt  = (f.get('format') or '').lower()
    if name.endswith('.mp3'): return 0
    if name.endswith('.ogg'): return 1
    if 'mp3' in fmt:          return 2
    if 'ogg' in fmt:          return 3
    return 99
files = [f for f in files if isinstance(f.get('name'), str)]
files.sort(key=score)
for f in files:
    if score(f) < 99:
        print(f['name'])
        sys.exit(0)
sys.exit(2)
"
}

retry_curl() {
  local url="$1" out="$2"
  local tries=3 i
  for i in $(seq 1 $tries); do
    if curl -fsSL --max-time 120 -o "$out.partial" "$url"; then
      mv "$out.partial" "$out"
      return 0
    fi
    rm -f "$out.partial"
    if [[ $i -lt $tries ]]; then
      echo "    retry $i/$((tries-1)) after brief pause…"
      sleep 3
    fi
  done
  return 1
}

for entry in "${ITEMS[@]}"; do
  IFS='|' read -r sub prefix item label <<<"$entry"
  existing=$(ls "$DEST/$sub/${prefix}".* 2>/dev/null | head -1 || true)
  if [[ -n "$existing" ]]; then
    echo "  · $(green skip) $sub/${prefix}.* — already present"
    continue
  fi

  echo "  · resolve $label"
  fname=$(pick_audio_file "$item" || true)
  if [[ -z "$fname" ]]; then
    echo "    $(red fail) — no audio file in /metadata/${item}"
    continue
  fi

  ext="${fname##*.}"
  out="$DEST/$sub/${prefix}.${ext}"
  url="https://archive.org/download/${item}/${fname}"
  echo "    fetch ← ${fname}"
  if retry_curl "$url" "$out"; then
    echo "    $(green ok) $(du -h "$out" | cut -f1)"
  else
    echo "    $(red fail) — IA may be throttling; rerun later"
  fi
done

cat <<EOF

$(green "[seed-music] done.") library laid out at:
  $DEST/jazz/
  $DEST/classical/

press play with any of these:
  flatpak run dev.dergs.Tonearm                      # tonearm
  flatpak run org.gnome.Music                        # gnome music
  mpv "$DEST/jazz"                                   # cli demo

EOF
