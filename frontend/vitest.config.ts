import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    // Unit/component tests live under src/. The Playwright e2e specs under e2e/
    // use @playwright/test (not vitest) and must not be collected here.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    coverage: {
      provider: "v8",
      // Measure coverage over all source files scanned during tests.
      // Thresholds are set conservatively at just below current levels so that
      // regressions (deleting tests, adding untested code) trip the gate, while
      // new features without unit tests don't immediately block CI.
      thresholds: {
        lines: 60,
        functions: 60,
        statements: 60,
        branches: 50,
      },
    },
  },
});
