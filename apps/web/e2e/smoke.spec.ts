import { expect, test } from "@playwright/test";
import { PAGES, login, resetDemo, watch } from "./helpers";

test("every page loads without console errors", async ({ page }) => {
  const errors = watch(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  for (const p of PAGES) {
    await page.goto(p);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1").first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});
