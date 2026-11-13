import { expect, test, type Page } from "@playwright/test";
import {
  ANGEETHI,
  GUEST,
  OWNER,
  approveOrder,
  clearDemoLimits,
  openTable,
  openTableMenu,
  placeOrder,
  resetVenue,
  staffPage,
  venueTables,
  type VenueTable,
} from "./helpers";

// Phase 1b: a guest at Angeethi House uses the app in Urdu, right to left, with Latin-digit money.
// Exact strings come from apps/guest-web/src/i18n/ur.ts; dish names from data/seed/angeethi_house.json.

const EASTERN_DIGITS = /[٠-٩۰-۹]/;
const ARABIC_SCRIPT = /[؀-ۿ]/;
const ASK = "Angeethi House سے پوچھیں"; // ui.chatTitle
const ADD_NAAN = "شامل کریں نان"; // `${ui.addToCart} ${name}`
let tables: Record<string, VenueTable>;

test.beforeEach(() => clearDemoLimits());

test.describe.serial("Urdu at Angeethi House", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    tables = await venueTables(ANGEETHI);
  });

  async function urduMenu(page: Page, label: string) {
    await openTable(ANGEETHI, label);
    await openTableMenu(page, tables[label].qr_token, "ur");
  }

  test("the scan page offers English and Urdu only, and Urdu turns it right-to-left", async ({ page }) => {
    await page.goto(`${GUEST}/q/${tables.T1.qr_token}`);
    const group = page.getByRole("group", { name: "زبان" }).or(page.getByRole("group", { name: "Language" }));
    await expect(group.getByRole("button")).toHaveText(["English", "اردو"]);
    await page.getByRole("button", { name: "اردو", exact: true }).click();
    await expect(page.locator('[dir="rtl"][lang="ur"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "مینو دیکھیں" })).toBeVisible();
  });

  test("the menu is Urdu, right-to-left, with Rs prices in Latin digits, from the first byte", async ({ page }) => {
    await urduMenu(page, "T2");
    const html = await (await page.request.get(`${GUEST}/ur/menu`)).text();
    // The [lang] layout wraps every page in lang/dir in the server HTML, before any content renders.
    expect(html).toMatch(/<body[^>]*><div hidden="">.*?<\/div><div lang="ur" dir="rtl"/);
    await expect(page.locator('[lang="ur"][dir="rtl"]').filter({ has: page.locator("main") })).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "چکن کڑاہی" })).toBeVisible();
    const price = page.locator("main .figure").filter({ hasText: /^Rs\s[\d,]+$/ }).first();
    await expect(price).toBeVisible();
    await expect(price).toHaveCSS("direction", "ltr");
    expect(await page.locator("body").innerText()).not.toMatch(EASTERN_DIGITS);
  });

  test("an order is placed and paid in Urdu; the kitchen still reads English", async ({ page, browser }) => {
    test.setTimeout(120_000);
    await urduMenu(page, "T3");
    await page.getByRole("button", { name: ADD_NAAN, exact: true }).click();
    await page.getByRole("button", { name: /^آرڈر دیکھیں/ }).click(); // ui.checkout · count
    await expect(page.getByRole("dialog", { name: "آپ کا آرڈر" })).toBeVisible();
    expect(await page.getByRole("dialog", { name: "آپ کا آرڈر" }).innerText()).not.toMatch(EASTERN_DIGITS);
    const id = await placeOrder(page, "ur");
    await approveOrder(id);

    await page.getByRole("button", { name: "بل ادا کریں" }).click();
    const pay = page.getByRole("dialog", { name: "بل ادا کریں" });
    await pay.getByRole("button", { name: /^نقد/ }).click();
    await expect(pay.getByRole("status")).toHaveText(/^ویٹر Rs\s[\d,]+ لینے آ رہا ہے۔$/); // pay.cash
    expect(await pay.innerText()).not.toMatch(EASTERN_DIGITS);
    await page.keyboard.press("Escape");

    const kitchen = await (await browser.newContext()).newPage();
    await staffPage(kitchen, ANGEETHI);
    await kitchen.goto(`${OWNER}/kitchen`);
    await expect(kitchen.getByRole("heading", { name: "TABLE T3" })).toBeVisible();
    await expect(kitchen.getByText("Naan", { exact: true }).first()).toBeVisible();
    expect(await kitchen.locator("body").innerText()).not.toMatch(ARABIC_SCRIPT);
    await kitchen.context().close();
  });

  test("at 320 px in Urdu the assistant never covers a dish and nothing scrolls sideways", async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 320, height: 640 } });
    const page = await ctx.newPage();
    await urduMenu(page, "T4");
    const clears = async (when: string) => {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${when}: no sideways scroll`).toBe(true);
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      const row = await page.locator("main li").last().boundingBox(); // the whole row: price, chips and + button
      const chat = await page.getByRole("button", { name: ASK }).boundingBox();
      expect(row && chat, `${when}: last dish row and assistant button are on screen`).toBeTruthy();
      const apart = chat!.y >= row!.y + row!.height || chat!.y + chat!.height <= row!.y;
      expect(apart, `${when}: assistant ${JSON.stringify(chat)} vs last dish row ${JSON.stringify(row)}`).toBe(true);
    };
    await clears("menu");
    await page.getByRole("button", { name: ADD_NAAN, exact: true }).click();
    await expect(page.getByRole("button", { name: /^آرڈر دیکھیں · 1/ })).toBeVisible();
    await clears("menu with the order bar");
    await ctx.close();
  });

  test("a language the venue does not offer falls back to the visit's language", async ({ page }) => {
    await openTable(ANGEETHI, "T5");
    await openTableMenu(page, tables.T5.qr_token, "en");
    await page.goto(`${GUEST}/ar/menu`);
    await expect(page).toHaveURL(/\/en\/menu$/);
    const it = await page.goto(`${GUEST}/it/menu`);
    expect(it?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: "Angeethi House" })).toHaveCount(0);
  });
});
