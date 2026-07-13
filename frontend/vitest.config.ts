import { defineConfig } from "vitest/config";

// Node 22+ gates globalThis.localStorage behind this CLI flag (jsdom no longer
// ships its own polyfill, deferring to the runtime's) -- theme.ts's
// setupThemeToggle() uses localStorage directly, so tests need it available.
// Set via NODE_OPTIONS (inherited by whatever child process vitest's pool
// spawns) rather than a pool-specific execArgv option, since that option's
// shape has changed across vitest major versions.
process.env.NODE_OPTIONS =
  `${process.env.NODE_OPTIONS ?? ""} --localstorage-file=.vitest-localstorage.sqlite`.trim();

// Separate from vite.config.ts (which configures the multi-page app build/dev
// server, not relevant here) -- unit tests for browser-API-touching modules
// (cookies.ts, theme.ts) that don't warrant a real browser (see test/e2e/ for
// that). Only picks up src/**/*.test.ts, so it never collides with the
// Playwright specs in ../test/e2e/.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
});
