/**
 * Hosted-build stub for sync/repo.
 *
 * The local appliance build of repo.ts drags in ~1.2 MB of Automerge WASM,
 * which is wasted weight for the hosted Vercel marketing SPA (never syncs,
 * `nodes_enabled: false`). Field-terminal's vite.config.ts aliases
 * `./sync/repo` → this file so the hosted bundle never compiles the real
 * repo and therefore never bundles Automerge.
 *
 * The appliance build of vite.config.ts does NOT use this alias.
 */
export function startSync(): void {
  // no-op on hosted builds; nodes_enabled is always false there anyway
}
