import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const githubPagesBase = process.env.GITHUB_PAGES === "1"
  ? "/agentic-ontology-dashboard/"
  : "/";

export default defineConfig({
  base: githubPagesBase,
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3100,
    strictPort: true,
    allowedHosts: ["dashboard.oosu.dev"],
    proxy: { "/api": { target: "http://127.0.0.1:8100" } },
  },
  preview: {
    host: "127.0.0.1",
    port: 3100,
    strictPort: true,
    allowedHosts: ["dashboard.oosu.dev"],
    proxy: { "/api": { target: "http://127.0.0.1:8100" } },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
