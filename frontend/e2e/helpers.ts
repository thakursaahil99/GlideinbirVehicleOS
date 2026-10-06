import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Demo@12345";
export const USERS = {
  admin: "superadmin@demo.local",
  agency: "admin@speedy-auto-care.demo.local",
  staff: "staff@speedy-auto-care.demo.local",
  customer: "customer01@demo.local",
} as const;

export async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** Fail the test on uncaught JS errors or any 5xx from the API. */
export function watchForErrors(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (err) => problems.push(`JS error: ${err.message}`));
  page.on("response", (res) => {
    if (res.url().includes("/api/") && res.status() >= 500) problems.push(`HTTP ${res.status()} ${res.url()}`);
  });
  return problems;
}

/** No sideways scrolling on phones. */
export async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page scrolls horizontally").toBeLessThanOrEqual(1);
}

export const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1440) < 640;
