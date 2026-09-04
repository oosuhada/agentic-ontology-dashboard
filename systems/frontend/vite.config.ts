import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const configuredBase = process.env.VITE_APP_BASE_PATH?.trim();
const githubPagesBase = process.env.GITHUB_PAGES === "1"
  ? "/agentic-ontology-dashboard/"
  : "/";
const appBase = configuredBase
  ? `/${configuredBase.replace(/^\/+|\/+$/g, "")}/`
  : githubPagesBase;

const apiProxy = {
  "/api": { target: "http://127.0.0.1:8100" },
  "/health": { target: "http://127.0.0.1:8100" },
  "/docs": { target: "http://127.0.0.1:8100" },
  "/redoc": { target: "http://127.0.0.1:8100" },
  "/openapi.json": { target: "http://127.0.0.1:8100" },
};

function interactiveTeamShareRoute(): Plugin {
  const rewrite = (
    request: { url?: string },
    _response: unknown,
    next: () => void,
  ) => {
    const url = request.url ?? "";
    const suffixIndex = url.search(/[?#]/);
    const pathname = suffixIndex === -1 ? url : url.slice(0, suffixIndex);
    if (pathname === "/team-share-adaptive") {
      request.url = `/index.html${suffixIndex === -1 ? "" : url.slice(suffixIndex)}`;
    }
    next();
  };
  return {
    name: "interactive-team-share-route",
    configureServer(server) {
      server.middlewares.use(rewrite);
    },
    configurePreviewServer(server) {
      server.middlewares.use(rewrite);
    },
  };
}

export default defineConfig({
  base: appBase,
  plugins: [interactiveTeamShareRoute(), react()],
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
    proxy: apiProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 3100,
    strictPort: true,
    allowedHosts: ["dashboard.oosu.dev"],
    proxy: apiProxy,
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
