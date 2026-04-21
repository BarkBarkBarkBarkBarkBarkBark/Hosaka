# This directory is intentionally empty.
#
# The Vercel build (hosaka-field-terminal → scripts/sync-console.sh) does a
# `cp -r frontend/public/locales …` during the "syncing public/" step. The
# actual locale JSON for the SPA lives at frontend/src/locales/ and is bundled
# by Vite (see frontend/src/i18n.ts), so nothing needs to be served from here
# — but the directory has to exist or the sync script fails pre-build.
#
# If you move locales back to runtime-served JSON, populate this folder.
