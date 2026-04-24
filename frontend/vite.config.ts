import path from "path";
import { fileURLToPath } from "url";
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

export default defineConfig({
  base,
  plugins: [react()],
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
        // long-cacheable vendor chunk; everything else (panels, locales)
        // ends up in lazy chunks via dynamic imports in App.tsx.
        manualChunks: (id) => {
          if (id.includes("node_modules/react-dom/")) return "react-vendor";
          if (id.includes("node_modules/react/")) return "react-vendor";
          if (id.includes("node_modules/scheduler/")) return "react-vendor";
          return undefined;
        },
      },
    },
  },
});
