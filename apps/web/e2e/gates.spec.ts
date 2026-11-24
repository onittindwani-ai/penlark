import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { PAGES, call, login, resetDemo, watch } from "./helpers";

const SHOTS = resolve(__dirname, "../../../docs/screenshots");
mkdirSync(SHOTS, { recursive: true });
const VIEWS = [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }];
const slug = (p: string) => (p === "/" ? "studio" : p.slice(1));
const BAD = "In today's fast-paced world it is important to note that effective communication is a game changer \u2014 and I grew sales by 300 percent last year. We shipped. Fair.";

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(900);
}
async function layoutShift(page: Page) {
  return page.evaluate(() => new Promise<number>((done) => {
    let total = 0;
    const o = new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) total += e.value; });
    o.observe({ type: "layout-shift", buffered: true });
    setTimeout(() => { o.disconnect(); done(total); }, 1200);
  }));
}

test.describe.serial("quality gates", () => {
  let page: Page;
  let errors: string[];
  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ baseURL: `http://localhost:${process.env.WEB_PORT ?? "3000"}`, viewport: { width: 1440, height: 900 } });
    page = await ctx.newPage();
    errors = watch(page);
    await login(page);
    await resetDemo(page);
  });
  test.afterAll(async () => { await page.close(); });

  for (const v of VIEWS) {
    test(`screenshot of every page, ${v.name}`, async () => {
      await page.setViewportSize({ width: v.width, height: v.height });
      for (const p of PAGES) {
        await page.goto(p); await settle(page);
        await page.screenshot({ path: `${SHOTS}/page-${slug(p)}-${v.name}.png` });
      }
    });

    test(`eight states, ${v.name}`, async () => {
      await page.setViewportSize({ width: v.width, height: v.height });
      const shot = (n: string) => page.screenshot({ path: `${SHOTS}/state-${n}-${v.name}.png` });
      // 1 default: the studio with a close match
      await page.goto("/"); await settle(page);
      await expect(page.locator("[aria-label='Voice match']").first()).toBeVisible();
      await shot("1-default-studio");
      // 2 detail: the radar with an axis picked
      await page.goto("/voice"); await settle(page);
      await page.getByText("Formality", { exact: true }).first().click();
      await expect(page.getByRole("heading", { name: "Formality" })).toBeVisible();
      await shot("2-detail-radar-axis");
      // 3 warning: banned phrases and an unsupported claim
      await page.goto("/"); await settle(page);
      await page.getByLabel("Draft text").fill(BAD);
      await expect(page.getByText("is on the banned list").first()).toBeVisible();
      await expect(page.getByText("Needs a source or a founder fact").first()).toBeVisible();
      await page.waitForTimeout(500);
      await shot("3-warning-rules-broken");
      // 4 button mid processing
      await page.route("**/api/demo/tick", async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue(); });
      await page.getByRole("button", { name: "Run now" }).click(); await page.waitForTimeout(500);
      await shot("4-button-processing");
      await page.waitForTimeout(2600);
      await page.unroute("**/api/demo/tick");
      // 5 toast with undo
      await page.goto("/rules"); await settle(page);
      await page.getByRole("button", { name: /Turn off/ }).first().click();
      await expect(page.getByText("Rule turned off.")).toBeVisible();
      await page.waitForTimeout(400);
      await shot("5-toast-with-undo");
      await page.getByRole("button", { name: "Undo" }).click();
      await page.waitForTimeout(800);
      // 6 empty: no ideas
      await page.route("**/api/ideas", (route) => route.fulfill({ json: [] }));
      await page.goto("/ideas"); await settle(page);
      await expect(page.getByText("No ideas yet")).toBeVisible();
      await shot("6-empty-state");
      await page.unroute("**/api/ideas");
      // 7 error: the draft list is cut off
      const before = errors.length;
      await page.route("**/api/drafts", (route) => route.abort());
      await page.goto("/"); await page.waitForTimeout(3000);
      await expect(page.getByText(/Could not load/i).first()).toBeVisible();
      await shot("7-error-state");
      await page.unroute("**/api/drafts");
      errors.splice(before);
      // 8 dark
      await page.goto("/voice"); await settle(page);
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
      await page.waitForTimeout(300);
      await shot("8-dark");
      await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
    });
  }

  for (const theme of ["light", "dark"]) {
    test(`axe finds no serious or critical problems on any page, ${theme}`, async () => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
      const bad: string[] = [];
      for (const p of PAGES) {
        await page.goto(p); await settle(page);
        if (theme === "dark") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
        await page.waitForTimeout(300);
        const res = await new AxeBuilder({ page }).analyze();
        for (const v of res.violations.filter((x) => x.impact === "serious" || x.impact === "critical")) bad.push(`${theme} ${p} ${v.id} ${v.impact}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`);
      }
      await page.emulateMedia({ colorScheme: "light" });
      await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
      expect(bad).toEqual([]);
    });
  }

  test("keyboard path: every stop shows focus, the palette opens, the editor works", async () => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/"); await settle(page);
    const seen: string[] = [];
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const e = document.activeElement as HTMLElement | null;
        if (!e || e === document.body) return null;
        const cs = getComputedStyle(e);
        const r = e.getBoundingClientRect();
        return { name: (e.getAttribute("aria-label") || e.textContent || e.tagName).trim().slice(0, 30), ring: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none" || e.matches("[data-selected]"), visible: r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight };
      });
      if (info) { seen.push(info.name); expect(info.visible, `${info.name} is on screen`).toBeTruthy(); expect(info.ring, `${info.name} shows focus`).toBeTruthy(); }
    }
    expect(seen.length).toBeGreaterThan(10);
    await page.keyboard.press("Control+k");
    const dlg = page.getByRole("dialog");
    await expect(dlg).toBeVisible();
    await page.keyboard.type("Calendar");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/calendar/);
    await page.goto("/");
    await page.getByLabel("Draft text").focus();
    await page.keyboard.type(" extra words typed with the keyboard only");
    await expect(page.getByLabel("Draft text")).toContainText("keyboard only");
  });

  test("reduced motion: nothing animates forever", async () => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/"); await page.waitForLoadState("networkidle"); await page.waitForTimeout(1200);
    const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running" && (a.effect?.getComputedTiming().iterations ?? 1) === Infinity).length);
    expect(running).toBe(0);
    await page.emulateMedia({ reducedMotion: "no-preference" });
  });

  test("no layout shift on any page", async () => {
    const bad: string[] = [];
    for (const p of PAGES) {
      await page.goto(p);
      const cls = await layoutShift(page);
      if (cls > 0.1) bad.push(`${p} ${cls.toFixed(3)}`);
    }
    expect(bad).toEqual([]);
  });

  test("5,000 rows: the performance table opens fast and stays responsive", async () => {
    const add = await call(page, "/demo/stress-posts", { n: 5000 });
    expect(add.ok()).toBeTruthy();
    const t0 = Date.now();
    await page.goto("/performance");
    await expect(page.locator('[role="row"]').first()).toBeVisible({ timeout: 20000 });
    await settle(page);
    expect(Date.now() - t0, "performance table with 5,000 rows is ready").toBeLessThan(12000);
    expect(await page.locator('[role="row"]').count(), "only visible rows are in the page").toBeLessThan(200);
    await page.screenshot({ path: `${SHOTS}/state-13-five-thousand-rows-desktop.png` });
  });

  test("no console errors or failed requests during the whole run", async () => {
    expect(errors).toEqual([]);
  });
});
