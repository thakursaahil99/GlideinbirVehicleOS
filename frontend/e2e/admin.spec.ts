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

test("agency admin adds a staff member with a password who can sign in", async ({ page, browser }, info) => {
  const email = `mech-${info.project.name}-${Date.now()}@example.com`;
  await login(page, USERS.agency);
  await page.goto("/agency/staff");
  await page.getByRole("button", { name: "Add member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("E-mail").fill(email);
  await dialog.getByLabel("Full name").fill("E2E Mechanic");
  await dialog.getByLabel("Password (optional)").fill("Mech@Pass2026");
  await dialog.getByRole("button", { name: "Create member" }).click();
  await expect(page.getByText(`${email} can now sign in.`)).toBeVisible();

  const fresh = await browser.newPage({ baseURL: info.project.use.baseURL });
  await login(fresh, email, "Mech@Pass2026");
  await fresh.close();
});

test("super admin creates an agency, then a user inside it", async ({ page, browser }, info) => {
  const problems = watchForErrors(page);
  const tag = `${info.project.name}-${Date.now()}`;
  const agency = `E2E Motors ${tag}`;
  await login(page, USERS.admin);

  await page.goto("/admin/vendors");
  await page.getByRole("button", { name: "New agency" }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Agency name").fill(agency);
  await dialog.getByLabel("Business e-mail").fill(`shop-${tag}@example.com`);
  await dialog.getByLabel("Phone", { exact: true }).fill("+919812345678");
  await dialog.getByLabel("City").fill("Pune");
  await dialog.getByLabel("Admin full name").fill("E2E Owner");
  await dialog.getByLabel("Admin e-mail").fill(`owner-${tag}@example.com`);
  await dialog.getByLabel("Admin password (optional)").fill("Owner@Pass2026");
  await dialog.getByRole("button", { name: "Create agency" }).click();
  await expect(page.getByText(`${agency} is live.`, { exact: false })).toBeVisible();

  await page.goto("/admin/users");
  await page.getByRole("button", { name: "New user" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Role").selectOption("AGENCY_MANAGER");
  await dialog.getByLabel("Agency").selectOption({ label: `${agency} · Pune` });
  await dialog.getByLabel("Full name").fill("E2E Manager");
  await dialog.getByLabel("E-mail").fill(`mgr-${tag}@example.com`);
  await dialog.getByLabel("Password (optional)").fill("Manager@Pass2026");
  await dialog.getByRole("button", { name: "Create user" }).click();
  await expect(page.getByText(`mgr-${tag}@example.com can now sign in.`)).toBeVisible();
  expect(problems).toEqual([]);

  for (const [email, password] of [[`owner-${tag}@example.com`, "Owner@Pass2026"], [`mgr-${tag}@example.com`, "Manager@Pass2026"]]) {
    const fresh = await browser.newPage({ baseURL: info.project.use.baseURL });
    await login(fresh, email, password);
    await fresh.close();
  }
});
