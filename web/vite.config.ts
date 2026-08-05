import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const githubPagesBase = process.env.GITHUB_PAGES === "1"
  ? "/agentic-ontology-dashboard/"
  : "/";

export default defineConfig({
  base: githubPagesBase,
  plugins: [react()],
  // ManufacturingApp is route-lazy, so Vite's initial source scan does not
  // always discover its heavy UI dependencies before the first browser load.
  // Pre-bundle them during cold starts to avoid transient 504 Outdated
  // Optimize Dep responses on the public tunnel.
  optimizeDeps: {
    include: [
      "@blueprintjs/core",
      "@tanstack/react-table",
      "@tanstack/react-virtual",
      "@xyflow/react",
      "echarts",
      "echarts-for-react",
      "lucide-react",
      "react-grid-layout",
    ],
  },
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
