import { expect, test } from "@playwright/test";

import { login, USERS, watchForErrors } from "./helpers";

test("agency adds a scooter model, sells one, and sees who bought it", async ({ page }, info) => {
  const problems = watchForErrors(page);
  const name = `Jupiter ${info.project.name} ${Date.now() % 100000}`;
  await login(page, USERS.agency);
  await page.goto("/agency/showroom");
  await page.getByRole("button", { name: "New model" }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Brand").fill("TVS");
  await dialog.getByLabel("Model name").fill(name);
  await dialog.getByLabel("Ex-showroom price (₹)").fill("89000");
  await dialog.getByLabel("Units in stock").fill("3");
  await dialog.getByRole("button", { name: "Add model" }).click();
  await expect(page.getByText("Model added.")).toBeVisible();

  await page.getByPlaceholder(/Search brand/).fill(name);
  await page.getByRole("button", { name: "Sell" }).first().click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Buyer name").fill("Ravi Kumar");
  await dialog.getByLabel("Buyer phone").fill("+919811122233");
  await dialog.getByLabel("Chassis no.").fill("MD626TEST1");
  await dialog.getByRole("button", { name: "Record sale" }).click();
  await expect(page.getByText("Sale recorded — stock updated.")).toBeVisible();

  await page.getByRole("button", { name: "Sales" }).click();
  await page.getByPlaceholder(/Search buyer/).fill("MD626TEST1");
  await expect(page.getByText("Ravi Kumar").filter({ visible: true }).first()).toBeVisible();
  expect(problems).toEqual([]);
});
