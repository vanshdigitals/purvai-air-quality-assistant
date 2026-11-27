import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const ROUTES = [
  { path: "/today", heading: "Today" },
  { path: "/ask", heading: "Ask Purvai" },
  { path: "/home-air", heading: "Home Air" },
  { path: "/impact", heading: "Impact" },
  { path: "/reports", heading: "Reports & Data" },
  { path: "/settings", heading: "Settings" },
] as const;

test.describe("Purvai Phase 1 E2E", () => {
  test("redirects / to /today, connects to API, and navigates all routes", async ({
    page,
    request,
  }) => {
    const apiRes = await request.get("/api/v1/health");
    expect(apiRes.status()).toBe(200);
    expect(apiRes.headers()["content-type"]).toContain("application/json");
    const healthJson = (await apiRes.json()) as {
      status: string;
      mode: string;
    };
    expect(healthJson.status).toBe("ok");

    const unknownApiRes = await request.get("/api/v1/unknown");
    expect(unknownApiRes.status()).toBe(404);
    expect(unknownApiRes.headers()["content-type"]).toContain("application/json");
    const unknownBody = (await unknownApiRes.json()) as { error: { code: string } };
    expect(unknownBody.error.code).toBe("NOT_FOUND");

    const deepLinkRes = await request.get("/today");
    expect(deepLinkRes.status()).toBe(200);
    expect(deepLinkRes.headers()["content-type"]).toContain("text/html");
    expect(deepLinkRes.headers()["content-security-policy"]).toContain("default-src 'self'");
    expect(deepLinkRes.headers()["x-content-type-options"]).toBe("nosniff");

    await page.goto("/");
    await expect(page).toHaveURL(/\/today$/);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.getByText("API connected")).toBeVisible();

    for (const route of ROUTES) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
    }
  });

  test("keyboard navigation reaches skip link first, shows focus-visible ring, and hover adds no ring", async ({
    page,
  }) => {
    await page.goto("/today");
    await expect(page.getByText("API connected")).toBeVisible();

    await page.keyboard.press("Tab");
    const skipLink = page.getByRole("link", { name: "Skip to main content" });
    await expect(skipLink).toBeFocused();

    await page.keyboard.press("Tab");
    const focusedNavLink = page.locator("aside nav a:focus-visible").first();
    await expect(focusedNavLink).toBeVisible();
    const focusStyle = await focusedNavLink.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return {
        outlineWidth: style.outlineWidth,
        outlineStyle: style.outlineStyle,
      };
    });
    expect(focusStyle.outlineWidth).toBe("2px");
    expect(focusStyle.outlineStyle).toBe("solid");

    const askLink = page.locator('aside nav a[href="/ask"]');
    await askLink.hover();
    const hoverStyle = await askLink.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return {
        outlineStyle: style.outlineStyle,
        borderTopWidth: style.borderTopWidth,
      };
    });
    expect(hoverStyle.outlineStyle).toBe("none");
    expect(hoverStyle.borderTopWidth).toBe("0px");
  });

  test("toggles dark theme in Settings and passes axe across all routes in light and dark modes", async ({
    page,
  }) => {
    // Light mode axe audit
    await page.goto("/settings");
    await page.getByRole("radio", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    for (const route of ROUTES) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
      const results = await new AxeBuilder({ page }).analyze();
      const seriousOrCritical = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical"
      );
      expect(seriousOrCritical, `Light axe violations on ${route.path}`).toEqual([]);
    }

    // Dark mode toggle + reload persistence + axe audit
    await page.goto("/settings");
    await page.getByRole("radio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    for (const route of ROUTES) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
      const results = await new AxeBuilder({ page }).analyze();
      const seriousOrCritical = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical"
      );
      expect(seriousOrCritical, `Dark axe violations on ${route.path}`).toEqual([]);
    }
  });

  test("mobile viewport opens profile menu to reach Reports & Data and Settings", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/today");

    await page.getByRole("button", { name: "Reports and settings menu" }).click();
    const menu = page.getByRole("navigation", { name: "Account and workspace" });
    await expect(menu.getByRole("link", { name: "Reports & Data" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Settings" })).toBeVisible();
    await menu.getByRole("link", { name: "Reports & Data" }).click();
    await expect(page).toHaveURL(/\/reports$/);
    await expect(page.getByRole("heading", { level: 1, name: "Reports & Data" })).toBeVisible();
  });
});
