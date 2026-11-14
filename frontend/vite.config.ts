import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In local dev (`npm run dev`) API and WebSocket calls are proxied to the backend.
// In Docker, nginx does the same job (see nginx.conf).
const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": { target, changeOrigin: true },
      "/ws": { target: target.replace(/^http/, "ws"), ws: true },
    },
  },
});
