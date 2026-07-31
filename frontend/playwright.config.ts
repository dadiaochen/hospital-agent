import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests intentionally target the already-running Docker stack.
 * Keeping `webServer` out of this config makes it explicit that the E2E
 * contract includes the real frontend, backend, database and seeded data.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  timeout: 45_000,
  expect: {
    timeout: 8_000,
  },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "../var/playwright-report", open: "never" }],
  ],
  outputDir: "../var/playwright-test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Windows development uses the existing Edge installation so the
        // project does not need to download another browser binary.
        channel: process.env.E2E_BROWSER_CHANNEL ?? "msedge",
      },
    },
  ],
});
