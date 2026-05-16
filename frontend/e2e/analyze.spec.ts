import { test, expect } from "@playwright/test";

const API_BASE = process.env.MIRA_E2E_API_BASE || "http://localhost:8000";

const SKIP = !!process.env.PLAYWRIGHT_SKIP_E2E;

test.describe("analyze flow", () => {
  test.skip(SKIP, "PLAYWRIGHT_SKIP_E2E set");

  test("submit Apple query, land on report, render rich cards", async ({ page, request }) => {
    // Submit via API so we don't depend on the textarea polling cycle —
    // the page render is what we're verifying.
    const res = await request.post(`${API_BASE}/analyze`, {
      data: { query: "Analyze Apple Inc. (AAPL)" },
    });
    expect(res.ok()).toBeTruthy();
    const { job_id } = await res.json();
    expect(job_id).toBeTruthy();

    await page.goto(`/jobs/${job_id}`);

    // Poll until completed (or 90 s).
    const deadline = Date.now() + 90_000;
    let report: any = null;
    while (Date.now() < deadline) {
      const s = await request.get(`${API_BASE}/status/${job_id}`);
      if (s.ok()) {
        const body = await s.json();
        if (body.status === "completed") {
          // /status exposes the synthesized payload as `report`
          // (backend/app/api/status.py: out["report"] = job.result_json).
          report = body.report;
          break;
        }
        if (body.status === "failed") throw new Error(`job failed: ${body.error}`);
      }
      await page.waitForTimeout(2000);
    }
    expect(report, "job did not complete in 90s").toBeTruthy();

    // Force one more refresh so the page renders the final state.
    await page.reload();

    // Summary card renders at least one <p class="lead">.
    const leadParas = page.locator("p.lead");
    await expect(leadParas.first()).toBeVisible();

    // Correlation card shows interpretation captions.
    await expect(page.locator(".corr-caption").first()).toBeVisible();

    // Three key findings.
    const findings = page.locator(".finding");
    await expect(findings).toHaveCount(3);

    // Quarterly revenue bars render when data exists.
    if ((report.market_snapshot?.last_two_quarterly_revenues || []).length > 0) {
      await expect(page.locator(".rev-bars")).toBeVisible();
    }

    // Outlook card renders only when the synthesizer populated extended_analysis.
    // Don't fail the test if the LLM left it null on this run.
    const outlookHeader = page.getByText("§ I.5 — Outlook");
    if (await outlookHeader.count()) {
      await expect(outlookHeader.first()).toBeVisible();
    }
  });
});
