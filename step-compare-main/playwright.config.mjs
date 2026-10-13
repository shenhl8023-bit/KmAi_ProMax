import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:8765",
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "py -3 -m step_viewer --port 8765 --no-browser",
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
