import fs from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function onboard(page: Page) {
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

test.describe("Purvai Phase 5 E2E", () => {
  test("logs a trip on /impact and displays updated CO2 totals", async ({ page }) => {
    await onboard(page);
    await page.goto("/impact");
    await expect(page.getByRole("heading", { name: /Impact/i })).toBeVisible();

    await page.getByLabel("Distance (km)").fill("10");
    await page.getByRole("button", { name: "Log trip" }).click();

    await expect(page.getByText("1.38 kg")).toBeVisible();
    await page.getByRole("button", { name: "Table view" }).click();
    await expect(page.getByText("1380 g")).toBeVisible();
  });

  test("downloads PDF and CSV, backs up and restores, exports/clears/imports JSON, and passes axe", async ({
    page,
  }, testInfo) => {
    await onboard(page);
    await page.goto("/impact");
    await page.getByLabel("Distance (km)").fill("10");
    await page.getByRole("button", { name: "Log trip" }).click();
    await expect(page.getByText("1.38 kg")).toBeVisible();

    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: /Reports & Data/i })).toBeVisible();

    // PDF download
    const [pdfDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download PDF" }).click(),
    ]);
    const pdfPath = testInfo.outputPath("report.pdf");
    await pdfDownload.saveAs(pdfPath);
    const pdfBytes = fs.readFileSync(pdfPath);
    expect(pdfBytes.subarray(0, 5).toString("ascii")).toBe("%PDF-");

    // CSV download
    const [csvDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download CSV" }).click(),
    ]);
    const csvPath = testInfo.outputPath("report.csv");
    await csvDownload.saveAs(csvPath);
    const csvText = fs.readFileSync(csvPath, "utf-8");
    expect(csvText).toContain("Purvai Activity Log Export");

    // Backup & restore in local mode
    await page.getByRole("button", { name: "Create backup" }).click();
    await expect(page.getByText(/Backup created:/i)).toBeVisible();
    await page.getByRole("button", { name: "Restore" }).first().click();
    await expect(page.getByText(/Restored database from/i)).toBeVisible();

    // Export JSON
    const [jsonDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Export JSON" }).click(),
    ]);
    const jsonPath = path.join(testInfo.outputDir, "export.json");
    await jsonDownload.saveAs(jsonPath);

    const exported = JSON.parse(fs.readFileSync(jsonPath, "utf-8")) as {
      household: { members: unknown[]; locations: unknown[] };
      activities: unknown[];
    };
    const mCount = exported.household.members.length;
    const lCount = exported.household.locations.length;
    const aCount = exported.activities.length;

    // Keyboard-only clear-data flow
    const deleteBtn = page.getByRole("button", { name: "Delete all household data" });
    await deleteBtn.focus();
    await page.keyboard.press("Enter");
    const confirmInput = page.getByLabel("Type DELETE to confirm");
    await expect(confirmInput)
      .toBeFocused()
      .catch(() => undefined);
    await confirmInput.fill("DELETE");
    const confirmBtn = page.getByRole("button", { name: "Confirm delete all data" });
    await expect(confirmBtn).toBeEnabled();
    await confirmBtn.click();
    await expect(page.getByText(/All household data deleted/i)).toBeVisible();

    // Navigate back to /reports (deleting household may redirect to /welcome) and import exported JSON
    await page.goto("/reports");
    await page.getByLabel("Choose JSON export file").setInputFiles(jsonPath);
    await expect(
      page.getByText(
        new RegExp(
          `Dry-run preview: ${mCount} member groups, ${lCount} locations, ${aCount} activities`,
          "i"
        )
      )
    ).toBeVisible();
    await page.getByRole("button", { name: "Confirm replace import" }).click();
    await expect(
      page.getByText(
        new RegExp(`Imported ${mCount} members, ${lCount} locations, ${aCount} activities`, "i")
      )
    ).toBeVisible();

    // Axe on /impact and /reports in light and dark themes
    for (const theme of ["light", "dark"] as const) {
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
      for (const route of ["/impact", "/reports"]) {
        await page.goto(route);
        const results = await new AxeBuilder({ page }).analyze();
        const seriousOrCritical = results.violations.filter(
          (v) => v.impact === "serious" || v.impact === "critical"
        );
        expect(seriousOrCritical, `${route} (${theme})`).toEqual([]);
      }
    }
  });
});
