import { expect, test } from "@playwright/test";
import { login, resetDemo } from "./helpers";

/** Round 5, second set: tables. */
test("every row of a table lays its columns out like the header, with long text and with row buttons", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  for (const path of ["/library", "/rules", "/audit", "/attribution", "/performance"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const lefts = await page.evaluate(() => [...document.querySelectorAll(".sx-table__head, .sx-table__row")].slice(0, 14).map((r) => [...r.children].map((c) => Math.round(c.getBoundingClientRect().left)).join(",")));
    expect(lefts.length, path).toBeGreaterThan(3);
    expect(new Set(lefts).size, `${path} columns line up: ${[...new Set(lefts)].join(" | ")}`).toBe(1);
  }
});

test("on a phone the row buttons of a table are shown without hovering", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, baseURL: `http://localhost:${process.env.WEB_PORT ?? "3000"}` });
  const page = await ctx.newPage();
  await login(page);
  await page.goto("/library");
  await page.waitForLoadState("networkidle");
  const remove = page.getByRole("button", { name: /^Remove Sample 1:/ });
  await expect(remove).toBeVisible();
  expect(Number(await remove.evaluate((e) => getComputedStyle(e.closest(".sx-table__actions")!).opacity))).toBe(1);
  await ctx.close();
});

test("a table whose rows open nothing does not say enter opens", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  for (const path of ["/library", "/rules", "/performance", "/attribution"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const foot = page.locator(".sx-table__footer > span:last-child").first();
    await expect(foot).toBeVisible();
    expect(await foot.evaluate((e) => getComputedStyle(e, "::after").content), path).toContain("j k move");
    expect(await foot.evaluate((e) => getComputedStyle(e).fontSize), path).toBe("0px");
  }
  await page.goto("/audit");
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".sx-table__footer")).toContainText("enter opens");
});

test("an empty file, a stray word and an unknown file type are refused with a reason, and nothing is added", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/library");
  await page.waitForLoadState("networkidle");
  const choose = page.getByLabel("Choose a file or drop it here");
  await choose.setInputFiles({ name: "empty.txt", mimeType: "text/plain", buffer: Buffer.from("") });
  await expect(page.getByText(/no text in that file, or too little/)).toBeVisible();
  await choose.setInputFiles({ name: "program.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  await expect(page.getByText(/file type is not supported/)).toBeVisible();
  await expect(page.getByText("16 rows")).toBeVisible();
  await expect(page.getByText(/Added \d sample/)).toHaveCount(0);
});

test("the same post numbers imported twice are counted once", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/performance");
  const csv = "impressions,likes,comments,shares,text\n1000,40,3,2,A first imported post about invoices.\n900,30,2,1,A second imported post about reminders.\n";
  for (const [n, expectText] of [[1, "Import 2 posts"], [2, "2 rows are new."]] as const) {
    await page.getByRole("button", { name: "Import a CSV" }).click();
    await page.getByLabel("CSV text").fill(csv);
    await page.getByRole("button", { name: "Check the file" }).click();
    if (n === 1) { await expect(page.getByRole("button", { name: expectText })).toBeVisible(); await page.getByRole("button", { name: expectText }).click(); await expect(page.getByText("Imported.")).toBeVisible(); }
    else { await expect(page.getByText("0 rows are new. 2 already in your numbers, skipped.")).toBeVisible(); await expect(page.getByRole("button", { name: "Import 0 posts" })).toHaveAttribute("aria-disabled", "true"); await page.getByRole("button", { name: "Cancel" }).click(); }
  }
  await expect(page.locator(".sx-stat").filter({ hasText: "Posts" }).locator("[aria-hidden]").first()).toHaveText("62");
});

test("an address that does not exist gives a page with a way back", async ({ page }) => {
  await login(page);
  const r = await page.goto("/no-such-page");
  expect(r?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "That page does not exist" })).toBeVisible();
  await page.getByRole("link", { name: "Go to the Studio" }).click();
  await expect(page.getByRole("heading", { name: "Studio", exact: true })).toBeVisible();
});

test("the demo date in the banner moves forward with +1 day", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  await expect(page.locator(".vp-banner")).toContainText("Demo date: Tue, Dec 1.");
  await page.getByRole("button", { name: "+1 day" }).click();
  await expect(page.locator(".vp-banner")).toContainText("Demo date: Wed, Dec 2.");
  await resetDemo(page);
});

test("the voice page rounds its numbers, and a thumb can hit the note checkboxes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/voice");
  const own = page.getByText(/^Own centre /);
  await expect(own).toBeVisible();
  expect(await own.innerText()).not.toMatch(/\d\.\d{3,}/);
  await page.goto("/");
  const box = await page.getByLabel("Attach note 24").boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(20);
  expect(box!.height).toBeGreaterThanOrEqual(20);
  const row = await page.getByLabel("Attach note 24").locator("xpath=ancestor::label").boundingBox();
  expect(row!.height).toBeGreaterThanOrEqual(32);
});

test("the editor does not appear before its text, so nothing typed early is overwritten", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.route(/\/api\/drafts\/\d+$/, async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.continue(); });
  await page.goto("/");
  await expect(page.getByLabel("Draft text")).toHaveCount(0);
  await expect(page.getByLabel("Draft text")).toBeVisible({ timeout: 8000 });
  const loaded = await page.getByLabel("Draft text").inputValue();
  expect(loaded.length).toBeGreaterThan(20);
  await page.getByLabel("Draft text").press("End");
  await page.keyboard.type(" typed straight away");
  await page.waitForTimeout(1800);
  await expect(page.getByLabel("Draft text")).toHaveValue(loaded + " typed straight away");
});
