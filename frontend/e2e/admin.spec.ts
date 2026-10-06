import { expect, test } from "@playwright/test";

import { login, USERS, watchForErrors } from "./helpers";

test.describe.configure({ mode: "serial" });

test("super admin approves a pending agency", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "approval changes data — run once");
  const problems = watchForErrors(page);
  await login(page, USERS.admin);
  await page.goto("/admin/vendors?status=PENDING");
  const row = page.locator("tr", { hasText: "Royal Bikes Workshop" });
  await row.getByRole("button", { name: "Approve" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/Royal Bikes Workshop: approve successful/)).toBeVisible();
  expect(problems).toEqual([]);
});

test("reports run, filter and export", async ({ page }) => {
  await login(page, USERS.admin);
  await page.goto("/admin/reports");
  await expect(page.locator("table").first()).toBeVisible({ timeout: 15_000 });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
});

test("global search finds a vehicle by registration", async ({ page }) => {
  await login(page, USERS.agency);
  await page.goto("/agency/search");
  await page.getByPlaceholder(/Try MH12/).fill("MH12DM");
  await expect(page.getByText(/MH12DM\d+/).first()).toBeVisible();
});

test("agency admin adds a staff member", async ({ page }, info) => {
  await login(page, USERS.agency);
  await page.goto("/agency/staff");
  await page.getByRole("button", { name: "Add member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("E-mail").fill(`tech-${info.project.name}-${Date.now()}@example.com`);
  await dialog.getByLabel("Full name").fill("E2E Technician");
  await dialog.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText(/Invitation sent to/)).toBeVisible();
});
