import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const APP_ROUTES = [
  { path: "/today", heading: "Today" },
  { path: "/plan", heading: "Daily Protection Plan" },
  { path: "/home-air", heading: "Home Air" },
  { path: "/settings", heading: "Settings" },
] as const;

test.describe("Purvai Phase 3 E2E", () => {
  test("API separation, keyboard onboarding, Today, Plan, Home Air, theme persistence, and axe", async ({
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

    // 1. First run redirects / -> /welcome and checks axe on welcome screen
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Clear air-safety actions for your household" })
    ).toBeVisible();

    const welcomeAxe = await new AxeBuilder({ page }).analyze();
    expect(
      welcomeAxe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
    ).toEqual([]);

    // Keyboard check: Tab reaches skip link first
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();

    // Advance via keyboard/button to location step
    await page.getByRole("button", { name: "Get started" }).click();
    await expect(page).toHaveURL(/\/welcome\/location$/);

    const locAxe = await new AxeBuilder({ page }).analyze();
    expect(
      locAxe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
    ).toEqual([]);

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

    // 2. Today screen: verdict, AQI, GRAP, actions, forecast + table toggle
    await expect(page).toHaveURL(/\/today$/);
    await expect(page.getByText("Stay indoors today. Run the purifier.")).toBeVisible();
    await expect(page.getByLabel("312, Very Poor, CPCB scale, Measured")).toBeVisible();
    await expect(page.getByText(/GRAP Stage II is in force for Delhi NCR/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "12-hour forecast" })).toBeVisible();

    await page.getByRole("button", { name: "Show as table" }).click();
    await expect(page.getByRole("table")).toBeVisible();

    // 3. Daily Protection Plan opens with 4 periods
    await page.getByRole("link", { name: "Plan my day" }).click();
    await expect(page).toHaveURL(/\/plan$/);
    await expect(page.getByText("Morning")).toBeVisible();
    await expect(page.getByText("Afternoon")).toBeVisible();
    await expect(page.getByText("Evening")).toBeVisible();
    await expect(page.getByText("Night")).toBeVisible();

    // 4. Home Air calculator shows 8.5 ACH
    await page.goto("/home-air");
    await page.getByRole("button", { name: "Calculate ACH" }).click();
    await expect(page.getByText("8.5")).toBeVisible();
    await expect(page.getByText("Meets target")).toBeVisible();

    // 5. Light & Dark theme toggle, persistence across reload, and axe audit on all new screens
    await page.goto("/settings");
    await page.getByRole("radio", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    for (const route of APP_ROUTES) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
      const results = await new AxeBuilder({ page }).analyze();
      expect(
        results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
        `Light axe violations on ${route.path}`
      ).toEqual([]);
    }

    await page.goto("/settings");
    await page.getByRole("radio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    for (const route of APP_ROUTES) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
      const results = await new AxeBuilder({ page }).analyze();
      expect(
        results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
        `Dark axe violations on ${route.path}`
      ).toEqual([]);
    }

    // 6. Mobile layout (375x812) + mobile menu
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/today");
    await expect(page.getByText("Stay indoors today. Run the purifier.")).toBeVisible();
    await page.getByRole("button", { name: "Reports and settings menu" }).click();
    const menu = page.getByRole("navigation", { name: "Account and workspace" });
    await expect(menu.getByRole("link", { name: "Reports & Data" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Settings" })).toBeVisible();
  });
});
