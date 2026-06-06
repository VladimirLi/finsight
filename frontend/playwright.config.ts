import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright end-to-end config — the top (browser) tier of the test pyramid.
 *
 * It boots the REAL stack (FastAPI backend + Vite dev server) via `webServer`
 * and drives the app through a Chromium browser. Two specs run against it:
 *
 *   - app.spec.ts        — UI smoke (routing, company CRUD, upload affordance);
 *                          needs no LLM, so it runs in CI.
 *   - extraction.spec.ts — full upload → extract → review flow against a
 *                          locally-deployed Ollama model; gated behind
 *                          RUN_LLM_E2E=1 and skipped when Ollama is unreachable.
 *
 * The backend is started with LLM_PROVIDER=ollama and a throwaway SQLite DB so
 * nothing touches a developer's real finsight.db.
 */

const BACKEND_PORT = 8000;
const FRONTEND_PORT = 5173;
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? "http://localhost:11434";
const LLM_MODEL = process.env.E2E_LLM_MODEL ?? "llama3.1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Backend on a throwaway DB, wired to the local Ollama deployment.
      command:
        "cd ../backend && .venv/bin/uvicorn app.main:app --port 8000 --log-level warning",
      port: BACKEND_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        DATABASE_URL: "sqlite:///./_e2e.db",
        UPLOAD_DIR: "./_e2e_uploads",
        LLM_PROVIDER: "ollama",
        LLM_MODEL,
        OLLAMA_BASE_URL,
      },
    },
    {
      command: "npm run dev",
      port: FRONTEND_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
