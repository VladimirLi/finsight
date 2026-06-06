import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { existsSync } from "node:fs";
import { test, expect } from "@playwright/test";

/**
 * Full-stack extraction flow against a LOCALLY-DEPLOYED LLM (Ollama).
 *
 * This is the heaviest tier of the pyramid: it uploads a REAL company filing
 * (the consolidated financial statements sliced from Berkshire Hathaway's
 * annual report) and lets the genuine OCR + Ollama pipeline extract it through
 * the live backend, then verifies the review screen renders extracted items and
 * a ratio report. Because it depends on a running Ollama with a pulled model and
 * a third-party (uncommitted) fixture, it is:
 *
 *   - opt-in: only runs when RUN_LLM_E2E=1, and
 *   - self-skipping: skipped if Ollama is unreachable or the fixture is missing.
 *
 * Fetch the real fixture once (it is git-ignored, not vendored):
 *   backend/.venv/bin/python scripts/fetch_e2e_fixture.py
 *
 * Run it (with Ollama up and a model pulled, e.g. `ollama pull llama3.1`):
 *   RUN_LLM_E2E=1 npm run e2e
 */

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? "http://localhost:11434";
const __dirname = dirname(fileURLToPath(import.meta.url));
const SAMPLE_PDF = join(__dirname, "fixtures", "real-financials.pdf");

test.describe("full extraction against Ollama", () => {
  test.skip(
    process.env.RUN_LLM_E2E !== "1",
    "LLM e2e is opt-in; set RUN_LLM_E2E=1 with a local Ollama running.",
  );

  // Extraction with a local model is slow; give the whole flow generous room.
  test.setTimeout(300_000);

  test.beforeAll(async () => {
    if (!existsSync(SAMPLE_PDF)) {
      test.skip(
        true,
        "Missing fixture — run scripts/fetch_e2e_fixture.py to fetch it.",
      );
    }
    // Confirm Ollama is actually reachable; skip rather than fail if not.
    try {
      const res = await fetch(`${OLLAMA_BASE_URL}/api/tags`);
      if (!res.ok) test.skip(true, `Ollama not healthy at ${OLLAMA_BASE_URL}`);
    } catch {
      test.skip(true, `Ollama unreachable at ${OLLAMA_BASE_URL}`);
    }
  });

  test("upload → extract → review shows items and ratios", async ({ page }) => {
    await page.goto("/upload");

    // The file input is visually hidden; setInputFiles works on it directly.
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF);
    await page.getByRole("button", { name: /upload & process/i }).click();

    // The pipeline runs server-side; wait (long) for the reviewable state.
    const reviewLink = page.getByRole("link", { name: /review & ratios/i });
    await expect(reviewLink).toBeVisible({ timeout: 240_000 });
    await reviewLink.click();

    await expect(
      page.getByRole("heading", { name: /review period/i }),
    ).toBeVisible();

    // Extracted Items tab: the model should have found at least one line item.
    await expect(page.getByText(/items extracted/i)).toBeVisible();
    const itemRows = page.locator(".item-row");
    expect(await itemRows.count()).toBeGreaterThan(0);

    // Ratio Report tab: a deterministic report renders from the extracted items.
    await page.getByRole("button", { name: /ratio report/i }).click();
    const ratioCards = page.locator(".ratio-card");
    await expect(ratioCards.first()).toBeVisible();
    expect(await ratioCards.count()).toBeGreaterThan(0);
  });
});
