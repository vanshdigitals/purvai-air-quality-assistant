import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const APP_ROUTES = [
  { path: "/today", heading: "Today" },
  { path: "/plan", heading: "Daily Protection Plan" },
  { path: "/home-air", heading: "Home Air" },
  { path: "/settings", heading: "Settings" },
] as const;

async function ensureHouseholdOnboarded(page: Page) {
  await page.goto("/welcome/location");
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
}

test.describe("Purvai Phase 3 E2E", () => {
  test("first run redirects / to /welcome and onboarding search lands on Today with verdict, AQI, GRAP, and forecast", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page).toHaveURL(/\/welcome$/);

    await page.getByRole("button", { name: "Get started" }).click();
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
    await expect(page.getByText("Stay indoors today. Run the purifier.")).toBeVisible();
    await expect(page.getByLabel("312, Very Poor, CPCB scale, Measured")).toBeVisible();
    await expect(page.getByText(/GRAP Stage II is in force for Delhi NCR/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "12-hour forecast" })).toBeVisible();

    await page.getByRole("button", { name: "Show as table" }).click();
    await expect(page.getByRole("table")).toBeVisible();
  });

  test("deep link serves HTML with CSP headers, /api/v1/unknown returns JSON 404, and unknown web route shows 404 page", async ({
    page,
    request,
  }) => {
    const apiRes = await request.get("/api/v1/health");
    expect(apiRes.status()).toBe(200);
    expect(apiRes.headers()["content-type"]).toContain("application/json");

    const unknownApiRes = await request.get("/api/v1/unknown");
    expect(unknownApiRes.status()).toBe(404);
    expect(unknownApiRes.headers()["content-type"]).toContain("application/json");
    expect(((await unknownApiRes.json()) as { error: { code: string } }).error.code).toBe(
      "NOT_FOUND"
    );

    const deepLinkRes = await request.get("/today");
    expect(deepLinkRes.status()).toBe(200);
    expect(deepLinkRes.headers()["content-type"]).toContain("text/html");
    expect(deepLinkRes.headers()["content-security-policy"]).toContain("default-src 'self'");
    expect(deepLinkRes.headers()["x-content-type-options"]).toBe("nosniff");

    await ensureHouseholdOnboarded(page);
    await page.goto("/non-existent-page");
    await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  });

  test("skip after location saves household and reaches Today", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/welcome/location");
    await page.getByLabel("Search city or neighbourhood").fill("Noida");
    const resultRow = page.getByRole("radio", { name: /Sector 62, Noida/i });
    await expect(resultRow).toBeVisible();
    await resultRow.click();

    await page.getByRole("button", { name: "Skip for now" }).click();
    await expect(page).toHaveURL(/\/today$/);
    await expect(page.getByLabel("312, Very Poor, CPCB scale, Measured")).toBeVisible();
  });

  test("keyboard-only onboarding completes setup from /welcome", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/welcome");
    await expect(page.getByRole("button", { name: "Get started" })).toBeVisible();

    // Tab reaches skip link first
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();

    // Activate Get started via keyboard
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Get started" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/welcome\/location$/);

    const searchInput = page.getByLabel("Search city or neighbourhood");
    await searchInput.focus();
    await page.keyboard.type("Noida");
    const resultRow = page.getByRole("radio", { name: /Sector 62, Noida/i });
    await expect(resultRow).toBeVisible();
    await resultRow.focus();
    await page.keyboard.press("Enter");

    const continueBtn = page.getByRole("button", { name: "Continue" });
    await continueBtn.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/welcome\/household$/);

    await page.getByRole("checkbox", { name: /Child under 12/i }).focus();
    await page.keyboard.press("Space");
    await page.getByRole("button", { name: "Continue" }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/welcome\/commute$/);

    await page.getByRole("radio", { name: "Metro" }).focus();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Finish setup" }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/today$/);
  });

  test("plan shows 4 periods and toggles Today and Tomorrow", async ({ page }) => {
    await ensureHouseholdOnboarded(page);
    await page.getByRole("link", { name: "Plan my day" }).click();
    await expect(page).toHaveURL(/\/plan$/);
    await expect(page.getByText("Morning")).toBeVisible();
    await expect(page.getByText("Afternoon")).toBeVisible();
    await expect(page.getByText("Evening")).toBeVisible();
    await expect(page.getByText("Night")).toBeVisible();

    await page.getByRole("radio", { name: "Tomorrow" }).click();
    await expect(
      page.getByText(/Tomorrow's plan uses Open-Meteo CAMS hourly forecast data/i)
    ).toBeVisible();
  });

  test("Home Air calculator computes 8.5 ACH and shows target badge", async ({ page }) => {
    await ensureHouseholdOnboarded(page);
    await page.goto("/home-air");
    await page.getByRole("button", { name: "Calculate ACH" }).click();
    await expect(page.getByText("8.5")).toBeVisible();
    await expect(page.getByText("Meets target")).toBeVisible();
  });

  test("theme persists after reload through PUT /household", async ({ page }) => {
    await ensureHouseholdOnboarded(page);
    await page.goto("/settings");

    const putPromise = page.waitForResponse(
      (res) => res.url().includes("/api/v1/household") && res.request().method() === "PUT"
    );
    await page.getByRole("radio", { name: "Dark" }).click();
    const putRes = await putPromise;
    expect(putRes.status()).toBe(200);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  test("mobile menu opens Reports & Data and Settings at 375x812", async ({ page }) => {
    await ensureHouseholdOnboarded(page);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/today");
    await page.getByRole("button", { name: "Reports and settings menu" }).click();
    const menu = page.getByRole("navigation", { name: "Account and workspace" });
    await expect(menu.getByRole("link", { name: "Reports & Data" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Settings" })).toBeVisible();
  });

  test("layouts at 375x812 and 1280x800 fit without horizontal overflow", async ({ page }) => {
    await ensureHouseholdOnboarded(page);
    for (const viewport of [
      { width: 375, height: 812 },
      { width: 1280, height: 800 },
    ]) {
      await page.setViewportSize(viewport);
      for (const route of APP_ROUTES) {
        await page.goto(route.path);
        await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth
        );
        expect(overflow, `Overflow at ${viewport.width}px on ${route.path}`).toBe(false);
      }
    }
  });

  test("axe finds zero serious or critical issues on all screens in light and dark themes", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/welcome");
    for (const stepPath of ["/welcome", "/welcome/location"]) {
      await page.goto(stepPath);
      const res = await new AxeBuilder({ page }).analyze();
      expect(
        res.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
        `Axe violations on ${stepPath}`
      ).toEqual([]);
    }

    await ensureHouseholdOnboarded(page);

    for (const themeLabel of ["Light", "Dark"] as const) {
      await page.goto("/settings");
      await page.getByRole("radio", { name: themeLabel }).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", themeLabel.toLowerCase());
      for (const route of APP_ROUTES) {
        await page.goto(route.path);
        await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
        const res = await new AxeBuilder({ page }).analyze();
        expect(
          res.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
          `${themeLabel} axe violations on ${route.path}`
        ).toEqual([]);
      }
    }
  });
});
