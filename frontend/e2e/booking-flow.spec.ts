/**
 * The core business flow, across three accounts in real browsers:
 * customer books → agency confirms, receives the vehicle and works the job card →
 * completion issues the invoice → customer pays online → it shows as paid everywhere.
 */
import { expect, test, type Page } from "@playwright/test";

import { expectNoHorizontalOverflow, isMobile, login, USERS, watchForErrors } from "./helpers";

test.describe.configure({ mode: "serial" });

let bookingPath = ""; // /customer/bookings/<id>
let bookingId = "";

async function confirmDialog(page: Page, label: string) {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: label, exact: true }).click();
  await expect(dialog).toBeHidden();
}

test("customer books a service through the wizard", async ({ page }) => {
  const problems = watchForErrors(page);
  await login(page, USERS.customer);
  await page.goto("/customer/book");

  // 1. Vehicle → 2. Service → 3. Workshop (price comparison)
  await page.getByRole("button", { name: /Maruti Suzuki Swift/ }).click();
  await page.getByRole("button", { name: /General Service/ }).click();
  await expect(page.getByRole("heading", { name: "Compare workshops" })).toBeVisible();
  await page.getByRole("button", { name: /Speedy Auto Care/ }).click();

  // 4. Day → 5. Time → 6. Review → confirm. Like a real user, pick another slot if the API says
  // this one clashes (the demo seed already books some vehicles).
  await expect(page.getByRole("heading", { name: "Pick a day" })).toBeVisible();
  const done = page.getByRole("heading", { name: /Booking (received|confirmed)!/ });
  for (let attempt = 0; attempt < 6 && !(await done.isVisible()); attempt++) {
    if (await page.getByRole("heading", { name: "Pick a day" }).isVisible()) {
      await page.getByRole("button", { name: /\d+ free/ }).nth(attempt + 1).click();
    }
    await expect(page.getByRole("heading", { name: /Pick a time/ })).toBeVisible();
    await page.locator("section button:enabled").filter({ hasText: /\d{1,2}:\d{2}/ }).nth(attempt % 2).click();
    await expect(page.getByText("Review your booking")).toBeVisible();
    await page.getByLabel(/Anything the workshop should know/).fill("Brakes squeak (e2e)");
    if (isMobile(page)) await expectNoHorizontalOverflow(page);
    await page.getByRole("button", { name: "Confirm booking" }).click();
    await Promise.race([
      done.waitFor({ timeout: 10_000 }),
      page.getByRole("heading", { name: /Pick a time/ }).waitFor({ timeout: 10_000 }),
    ]).catch(() => undefined);
    if (!(await done.isVisible()) && (await page.getByRole("heading", { name: /Pick a time/ }).isVisible())) {
      await page.getByRole("button", { name: "Back" }).click(); // back to the day list for the next attempt
    }
  }
  await expect(done).toBeVisible();
  await page.getByRole("button", { name: "View booking" }).click();
  await expect(page).toHaveURL(/\/customer\/bookings\/[0-9a-f-]+$/);
  bookingPath = new URL(page.url()).pathname;
  bookingId = bookingPath.split("/").pop()!;
  await expect(page.getByText("Brakes squeak (e2e)")).toBeVisible();
  expect(problems).toEqual([]);
});

test("agency confirms, receives the vehicle and completes the job card", async ({ page }) => {
  test.skip(!bookingId, "booking step failed");
  const problems = watchForErrors(page);
  await login(page, USERS.agency);
  await page.goto(`/agency/bookings/${bookingId}`);

  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await confirmDialog(page, "Confirm");
  await expect(page.getByText(/^confirmed$/i).first()).toBeVisible();

  await page.getByRole("button", { name: "Vehicle received" }).click();
  await confirmDialog(page, "Vehicle received");
  await page.getByRole("link", { name: "Job card", exact: true }).click();
  await expect(page).toHaveURL(/\/agency\/job-cards\//);

  // Inspection checklist + start work
  await page.getByRole("button", { name: "OK", exact: true }).first().click();
  await page.getByRole("button", { name: "Save", exact: true }).first().click();
  await page.getByRole("button", { name: "Start work" }).click();
  await expect(page.getByText(/^work in progress$/i).first()).toBeVisible();

  // Use a part from inventory
  await page.getByRole("button", { name: "Add part" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Part").selectOption({ index: 1 });
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(/× ₹/).first()).toBeVisible();

  // Complete → booking completed, invoice generated
  await page.getByRole("button", { name: "Complete job" }).click();
  await confirmDialog(page, "Complete");
  await expect(page.getByText(/^completed$/i).first()).toBeVisible();

  await page.goto(`/agency/bookings/${bookingId}`);
  await expect(page.getByRole("link", { name: "Invoice", exact: true })).toBeVisible({ timeout: 15_000 });
  expect(problems).toEqual([]);
});

test("customer pays the invoice online and sees it as paid", async ({ page }) => {
  test.skip(!bookingId, "booking step failed");
  const problems = watchForErrors(page);
  await login(page, USERS.customer);
  await page.goto(bookingPath);
  await page.getByRole("link", { name: "Invoice", exact: true }).click();
  await expect(page).toHaveURL(/\/customer\/invoices\//);
  await expect(page.getByText("General Service").first()).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/^INV-\d{4}-\d{6}\.pdf$/);

  await page.getByRole("button", { name: /via UPI/ }).click();
  await expect(page.getByText(/Payment successful/)).toBeVisible();
  await expect(page.getByText(/^paid$/i).first()).toBeVisible();
  if (isMobile(page)) await expectNoHorizontalOverflow(page);

  // The customer's notifications reflect the journey.
  await page.goto("/customer/notifications");
  await expect(page.getByText("Payment received").first()).toBeVisible();
  expect(problems).toEqual([]);
});

test("customer can cancel an upcoming booking with a reason", async ({ page }) => {
  await login(page, USERS.customer);
  await page.goto("/customer/bookings");
  const upcoming = page.locator("tbody tr").filter({ hasText: /Pending|Confirmed/ }).first().getByRole("link").first();
  await upcoming.click();
  await page.getByRole("button", { name: "Cancel booking" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Reason/).fill("Plans changed (e2e)");
  await dialog.getByRole("button", { name: "Cancel booking" }).click();
  await expect(page.getByText(/Cancelled .*Plans changed \(e2e\)/)).toBeVisible();
});
