import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// API base is configurable at build/runtime via VITE_API_BASE.
// Inside compose the web container nginx proxies /api and /health to the API.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: Number(env.WEB_PORT ?? 5173),
      proxy: {
        "/api": {
          target: env.API_PROXY_TARGET ?? "http://localhost:8000",
          changeOrigin: true,
        },
        "/health": {
          target: env.API_PROXY_TARGET ?? "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    preview: { host: "0.0.0.0", port: Number(env.WEB_PORT ?? 4173) },
  };
});
