import { defineConfig, devices } from "@playwright/test";

// Browser tests against a running stack (DEMO_MODE=true, mock LLM): `make e2e` or `make verify-f`.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    trace: "retain-on-failure",
  },
});
