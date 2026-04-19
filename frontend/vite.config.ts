import path from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// GitHub Pages serves from /<repo>/ by default; override via HOSAKA_BASE env var
// (set by the GH Pages workflow) to support project pages + custom domains.
const base = process.env.HOSAKA_BASE ?? "/";

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  build: {
    target: "es2022",
    sourcemap: true,
    // FastAPI serves static files from hosaka/web/ui (same path under /opt after rsync).
    outDir: path.resolve(__dirname, "../hosaka/web/ui"),
    emptyOutDir: true,
  },
});
