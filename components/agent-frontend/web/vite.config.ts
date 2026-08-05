import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// ADR-0044: reproducible frontend toolchain producing static assets at
// build time, served by the Go binary in components/agent-frontend
// (see internal/assets). `base: "/static/"` matches the Go server's
// existing static-asset route prefix. `manifest: true` writes
// dist/.vite/manifest.json, which internal/assets reads at startup to
// resolve each entry's content-hashed filename - the standard Vite
// "backend integration" pattern (https://vite.dev/guide/backend-integration),
// chosen over hardcoding hashless filenames so cache-busting still works.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: {
    outDir: "dist",
    manifest: true,
    rollupOptions: {
      input: {
        portal: resolve(__dirname, "src/portal/main.tsx"),
        chat: resolve(__dirname, "src/chat/main.tsx"),
      },
    },
  },
});
