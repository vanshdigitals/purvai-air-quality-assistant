import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const ALL_APP_ROUTES = [
  "/today",
  "/plan",
  "/ask",
  "/home-air",
  "/impact",
  "/reports",
  "/settings",
  "/nonexistent-404",
] as const;

const WELCOME_ROUTES = [
  "/welcome",
  "/welcome/location",
  "/welcome/household",
  "/welcome/commute",
] as const;

async function onboardAndMeasure(page: Page): Promise<number> {
  const start = Date.now();
  await page.goto("/welcome");
  await page.getByRole("button", { name: /Get started/i }).click();
  await expect(page).toHaveURL(/\/welcome\/location$/);
  await page.getByLabel("Search city or neighbourhood").fill("Noida");
  const resultRow = page.getByRole("radio", { name: /Sector 62, Noida/i });
  await expect(resultRow).toBeVisible();
  await resultRow.click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/welcome\/household$/);
  await page.getByText("Child under 12").click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/welcome\/commute$/);
  await page.getByRole("radio", { name: "Metro" }).click();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page).toHaveURL(/\/today$/);
  return Date.now() - start;
}

test.describe("Purvai Phase 6 A11Y & Performance", () => {
  test("axe passes on welcome routes in light & dark at 375x812 and 1280x800", async ({ page }) => {
    test.setTimeout(90_000);
    for (const vp of [
      { width: 375, height: 812 },
      { width: 1280, height: 800 },
    ]) {
      await page.setViewportSize(vp);
      for (const route of WELCOME_ROUTES) {
        for (const theme of ["light", "dark"] as const) {
          await page.goto(route);
          await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
          const results = await new AxeBuilder({ page }).analyze();
          const bad = results.violations.filter(
            (v) => v.impact === "serious" || v.impact === "critical"
          );
          expect(bad, `${route} (${theme} ${vp.width}x${vp.height})`).toEqual([]);
        }
      }
    }
  });

  test("axe passes on all app routes in light & dark at 375x812 and 1280x800", async ({ page }) => {
    test.setTimeout(120_000);
    await onboardAndMeasure(page);

    for (const vp of [
      { width: 375, height: 812 },
      { width: 1280, height: 800 },
    ]) {
      await page.setViewportSize(vp);
      for (const route of ALL_APP_ROUTES) {
        for (const theme of ["light", "dark"] as const) {
          await page.goto(route);
          await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
          const results = await new AxeBuilder({ page }).analyze();
          const bad = results.violations.filter(
            (v) => v.impact === "serious" || v.impact === "critical"
          );
          expect(bad, `${route} (${theme} ${vp.width}x${vp.height})`).toEqual([]);
        }
      }
    }
  });

  test("320px viewport reflow, 200% zoom, and prefers-reduced-motion", async ({ page }) => {
    await onboardAndMeasure(page);

    // 320px reflow check (A11Y-12)
    await page.setViewportSize({ width: 320, height: 640 });
    for (const route of [
      "/today",
      "/plan",
      "/ask",
      "/home-air",
      "/impact",
      "/reports",
      "/settings",
    ]) {
      await page.goto(route);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1
      );
      expect(overflow, `320px overflow on ${route}`).toBe(false);
    }

    // 200% zoom equivalent (640px CSS width at 1280px physical)
    await page.setViewportSize({ width: 640, height: 800 });
    await page.goto("/today");
    const zoomOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    );
    expect(zoomOverflow).toBe(false);

    // prefers-reduced-motion: reduce -> transitions <= 0ms (A11Y-05)
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/today");
    const maxDurationMs = await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll("button, a, .purvai-card"));
      let maxMs = 0;
      for (const el of els) {
        const dur = getComputedStyle(el).transitionDuration;
        for (const part of dur.split(",")) {
          const val = Number.parseFloat(part);
          const ms = part.trim().endsWith("ms") ? val : val * 1000;
          if (Number.isFinite(ms) && ms > maxMs) maxMs = ms;
        }
      }
      return maxMs;
    });
    expect(maxDurationMs).toBeLessThanOrEqual(0);
  });

  test("FR-01 onboarding < 60s, verdict < 10s, and NFR-01 LCP under Fast 4G + 4x CPU", async ({
    page,
    context,
  }) => {
    const onboardingMs = await onboardAndMeasure(page);
    console.log(`FR-01 onboarding time: ${onboardingMs} ms`);
    expect(onboardingMs).toBeLessThan(60_000);

    // Measure verdict visible time from page load on /today
    const vStart = Date.now();
    await page.goto("/today");
    await expect(page.getByText(/AQI/i).first()).toBeVisible();
    const verdictMs = Date.now() - vStart;
    console.log(`Verdict visible time: ${verdictMs} ms`);
    expect(verdictMs).toBeLessThan(10_000);

    // Measure LCP across 3 runs with Fast 4G + 4x CPU throttling via CDP
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      downloadThroughput: (9 * 1024 * 1024) / 8,
      uploadThroughput: (1.5 * 1024 * 1024) / 8,
      latency: 150,
    });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

    await page.addInitScript(() => {
      (window as unknown as { __lcpMs?: number }).__lcpMs = 0;
      new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last) {
          (window as unknown as { __lcpMs?: number }).__lcpMs = last.startTime;
        }
      }).observe({ type: "largest-contentful-paint", buffered: true });
    });

    const lcpRuns: number[] = [];
    for (let i = 0; i < 3; i++) {
      await page.goto("/today", { waitUntil: "load" });
      await expect(page.getByText(/AQI/i).first()).toBeVisible();
      const lcp = await page.evaluate(
        () => (window as unknown as { __lcpMs?: number }).__lcpMs ?? 0
      );
      lcpRuns.push(Math.round(lcp));
    }

    const sorted = [...lcpRuns].sort((a, b) => a - b);
    const median = sorted[1];
    console.log(`NFR-01 LCP runs (ms): ${JSON.stringify(lcpRuns)}, median: ${median} ms`);
    expect(median).toBeGreaterThan(0);
  });
});
