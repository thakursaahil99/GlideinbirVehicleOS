import { expect, test } from "@playwright/test";

import { isMobile, login, USERS, watchForErrors } from "./helpers";

test.describe("authentication & role routing", () => {
  for (const [role, email, home] of [
    ["super admin", USERS.admin, "/admin"],
    ["agency admin", USERS.agency, "/agency"],
    ["customer", USERS.customer, "/customer"],
  ] as const) {
    test(`${role} lands on ${home}`, async ({ page }) => {
      const problems = watchForErrors(page);
      await login(page, email);
      await expect(page).toHaveURL(new RegExp(`${home}$`));
      await expect(page.locator("h1").first()).toBeVisible();
      expect(problems).toEqual([]);
    });
  }

  test("wrong password shows an error and stays on login", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("E-mail").fill(USERS.customer);
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Invalid email or password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("customers are kept out of other areas", async ({ page }) => {
    await login(page, USERS.customer);
    await page.goto("/admin/vendors");
    await expect(page).toHaveURL(/\/forbidden/);
    await page.goto("/agency/bookings");
    await expect(page).toHaveURL(/\/forbidden/);
  });

  test("signed-out users are sent to login", async ({ page }) => {
    await page.goto("/agency/bookings");
    await expect(page).toHaveURL(/\/login/);
  });

  test("log out ends the session", async ({ page }) => {
    await login(page, USERS.agency);
    if (isMobile(page)) await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("button", { name: "Log out" }).locator("visible=true").first().click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/agency");
    await expect(page).toHaveURL(/\/login/);
  });

  test("customer can register a new account", async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`;
    await page.goto("/register");
    await page.getByLabel("Full name").fill("E2E Tester");
    await page.getByLabel("E-mail").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("Str0ng!Passw0rd");
    await page.getByLabel("Confirm password").fill("Str0ng!Passw0rd");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/customer$/);
  });
});
