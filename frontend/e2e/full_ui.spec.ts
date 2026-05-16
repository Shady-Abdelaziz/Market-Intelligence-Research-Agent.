/**
 * Full UI walk-through as a real user — exercises every button and page in
 * the app against a live backend. Run after analyze+monitor smoke pass.
 *
 *   MIRA_E2E_API_BASE=http://127.0.0.1:8000 \
 *     npx playwright test e2e/full_ui.spec.ts --reporter=list
 */
import { test, expect } from "@playwright/test";

const API_BASE = process.env.MIRA_E2E_API_BASE || "http://localhost:8000";
const SKIP = !!process.env.PLAYWRIGHT_SKIP_E2E;

test.describe.serial("full UI walk", () => {
  test.skip(SKIP, "PLAYWRIGHT_SKIP_E2E set");

  test("home page renders chrome, samples, and brand", async ({ page }) => {
    await page.goto("/");
    // Topbar
    await expect(page.locator(".brand-mark")).toBeVisible();
    await expect(page.getByText("Market Intelligence Agent")).toBeVisible();
    // API health pill should resolve to ONLINE since backend is up.
    await expect(page.locator(".status")).toContainText(/API ONLINE/);
    // Two top tabs.
    await expect(page.getByRole("link", { name: "Report" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Monitors" })).toBeVisible();
    // Submit form.
    await expect(page.locator("textarea")).toBeVisible();
    const runBtn = page.locator("button.btn[type='submit']");
    await expect(runBtn).toBeVisible();
    await expect(runBtn).toBeDisabled(); // empty query
    // Sample tiles.
    await expect(page.locator(".sample")).toHaveCount(4);
    // Footer.
    await expect(page.getByText("POST /analyze")).toBeVisible();
  });

  test("typing in textarea enables submit, manual submit lands on job page", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    await textarea.fill("Analyze Microsoft (MSFT) outlook.");
    const runBtn = page.locator("button.btn[type='submit']");
    await expect(runBtn).toBeEnabled();
    await runBtn.click();
    await expect(page).toHaveURL(/\/jobs\//);
  });

  test("clicking a sample tile submits and routes to /jobs/<id>", async ({ page }) => {
    await page.goto("/");
    const firstSample = page.locator(".sample").first();
    await expect(firstSample).toBeVisible();
    await firstSample.click();
    await expect(page).toHaveURL(/\/jobs\//);
  });

  test("monitors page: filter chips render and toggle", async ({ page }) => {
    await page.goto("/monitor");
    const chips = page.locator(".filter-row button.filter");
    await expect(chips).toHaveCount(4); // All / Alert / Watching / Quiet
    // Click the second chip and confirm it gets the active class.
    await chips.nth(1).click();
    await expect(chips.nth(1)).toHaveClass(/active/);
  });

  test("end-to-end: submit AAPL via UI button, wait for completion, "
    + "verify Report renders, click JSON export, click Monitors tab",
    async ({ page, request }) => {
      // Submit via the UI rather than API to exercise the form path.
      await page.goto("/");
      await page.locator("textarea").fill("Analyze Apple (AAPL).");
      await page.locator("button.btn[type='submit']").click();
      await expect(page).toHaveURL(/\/jobs\//);

      // Wait until backend marks completed.
      const url = new URL(page.url());
      const jobId = url.pathname.split("/").pop();
      const deadline = Date.now() + 90_000;
      while (Date.now() < deadline) {
        const s = await request.get(`${API_BASE}/status/${jobId}`);
        if (s.ok()) {
          const body = await s.json();
          if (body.status === "completed") break;
          if (body.status === "failed") throw new Error(`job failed: ${body.error}`);
        }
        await page.waitForTimeout(2000);
      }

      // Reload to ensure the final report DOM mounts.
      await page.reload();
      await expect(page.locator(".finding").first()).toBeVisible();

      // Export buttons exist and are clickable.
      const jsonBtn = page.getByRole("button", { name: /JSON/i }).first();
      const pdfBtn = page.getByRole("button", { name: /PDF/i }).first();
      await expect(jsonBtn).toBeVisible();
      await expect(pdfBtn).toBeVisible();

      // Click JSON export — should trigger a download or open a blob URL.
      const [download] = await Promise.all([
        page.waitForEvent("download", { timeout: 8_000 }).catch(() => null),
        jsonBtn.click(),
      ]);
      // We don't require the download to succeed (the handler may use blob+anchor);
      // we only assert no exception was thrown and the button stayed in the DOM.
      void download;
      await expect(jsonBtn).toBeVisible();

      // Now navigate to Monitors via the top tab.
      await page.getByRole("link", { name: "Monitors" }).click();
      await expect(page).toHaveURL(/\/monitor/);
      await expect(page.locator(".brand-mark")).toBeVisible();
    });

  test("monitor lifecycle via UI: add → row visible → delete", async ({ page, request }) => {
    const ticker = "NVDA";
    await request.delete(`${API_BASE}/monitor/${ticker}`).catch(() => {});

    await page.goto("/monitor");
    // Add form: first input is the Ticker field, button reads "Start watching".
    const tickerInput = page.locator("section.add input").first();
    await tickerInput.fill(ticker);
    const addBtn = page
      .locator("section.add button.btn")
      .filter({ hasText: /Start watching|Adding/i })
      .first();
    await expect(addBtn).toBeEnabled();
    await addBtn.click();

    // The row should appear (baseline run + monitor list refresh).
    const row = page.locator(".monitor-row", { hasText: ticker });
    await expect(row).toBeVisible({ timeout: 30_000 });

    // Click the danger delete button. The handler calls window.confirm
    // before issuing DELETE /monitor/{ticker} — accept the dialog.
    page.once("dialog", (d) => d.accept());
    const delBtn = row.locator("button.danger");
    await expect(delBtn).toBeVisible();
    await delBtn.click();

    // Row should disappear after the list refresh.
    await expect(row).toHaveCount(0, { timeout: 15_000 });
  });
});
