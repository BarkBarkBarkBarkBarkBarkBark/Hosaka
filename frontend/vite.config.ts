import path from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";
import { writeFileSync } from "fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// GitHub Pages serves from /<repo>/ by default; override via HOSAKA_BASE env var
// (set by the GH Pages workflow) to support project pages + custom domains.
const base = process.env.HOSAKA_BASE ?? "/";

// Only emit sourcemaps when explicitly asked (CI / dev machines). On the Pi
// they double the on-disk asset size and roughly double the build's RAM peak,
// which is exactly the budget we don't have on a Pi 3B.
const wantSourcemaps = process.env.HOSAKA_SOURCEMAP === "1";
const apiTarget = process.env.HOSAKA_API_TARGET ?? "http://127.0.0.1:8421";

// Build stamp baked into the bundle so an operator can verify a redeploy
// actually loaded. Visible in the menu's "diagnostics" section, on
// `window.__hosakaBuild`, and printed to console at boot. Prefer git sha;
// fall back to env vars (HOSAKA_BUILD_SHA / HOSAKA_BUILD_REF) when the
// build runs outside a checkout (e.g. CI tarball).
function detectBuildStamp(): { sha: string; ref: string; iso: string } {
  let sha = process.env.HOSAKA_BUILD_SHA ?? "";
  let ref = process.env.HOSAKA_BUILD_REF ?? "";
  if (!sha) {
    try { sha = execSync("git rev-parse --short=10 HEAD", { cwd: __dirname }).toString().trim(); }
    catch { sha = "unknown"; }
  }
  if (!ref) {
    try { ref = execSync("git rev-parse --abbrev-ref HEAD", { cwd: __dirname }).toString().trim(); }
    catch { ref = "?"; }
  }
  return { sha, ref, iso: new Date().toISOString() };
}
const __HOSAKA_BUILD__ = detectBuildStamp();

export default defineConfig({
  base,
  plugins: [
    react(),
    {
      // Drop a sidecar JSON next to the built assets so server-side tools
      // (hosaka logs dump, smoke tests) can confirm what's deployed without
      // parsing the JS bundle.
      name: "hosaka-build-stamp",
      apply: "build",
      writeBundle() {
        const out = path.resolve(__dirname, "../hosaka/web/ui/build-stamp.json");
        try { writeFileSync(out, JSON.stringify(__HOSAKA_BUILD__) + "\n"); }
        catch { /* non-fatal */ }
      },
    },
  ],
  define: {
    __HOSAKA_BUILD__: JSON.stringify(__HOSAKA_BUILD__),
  },
  resolve: {
    alias: [
      // @automerge/automerge's "browser" export imports its WASM via ESM-
      // import syntax (needs vite-plugin-wasm). Route directly to the
      // `fullfat_base64.js` build which inlines the WASM as base64 — works
      // out of the box, costs ~1.2 MB of inlined wasm once per page load.
      // Using a literal file path (not the package specifier) sidesteps
      // the `exports` map's "browser" condition entirely.
      {
        find: /^@automerge\/automerge$/,
        replacement: path.resolve(
          __dirname,
          "node_modules/@automerge/automerge/dist/mjs/entrypoints/fullfat_base64.js",
        ),
      },
    ],
  },
  optimizeDeps: {
    // Same reason — dev mode pre-bundling would otherwise follow the
    // bundler entry and hit the same WASM-import error as `vite build`.
    exclude: ["@automerge/automerge"],
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    fs: {
      // The frontend imports hosaka-apps/*.yaml via ?raw/import.meta.glob.
      // Those files live outside frontend/, so Vite dev needs explicit access.
      allow: [__dirname, path.resolve(__dirname, "..")],
    },
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    target: "es2022",
    sourcemap: wantSourcemaps,
    minify: "esbuild",
    cssMinify: "esbuild",
    reportCompressedSize: false,
    chunkSizeWarningLimit: 1024,
    outDir: path.resolve(__dirname, "../hosaka/web/ui"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Keep the entry chunk small. React + ReactDOM go in their own
        // long-cacheable vendor chunk; xterm and Automerge get their own
        // buckets so panel-source edits don't invalidate them on every
        // hosaka update (huge cold-start win on the Pi where re-parse of
        // the Automerge fullfat_base64 chunk is multi-second). Everything
        // else lands in lazy chunks via dynamic imports in App.tsx.
        manualChunks: (id) => {
          if (id.includes("node_modules/react-dom/")) return "react-vendor";
          if (id.includes("node_modules/react/")) return "react-vendor";
          if (id.includes("node_modules/scheduler/")) return "react-vendor";
          if (id.includes("node_modules/@xterm/")) return "xterm-vendor";
          if (id.includes("node_modules/@automerge/")) return "automerge-vendor";
          if (id.includes("node_modules/idb-keyval")) return "idb-vendor";
          return undefined;
        },
      },
    },
  },
});
