import { defineConfig, devices } from "@playwright/test";

const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? "3200";
const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "8200";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${webPort}`;
const apiURL = process.env.PLAYWRIGHT_API_URL ?? `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVERS === "1" ? undefined : [
    {
      command: `sh -c 'DB=/tmp/ontology-dashboard-playwright-$$.db; ARTIFACTS=/tmp/ontology-dashboard-playwright-$$-datasets; rm -f "$DB"; rm -rf "$ARTIFACTS"; APP_ENV=test SEED_DEMO_ACCOUNTS=1 ONTOLOGY_DASHBOARD_DB="$DB" PYTHONPATH=../api:../ml/src ../.venv/bin/python ../scripts/seed_demo_dataset_catalog.py --database "$DB" --artifact-root "$ARTIFACTS" >/tmp/ontology-dashboard-playwright-seed.log && APP_ENV=test SEED_DEMO_ACCOUNTS=1 ONTOLOGY_DASHBOARD_DB="$DB" PYTHONPATH=../api:../ml/src ../.venv/bin/python -m uvicorn ontology_dashboard.main:app --host 127.0.0.1 --port ${apiPort}'`,
      url: `${apiURL}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: `VITE_API_BASE_URL=${apiURL} ./node_modules/.bin/vite --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: baseURL,
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
