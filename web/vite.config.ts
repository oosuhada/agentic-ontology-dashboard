import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = {
  "/api": { target: "http://127.0.0.1:8100" },
  "/health": { target: "http://127.0.0.1:8100" },
  "/docs": { target: "http://127.0.0.1:8100" },
  "/redoc": { target: "http://127.0.0.1:8100" },
  "/openapi.json": { target: "http://127.0.0.1:8100" },
};

export default defineConfig({
  base: "/",
  plugins: [react()],
  optimizeDeps: {
    include: ["@tanstack/react-virtual", "lucide-react"],
  },
  server: {
    host: "127.0.0.1",
    port: 3100,
    strictPort: true,
    allowedHosts: ["dashboard.oosu.dev"],
    proxy: apiProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 3100,
    strictPort: true,
    allowedHosts: ["dashboard.oosu.dev"],
    proxy: apiProxy,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
