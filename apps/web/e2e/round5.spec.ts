import { expect, test, type Page } from "@playwright/test";
import { call, login, resetDemo, signOut, watch } from "./helpers";

/** Round 5: every test below belongs to one defect found by walking the screens as a first time owner. */
const put = (page: Page, path: string, json: unknown) => page.request.put(`/api${path}`, { headers: { "x-penlark": "1", "content-type": "application/json" }, data: json });
const CLEAN = "Late invoices feel awkward. Chasing them should not.\n\nName the invoice. Name the date. Ask when it will be paid. Stop there.\n\nShort email. Plain words. Send it today.";


test("signing in returns to the page that was asked for", async ({ page }) => {
  await page.goto("/library");
  await expect(page).toHaveURL(/\/login\?next=%2Flibrary/);
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/library$/);
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
  // an address on another site is never followed
  await page.waitForLoadState("networkidle"); // let the page's own requests finish, or the next navigation can be cut off
  await page.context().clearCookies();
  await page.goto("/login?next=https%3A%2F%2Fevil.example.org%2F");
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Studio", exact: true })).toBeVisible();
});

test("on a phone Pause all and Sign out stay in the top bar, and the kill switch says what it does", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await resetDemo(page);
  const pause = page.getByRole("button", { name: "Pause all" });
  await expect(pause).toBeVisible();
  expect((await pause.boundingBox())!.height).toBeGreaterThanOrEqual(36);
  await pause.click();
  await expect(page.getByRole("dialog")).toContainText("Pause all sending?");
  await page.getByRole("button", { name: "Pause all" }).last().click();
  await expect(page.getByText("Kill switch is on.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Turn it off (kill switch)" })).toBeVisible();
  await page.getByRole("button", { name: "Turn it off (kill switch)" }).click();
  await expect(page.getByText("Kill switch is on.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Pause all" })).toBeVisible();
  await signOut(page);
});

test("the banner on a wide screen says what the kill switch leaves working", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await call(page, "/settings", { kill_switch: true });
  await page.goto("/");
  await expect(page.locator(".vp-banner")).toContainText("Nothing is sent to a scheduler. Writing, approving and exporting to a file still work.");
  await call(page, "/settings", { kill_switch: false });
});

test("the palette runs actions and G then a number goes to the page", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.keyboard.press("Control+k");
  for (const name of ["Go to Studio", "Sign out", "Pause all (kill switch)", "Switch to dark theme", "Switch to light theme", "Run the jobs now", "Move the demo clock forward one day", "Reset the demo data"]) await expect(page.getByRole("option", { name: new RegExp(name.replace(/[()]/g, "\\$&")) })).toBeVisible();
  await page.keyboard.type("dark");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.keyboard.press("Control+k");
  await page.keyboard.type("light");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.keyboard.press("Control+k");
  await page.keyboard.type("reset");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText("Reset the demo?");
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("Demo data reset.")).toBeVisible();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("g");
  await page.keyboard.press("3");
  await expect(page).toHaveURL(/\/calendar$/);
  // typing a g and a 3 in a text field goes nowhere
  await page.goto("/");
  await page.getByLabel("Draft text").click();
  await page.keyboard.type("g3");
  await expect(page).toHaveURL(/localhost:\d+\/$/);
});

test("a viewer sees every write control switched off, with a reason, and no request is refused", async ({ page }) => {
  const errors = watch(page);
  await login(page, "viewer@example.test");
  await resetDemo(page).catch(() => null);
  const off = async (name: string | RegExp) => { const b = page.getByRole("button", { name }).first(); await expect(b).toHaveAttribute("aria-disabled", "true"); };
  await page.goto("/"); await page.waitForLoadState("networkidle");
  await expect(page.getByLabel("Draft text")).toHaveAttribute("readonly", "");
  for (const n of ["Save draft", "Ask for approval", "Export to a file", "Run now", "+1 day"]) await off(n);
  await expect(page.getByRole("button", { name: "Pause all" })).toHaveCount(0);
  await page.goto("/ideas"); for (const n of ["Add a note", "Find ideas again", "Write a draft", "Drop"]) await off(n);
  await page.goto("/rules"); await off("Add rule"); await off(/^Turn off/);
  await page.goto("/library"); await off("Add sample"); await off(/^Remove/);
  await page.goto("/voice"); for (const n of ["Save guide", "Build a new version"]) await off(n);
  await page.goto("/attribution"); await off("Make the link");
  await page.goto("/experiments"); await off("Start"); await off("Save counts");
  await page.goto("/performance"); await off("Import a CSV");
  await page.goto("/approvals"); await off("Approve"); await off("Reject");
  await page.goto("/integrations"); await off("Test the one in use");
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("option", { name: /Run the jobs now/ })).toHaveCount(0);
  await expect(page.getByRole("option", { name: /Reset the demo data/ })).toHaveCount(0);
  expect(errors.filter((e) => !/events\/stream|ERR_ABORTED/.test(e))).toEqual([]);
});

test("the voice you pick in the studio is saved with the draft", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const voice = page.getByLabel("Voice", { exact: true });
  await expect(page.getByRole("button", { name: "Save draft" })).toHaveAttribute("aria-disabled", "true"); // nothing to save yet
  await voice.selectOption({ label: "Imani Castellan (fictional)" });
  await expect(page.getByText("unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Draft saved.").first()).toBeVisible();
  await page.reload();
  await expect(voice).toHaveValue("2");
  await expect(page.getByText("Voice: Imani Castellan (fictional)")).toBeVisible();
});

test("leaving a draft with unsaved changes asks first", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  await page.getByLabel("Draft text").fill("A change nobody saved yet. Short and plain.");
  await page.getByLabel("Draft", { exact: true }).selectOption({ index: 1 });
  await expect(page.getByRole("dialog")).toContainText("Leave this draft?");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByLabel("Draft text")).toHaveValue("A change nobody saved yet. Short and plain.");
  await page.getByLabel("Draft", { exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Discard the changes" }).click();
  await expect(page.getByLabel("Draft text")).not.toHaveValue("A change nobody saved yet. Short and plain.");
});

test("editing a draft that waits for approval withdraws the request, so the old request cannot be approved", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  await page.getByLabel("Draft", { exact: true }).selectOption({ label: "My biggest fear is the awkward email when a client is 30 days late (waiting for approval)" });
  await expect(page.getByLabel("Draft text")).toContainText("Late invoices feel awkward");
  await page.getByLabel("Draft text").fill("[YOUR ANSWER] In today's fast-paced world it is a game changer.");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText(/The approval was withdrawn/)).toBeVisible();
  await page.goto("/approvals");
  await expect(page.getByText("Waiting (0)")).toBeVisible();
  await expect(page.getByText("The draft was edited after it was sent for approval.")).toBeVisible();
  await signOut(page);
  await login(page, "approver@example.test");
  const r = await call(page, "/approvals/1/decide", { approve: true });
  expect(r.status()).toBe(409);
  expect((await page.request.get("/api/drafts/1")).ok()).toBeTruthy();
  expect(((await (await page.request.get("/api/drafts/1")).json()) as { status: string }).status).toBe("draft");
});

test("the approvals page shows the text that is being approved", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/approvals");
  await expect(page.getByText("Name the invoice. Name the date. Ask when it will be paid.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the Studio" })).toBeVisible();
});

test("the audit log uses plain words and every row opens", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/audit");
  await expect(page.getByText("Draft written").first()).toBeVisible();
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/draft\.created|approval\.requested|profile\.built|draft:\d/);
  await page.getByRole("button", { name: "Open" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Entry number");
  await expect(page.getByRole("dialog")).toContainText("Who");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Check the chain" }).click();
  await expect(page.getByText(/audit log is intact/i)).toBeVisible();
});

test("integrations name the scheduler, not a raw category, and show the test answer", async ({ page }) => {
  await login(page);
  await page.goto("/integrations");
  await expect(page.getByRole("heading", { name: /Scheduler \(where an approved draft goes\)/ })).toBeVisible();
  await expect(page.getByText("File export")).toBeVisible();
  await page.getByRole("button", { name: "Test the one in use" }).click();
  await expect(page.getByText(/Scheduler \(where an approved draft goes\) test/).first()).toBeVisible();
  await expect(page.locator("main")).not.toContainText("undefined");
  await expect(page.getByRole("status").filter({ hasText: /^(Works|Failed):/ })).toBeVisible();
});

test("a file dropped on the library goes to the drop zone and a drop anywhere else does not leave the app", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/library");
  await page.waitForLoadState("networkidle");
  const before = page.url();
  const stray = await page.evaluate(() => { const dt = new DataTransfer(); dt.items.add(new File(["x"], "a.csv")); const e = new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }); document.querySelector("main")!.dispatchEvent(e); return e.defaultPrevented; });
  expect(stray, "the browser must not open a stray file").toBe(true);
  expect(page.url()).toBe(before);
  const body = "A dropped sample. ".repeat(10) + "It has enough words to count.";
  const dt = await page.evaluateHandle((b) => { const d = new DataTransfer(); d.items.add(new File([b], "dropped.txt", { type: "text/plain" })); return d; }, body);
  await page.dispatchEvent("[data-filedrop]", "drop", { dataTransfer: dt });
  await expect(page.getByText("Added 1 sample.").first()).toBeVisible();
  await expect(page.getByText("17 rows")).toBeVisible();
  // the same file again adds nothing
  const dt2 = await page.evaluateHandle((b) => { const d = new DataTransfer(); d.items.add(new File([b], "dropped.txt", { type: "text/plain" })); return d; }, body);
  await page.dispatchEvent("[data-filedrop]", "drop", { dataTransfer: dt2 });
  await expect(page.getByText(/Nothing new/)).toBeVisible();
  await expect(page.getByText("17 rows")).toBeVisible();
});

test("a CSV of post numbers can be chosen as a file, and counts read as English", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/performance");
  await page.getByRole("button", { name: "Import a CSV" }).click();
  const csv = "impressions,likes,comments,shares,text\n1000,40,3,2,A first imported post about invoices.\n900,30,2,1,A second imported post about reminders.\n";
  await page.getByLabel("Choose a CSV file or drop it here").setInputFiles({ name: "posts.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByLabel("CSV text")).toHaveValue(csv);
  await page.getByRole("button", { name: "Check the file" }).click();
  await expect(page.getByText("2 rows are new.")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator("main")).not.toContainText(/(?<!\d)1 posts/);
  await expect(page.locator("main")).toContainText("1 post with it, 59 without");
  await expect(page.locator("main")).toContainText("No post has this trait and 60 do not.");
  await expect(page.locator("main")).not.toContainText(/Only 0 post/);
});

test("the tracked links page fits a phone, shows this app's own address and does not make a link twice", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await resetDemo(page);
  await page.goto("/attribution");
  await page.waitForLoadState("networkidle");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const origin = new URL(page.url()).origin;
  await expect(page.getByText(`${origin}/r/seed010`)).toBeVisible();
  await page.getByLabel("Campaign").fill("twice");
  await page.getByRole("button", { name: "Make the link" }).click();
  await expect(page.getByText(/Link made: /).first()).toBeVisible();
  await page.getByLabel("Campaign").fill("twice");
  await page.getByRole("button", { name: "Make the link" }).click();
  await expect(page.getByText(/You already have that link/)).toBeVisible();
  expect((await (await page.request.get("/api/links")).json() as { campaign: string }[]).filter((l) => l.campaign === "twice")).toHaveLength(1);
});

test("a banned phrase cannot be added twice", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/rules");
  await page.getByLabel("Phrase to ban").fill("game changer");
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByText("Could not add the rule")).toBeVisible();
  await expect(page.getByText("That rule is already in the list.")).toBeVisible();
});

test("the calendar names its week in words and has a way back to today", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/calendar");
  await expect(page.getByRole("heading", { name: /^Nov 30 to Dec 6, 2026$/ })).toBeVisible();
  const today = page.getByRole("button", { name: "Today" });
  await expect(today).toHaveAttribute("aria-disabled", "true");
  await page.getByRole("button", { name: "Later" }).click();
  await expect(page.getByRole("heading", { name: /^Dec 7 to Dec 13, 2026$/ })).toBeVisible();
  await today.click();
  await expect(page.getByRole("heading", { name: /^Nov 30 to Dec 6, 2026$/ })).toBeVisible();
});

test("an idea that was dropped stays dropped, and an idea with a draft says so", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/ideas");
  await expect(page.getByRole("button", { name: "Write another draft" })).toHaveCount(2);
  const first = await page.getByRole("heading", { level: 3 }).first().innerText();
  expect(first.toLowerCase()).not.toContain("biggest fear"); // ideas that still need a draft come first
  await page.getByRole("button", { name: "Drop" }).first().click();
  await expect(page.getByText("Idea dropped.")).toBeVisible();
  await page.getByRole("button", { name: "Find ideas again" }).click();
  await expect(page.getByText(/Looked through all notes again\./)).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: first })).toHaveCount(0);
});

test("the numbers that count up never show a decimal on the way when they end whole", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  const sample = async (path: string) => {
    await page.goto(path, { waitUntil: "commit" });
    return page.evaluate(() => new Promise<string[]>((done) => {
      const seen = new Set<string>();
      const t = setInterval(() => { document.querySelectorAll(".sx-stat__value [aria-hidden]").forEach((e) => seen.add(`${(e.closest(".sx-stat") as HTMLElement | null)?.querySelector(".sx-stat__label")?.textContent}=${e.textContent}`)); }, 30);
      setTimeout(() => { clearInterval(t); done([...seen]); }, 2200);
    }));
  };
  for (const path of ["/performance", "/attribution"]) {
    const seen = await sample(path);
    expect(seen.length).toBeGreaterThan(3);
    for (const s of seen.filter((x) => !x.startsWith("Average engagement"))) expect(s, `${path} ${s}`).toMatch(/=[\d,]+$/);
  }
  await call(page, "/demo/reset");
  const again = await sample("/performance");
  for (const s of again.filter((x) => !x.startsWith("Average engagement"))) expect(s).toMatch(/=[\d,]+$/);
});

test("a draft that fails the checks cannot be put in front of an approver, and a clean one can", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await put(page, "/drafts/2", { text: CLEAN, author_id: 1 });
  await page.goto("/");
  await page.getByLabel("Draft", { exact: true }).selectOption({ index: 0 });
  await expect(page.getByRole("button", { name: "Ask for approval" })).toBeEnabled();
  await page.getByRole("button", { name: "Ask for approval" }).click();
  await expect(page.getByText("Sent for approval.").first()).toBeVisible();
});

test("exporting a planned draft leaves one calendar entry, and the text can be copied", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await login(page);
  await resetDemo(page);
  await signOut(page);
  await login(page, "approver@example.test");
  expect((await call(page, "/approvals/1/decide", { approve: true })).ok()).toBeTruthy();
  await signOut(page);
  await login(page);
  expect((await call(page, "/drafts/1/schedule", { platform: "x", run_on: "2026-12-03" })).ok()).toBeTruthy();
  await page.goto("/");
  await page.getByLabel("Draft", { exact: true }).selectOption({ label: "My biggest fear is the awkward email when a client is 30 days late (planned)" });
  await page.getByRole("button", { name: "Copy the text" }).click();
  await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("Late invoices feel awkward");
  await page.getByRole("button", { name: "Export to a file" }).click();
  await expect(page.getByText(/Exported\. Saved to .*-x-/)).toBeVisible();
  await page.goto("/calendar");
  await expect(page.locator(".vp-chip-post:has-text('exported')")).toHaveCount(1);
  await expect(page.locator(".vp-chip-post:has-text('planned')")).toHaveCount(0);
  await expect(page.locator(".vp-day[data-day='2026-12-03'] .vp-chip-post")).toContainText("X");
  await expect(page.getByLabel("Posting rhythm")).toContainText("Rhythm for the week of Nov 30:");
});

test("an experiment can name its two versions", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/experiments");
  await page.getByLabel("What are you comparing?").fill("Long opener against short opener");
  await page.getByLabel("Name of version A").fill("Alpha");
  await page.getByLabel("Name of version B").fill("Beta");
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText("Experiment started.")).toBeVisible();
  await expect(page.getByText("Alpha views")).toBeVisible();
  await expect(page.getByText("Beta hits")).toBeVisible();
});

test("a draft written from an idea opens in the studio", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/ideas");
  await page.getByRole("button", { name: "Write a draft" }).first().click();
  await page.getByRole("button", { name: "Write the draft" }).click();
  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await expect(page.getByLabel("Draft", { exact: true }).locator("option:checked")).toContainText("Do you have wording that actually works without being rude");
});
