import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:8000",
    trace: "off",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile-chrome", use: { ...devices["Pixel 7"] } },
    // Real WebKit, not Chromium's mobile emulation -- Chrome and Safari apply CSS/SVG
    // differently in ways emulation alone won't catch (e.g. Safari doesn't honor styles
    // defined inside an externally-referenced SVG document pulled in via <use>).
    { name: "mobile-safari", use: { ...devices["iPhone 14"] } },
  ],
});
