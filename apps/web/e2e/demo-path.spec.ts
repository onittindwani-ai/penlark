import { expect, test } from "@playwright/test";
import { call, login, resetDemo, signOut, watch } from "./helpers";

const BAD = "In today's fast-paced world it is important to note that effective communication is a game changer. I grew sales by 300 percent last year.";
const GOOD = "Invoices go out on the day the work ends. Short email. Due date first. A thank you at the end.\n\nI timed it. It works.";

test("the five minute demo path, with no accounts", async ({ page }) => {
  const errors = watch(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  // 1 the live meter answers as you type
  const editor = page.getByLabel("Draft text");
  await expect(page.getByText("Voice match").first()).toBeVisible();
  await editor.fill(BAD);
  await expect(page.getByText("is on the banned list").first()).toBeVisible();
  await expect(page.getByText("Needs a source or a founder fact").first()).toBeVisible();
  const bad = await page.locator(".sx-gauge, [aria-label='Voice match']").first().textContent();
  await editor.fill(GOOD);
  await expect(page.getByText("No rule broken")).toBeVisible();
  expect(await page.locator("[aria-label='Voice match']").first().textContent()).not.toBe(bad);
  // 2 ask for approval, a second person decides
  await page.getByRole("button", { name: "Ask for approval" }).click();
  await expect(page.getByText("Sent for approval").first()).toBeVisible();
  await page.goto("/approvals");
  await expect(page.getByText("Waiting (2)")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText(/someone else must decide/i).first()).toBeVisible(); // the person who asked cannot approve
  await signOut(page);
  await login(page, "approver@example.test");
  await page.goto("/approvals");
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Approved.").first()).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Waiting (0)")).toBeVisible();
  await signOut(page);
  // 3 plan a day on the calendar and export to a file
  await login(page);
  await page.goto("/calendar");
  await expect(page.getByText("Ready to plan")).toBeVisible();
  await expect(page.getByLabel("Posting rhythm")).toContainText("LinkedIn");
  await expect(page.getByLabel("Posting rhythm")).toContainText("of 2");
  const chip = page.locator(".vp-chip-post").first();
  await chip.dragTo(page.locator(".vp-day").nth(3));
  await expect(page.getByText(/Planned on/).first()).toBeVisible();
  await page.goto("/");
  await page.getByLabel("Draft", { exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Export to a file" }).click();
  await expect(page.getByText(/Exported\. Saved to/).first()).toBeVisible();
  // 4 the voice radar, the learning loop, a safe tracked link
  await page.goto("/voice");
  await expect(page.getByRole("img", { name: /Voice fingerprint radar/ })).toBeVisible();
  await page.getByText("Formality", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Formality" })).toBeVisible();
  await page.goto("/performance");
  await expect(page.getByText("too few to say").first()).toBeVisible();
  await page.goto("/attribution");
  await page.getByLabel("Where it points").fill("https://evil.example.org/x");
  await page.getByLabel("Campaign").fill("demo test");
  await page.getByRole("button", { name: "Make the link" }).click();
  await expect(page.getByText(/allow list/i).first()).toBeVisible();
  await page.getByLabel("Where it points").fill("https://larkspur.example.test/start");
  await page.getByRole("button", { name: "Make the link" }).click();
  await expect(page.getByText(/Link made/).first()).toBeVisible();
  const r = await call(page, "/links", { target: "https://larkspur.example.test/x", campaign: "t" });
  const code = (await r.json()).code as string;
  const red = await page.request.get(`/r/${code}`, { maxRedirects: 0 });
  expect(red.status()).toBe(302);
  expect(red.headers()["location"]).toContain("larkspur.example.test");
  expect(errors.filter((e) => !/409|400/.test(e))).toEqual([]);
});
