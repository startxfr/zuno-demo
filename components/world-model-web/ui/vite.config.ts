import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served at / by world-model-web (StaticFiles); the API is on the same origin, so no proxy in production.
// For `npm run dev` against a local world-model-web (WORLD_MODEL_AUTH=dev), proxy /api to it.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
  server: { proxy: { "/api": { target: "http://127.0.0.1:8080", ws: true } } },
});
