#!/usr/bin/env bash
# Seed ~/Books with a handful of public-domain epubs from Project Gutenberg.
#
# Foliate (com.github.johnfactotum.Foliate) doesn't have a fixed library
# path; it just opens whatever you point it at. We pick ~/Books/ as the
# convention and pre-populate it so a fresh kiosk has something to read.
#
# Usage:
#   bash scripts/seed-books.sh                # download to ~/Books
#   BOOKS_DIR=/data/lib bash scripts/seed-books.sh
#
# Idempotent: skips files that already exist.

set -euo pipefail

DEST="${BOOKS_DIR:-$HOME/Books}"
mkdir -p "$DEST"

# Curated public-domain set spanning ancient/eastern/western canon plus
# the doomsday-prep / cyberpunk-adjacent reading list. All from Project
# Gutenberg, all small (< 2 MB each), all plain ascii or utf-8.
# Format: "<filename>|<gutenberg ID>|<title>"
BOOKS=(
  # ancient + sacred
  "gilgamesh.epub|11000|The Epic of Gilgamesh"
  "egyptian-book-of-the-dead.epub|7145|The Egyptian Book of the Dead"
  "tao-te-ching.epub|216|Tao Te Ching — Lao Tzu"
  "bhagavad-gita.epub|2388|Bhagavad-Gita"
  "art-of-war.epub|132|The Art of War — Sun Tzu"
  "meditations.epub|2680|Meditations — Marcus Aurelius"
  # western classics
  "frankenstein.epub|84|Frankenstein — Mary Shelley"
  "moby-dick.epub|2701|Moby-Dick — Herman Melville"
  "pride-and-prejudice.epub|1342|Pride and Prejudice — Jane Austen"
  "alice-in-wonderland.epub|11|Alice's Adventures in Wonderland — Lewis Carroll"
  "sherlock-holmes.epub|1661|Adventures of Sherlock Holmes — A. C. Doyle"
  "dracula.epub|345|Dracula — Bram Stoker"
  "time-machine.epub|35|The Time Machine — H. G. Wells"
  "war-of-the-worlds.epub|36|The War of the Worlds — H. G. Wells"
  # practical / prepper-adjacent
  "walden.epub|205|Walden — H. D. Thoreau"
  "republic.epub|1497|The Republic — Plato"
  "prince.epub|1232|The Prince — Machiavelli"
)

cyan() { printf '\033[0;36m%s\033[0m' "$*"; }
green() { printf '\033[0;32m%s\033[0m' "$*"; }

echo "$(cyan "[seed-books]") destination: $DEST"

for entry in "${BOOKS[@]}"; do
  fn="${entry%%|*}"; rest="${entry#*|}"
  id="${rest%%|*}"; title="${rest#*|}"
  out="$DEST/$fn"
  if [[ -s "$out" ]]; then
    echo "  · $(green skip) $fn — already present ($title)"
    continue
  fi
  url="https://www.gutenberg.org/ebooks/${id}.epub.images"
  echo "  · fetch $fn ← $title"
  if curl -fsSL --max-time 60 -o "$out.partial" "$url"; then
    mv "$out.partial" "$out"
    echo "    $(green ok)"
  else
    rm -f "$out.partial"
    echo "    $(printf '\033[0;31m%s\033[0m' fail) — gutenberg may be rate-limiting; retry later"
  fi
done

cat <<EOF

$(green "[seed-books] done.") open foliate and point it at:
  $DEST

or stage them as a foliate "library folder" via:
  flatpak run --command=foliate com.github.johnfactotum.Foliate "$DEST"

EOF
