import { test, expect } from "@playwright/test";

/**
 * UI smoke — exercises the parts of the app that need no LLM extraction:
 * routing/navigation, the empty states, and company creation through the modal
 * (which round-trips POST /companies → GET /companies against the real backend).
 *
 * Runs in CI because it depends only on the backend API, not on a model.
 */

test.describe("app shell", () => {
  test("redirects root to the upload page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/upload$/);
    await expect(
      page.getByRole("heading", { name: /upload financial statement/i }),
    ).toBeVisible();
    // The drop zone is the primary affordance on the upload page.
    await expect(page.getByText(/drop your pdf here/i)).toBeVisible();
  });

  test("navigates between the main sections", async ({ page }) => {
    await page.goto("/upload");
    await page.getByRole("link", { name: "Documents", exact: true }).click();
    await expect(page).toHaveURL(/\/documents$/);

    await page.getByRole("link", { name: "Companies", exact: true }).click();
    await expect(page).toHaveURL(/\/companies$/);
    await expect(
      page.getByRole("heading", { name: /companies/i }),
    ).toBeVisible();
  });
});

test.describe("company creation", () => {
  test("creates a company via the modal and lists it", async ({ page }) => {
    // Unique name so repeated local runs don't collide in a shared dev DB.
    const name = `E2E Test Co ${Date.now()}`;

    await page.goto("/companies");
    // Header trigger ("+ New company") opens the modal.
    await page.getByRole("button", { name: /new company/i }).click();

    const modal = page.locator("form.modal");
    await expect(
      modal.getByRole("heading", { name: /new company/i }),
    ).toBeVisible();

    await modal.getByPlaceholder("Acme Corp", { exact: true }).fill(name);
    await modal.getByPlaceholder("ACME", { exact: true }).fill("E2E");
    await modal.getByPlaceholder("USD", { exact: true }).fill("USD");

    // Submit via the modal's own primary button.
    await modal.getByRole("button", { name: "Create", exact: true }).click();

    // The newly created company should appear in the listing.
    await expect(page.getByText(name)).toBeVisible();
  });
});
