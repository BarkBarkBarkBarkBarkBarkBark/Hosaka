#!/usr/bin/env bash
# Seed ~/Music with a small, demo-able set of public-domain jazz and
# classical recordings from archive.org's Open Source Audio collection.
#
# Why archive.org and not flatpak/spotify? Streaming services need a
# logged-in account to demo. Local mp3s play in any audio app (Tonearm,
# GNOME Music, mpv, even Foliate's epub readalong).
#
# Usage:
#   bash scripts/seed-music.sh                # download to ~/Music
#   MUSIC_DIR=/data/music bash scripts/seed-music.sh
#
# Idempotent: skips files that already exist. Total payload ~30 MB.

set -euo pipefail

DEST="${MUSIC_DIR:-$HOME/Music}"
mkdir -p "$DEST/jazz" "$DEST/classical"

cyan()  { printf '\033[0;36m%s\033[0m' "$*"; }
green() { printf '\033[0;32m%s\033[0m' "$*"; }
red()   { printf '\033[0;31m%s\033[0m' "$*"; }

echo "$(cyan "[seed-music]") destination: $DEST"

# Format: "<subdir>|<filename>|<archive.org URL>|<label>"
# All items below are public domain (pre-1929 recordings) hosted by
# archive.org's "78rpm" and Open Source Audio collections. URLs picked
# for stability — single-track mp3 deep links.
TRACKS=(
  # ── classical ──
  "classical|debussy-clair-de-lune.mp3|https://archive.org/download/ClairDeLune_555/Clair%20de%20Lune.mp3|Debussy — Clair de Lune"
  "classical|bach-brandenburg-3.mp3|https://archive.org/download/BrandenburgConcertoNo.3InGMajorBwv1048/Brandenburg%20Concerto%20No.%203%20in%20G%20major%2C%20BWV%201048.mp3|Bach — Brandenburg Concerto No. 3"
  "classical|beethoven-symphony-7-mvt2.mp3|https://archive.org/download/BeethovenSymphonyNo.7Mov.2/Beethoven%20-%20Symphony%20No.%207%2C%20Mov.%202.mp3|Beethoven — Symphony No. 7 mvt II"
  "classical|mozart-eine-kleine.mp3|https://archive.org/download/EineKleineNachtmusik_201310/Eine%20Kleine%20Nachtmusik.mp3|Mozart — Eine kleine Nachtmusik"
  # ── jazz (78rpm public-domain) ──
  "jazz|armstrong-west-end-blues.mp3|https://archive.org/download/78_west-end-blues_louis-armstrong-and-his-hot-five-clarence-williams_gbia0010289b/78_west-end-blues_louis-armstrong-and-his-hot-five-clarence-williams_gbia0010289b_01_2.7_CT_EQ.mp3|Louis Armstrong — West End Blues (1928)"
  "jazz|ellington-east-st-louis.mp3|https://archive.org/download/78_east-st.-louis-toodle-oo_duke-ellington-and-his-orchestra-bub-miller-tricky_gbia0011093/78_east-st.-louis-toodle-oo_duke-ellington-and-his-orchestra-bub-miller-tricky_gbia0011093_01_2.7_CT_EQ.mp3|Duke Ellington — East St. Louis Toodle-Oo (1927)"
  "jazz|jelly-roll-morton-black-bottom-stomp.mp3|https://archive.org/download/78_black-bottom-stomp_jelly-roll-morton-and-his-red-hot-peppers-jelly-roll-morto_gbia0011085/78_black-bottom-stomp_jelly-roll-morton-and-his-red-hot-peppers-jelly-roll-morto_gbia0011085_01_2.7_CT_EQ.mp3|Jelly Roll Morton — Black Bottom Stomp (1926)"
  "jazz|bix-beiderbecke-singin-the-blues.mp3|https://archive.org/download/78_singin-the-blues_frankie-trumbauer-and-his-orchestra-bix-beiderbecke-jimmy-do_gbia0011096/78_singin-the-blues_frankie-trumbauer-and-his-orchestra-bix-beiderbecke-jimmy-do_gbia0011096_01_2.7_CT_EQ.mp3|Bix Beiderbecke — Singin' the Blues (1927)"
)

for entry in "${TRACKS[@]}"; do
  IFS='|' read -r sub fn url label <<<"$entry"
  out="$DEST/$sub/$fn"
  if [[ -s "$out" ]]; then
    echo "  · $(green skip) $sub/$fn — already present"
    continue
  fi
  echo "  · fetch $sub/$fn ← $label"
  if curl -fsSL --max-time 90 -o "$out.partial" "$url"; then
    mv "$out.partial" "$out"
    echo "    $(green ok)"
  else
    rm -f "$out.partial"
    echo "    $(red fail) — archive.org link drift; check the IA item page"
  fi
done

cat <<EOF

$(green "[seed-music] done.") library laid out at:
  $DEST/jazz/
  $DEST/classical/

points any audio player at the folder. example:
  flatpak run org.gnome.Music                        # gnome music
  mpv "$DEST/jazz"                                   # cli demo
  flatpak run org.gnome.gitlab.somas.Apostrophe      # not a music player; for fun

EOF
