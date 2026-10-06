import { expect, test } from "@playwright/test";

import { expectNoHorizontalOverflow, isMobile, login, USERS, watchForErrors } from "./helpers";

/** Every page each role can reach from the navigation. */
const PAGES: Record<keyof typeof USERS, string[]> = {
  admin: [
    "/admin", "/admin/vendors", "/admin/bookings", "/admin/reports", "/admin/calendar", "/admin/services",
    "/admin/customers", "/admin/vehicles", "/admin/invoices", "/admin/payments", "/admin/users", "/admin/audit-logs",
    "/admin/search?q=MH", "/admin/notifications", "/admin/profile",
  ],
  agency: [
    "/agency", "/agency/bookings", "/agency/calendar", "/agency/job-cards", "/agency/customers", "/agency/vehicles",
    "/agency/inventory", "/agency/invoices", "/agency/payments", "/agency/reports", "/agency/services", "/agency/staff",
    "/agency/settings", "/agency/settings?tab=hours", "/agency/settings?tab=closures", "/agency/settings?tab=resources",
    "/agency/settings?tab=rules", "/agency/audit-logs", "/agency/search?q=MH", "/agency/notifications", "/agency/profile",
  ],
  staff: ["/agency", "/agency/bookings", "/agency/job-cards", "/agency/customers", "/agency/inventory", "/agency/profile"],
  customer: [
    "/customer", "/customer/book", "/customer/bookings", "/customer/vehicles", "/customer/invoices",
    "/customer/notifications", "/customer/profile", "/customer/search?q=MH",
  ],
};

for (const role of Object.keys(PAGES) as (keyof typeof USERS)[]) {
  test(`every ${role} page renders without errors`, async ({ page }) => {
    test.setTimeout(PAGES[role].length * 15_000);
    const problems = watchForErrors(page);
    await login(page, USERS[role]);
    for (const path of PAGES[role]) {
      await test.step(path, async () => {
        await page.goto(path);
        await expect(page.locator("h1").first(), `${path} has a heading`).toBeVisible();
        await expect(page.getByText("Something went wrong")).toHaveCount(0);
        await page.waitForLoadState("networkidle");
        await expect(page.locator(".skeleton").first()).toBeHidden({ timeout: 15_000 });
        if (isMobile(page)) await expectNoHorizontalOverflow(page);
        expect(problems, `errors on ${path}`).toEqual([]);
      });
    }
  });
}

test("dashboard charts render with data", async ({ page }) => {
  await login(page, USERS.agency);
  await expect(page.getByRole("heading", { name: "Revenue" }).first()).toBeVisible();
  await expect(page.locator(".recharts-surface").first()).toBeVisible();
  // The accessible table view of the chart has rows.
  await page.getByRole("button", { name: "Table" }).first().click();
  await expect(page.locator("table tr").first()).toBeVisible();
});

test("calendar shows bookings", async ({ page }) => {
  await login(page, USERS.agency);
  await page.goto("/agency/calendar");
  await expect(page.locator(".fc").first()).toBeVisible();
  await expect(page.locator(".fc-event, .fc-list-event").first()).toBeVisible({ timeout: 15_000 });
});
