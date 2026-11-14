import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  GUEST,
  NOOR,
  OWNER,
  TIKKA,
  addWithChoices,
  approveOrder,
  billOf,
  clearDemoLimits,
  confirmOrder,
  demoInfo,
  openTable,
  openTableMenu,
  placeOrder,
  resetVenue,
  skipWelcome,
  sql,
  staffPage,
  venueTables,
  type VenueTable,
} from "./helpers";

// Phase 2: a full order at Tikka Town (GBP, VAT included, optional 10% service outside tax) and at
// Noor & Za'atar in Arabic (AED, VAT included, no service). Exact guest strings come from
// apps/guest-web/src/i18n/{en,ar}.ts; dish names from data/seed/{tikka_town,noor_and_zaatar}.json.

const EASTERN_DIGITS = /[٠-٩۰-۹]/;
const ARABIC_SCRIPT = /[؀-ۿ]/;
const PRINT = (slug: string) => new RegExp(`/bills/[0-9a-f-]{36}/print\\?venue=${slug}$`);
const amount = async (el: Locator) => Number((await el.innerText()).match(/[\d,]+\.\d{2}/)![0].replace(/,/g, ""));
const pence = (n: number) => Math.round(n * 100);

let tikka: Record<string, VenueTable>;
let noor: Record<string, VenueTable>;

test.beforeEach(() => clearDemoLimits());

test.describe.serial("the two new venues", () => {
  test.beforeAll(async () => {
    for (const slug of [TIKKA, NOOR]) await resetVenue(slug);
    tikka = await venueTables(TIKKA);
    noor = await venueTables(NOOR);
  });

  test("Tikka Town in English: the optional service is its own line and the bill settles with it", async ({ page, browser }) => {
    test.setTimeout(120_000);
    await openTable(TIKKA, "T1");
    await openTableMenu(page, tikka.T1.qr_token);
    await expect(page.getByRole("heading", { name: "Tikka Town" })).toBeVisible();
    await expect(page.getByText("An optional 10% service charge is added to table bills.")).toBeVisible();
    await expect(page.locator("main .figure").filter({ hasText: /^£\d+\.\d{2}$/ }).first()).toBeVisible();

    await addWithChoices(page, "Chicken Tikka Masala", ["Medium"]);
    await page.getByRole("button", { name: /View order/ }).click();
    const id = await confirmOrder(page); // first order of the visit: staff approve it

    await page.getByRole("button", { name: "Pay bill" }).click();
    const pay = page.getByRole("dialog", { name: "Pay bill" });
    const subtotal = await amount(pay.locator("p").filter({ hasText: /^Subtotal/ }));
    const service = pay.getByRole("switch", { name: /^Add optional service \(10%\): £\d+\.\d{2}$/ });
    await expect(service).toHaveAttribute("aria-checked", "true");
    const serviceAmount = await amount(service);
    expect(pence(serviceAmount)).toBe(Math.round(pence(subtotal) / 10));
    // VAT is inside the dish prices only: the service is outside tax.
    const vat = pay.getByText(/^Includes VAT 20%: £\d+\.\d{2}$/);
    expect(pence(await amount(vat))).toBe(Math.round(pence(subtotal) / 6));
    const total = pay.getByTestId("pay-total");
    expect(pence(await amount(total))).toBe(pence(subtotal) + pence(serviceAmount));
    // Optional: off is the subtotal alone, then back on.
    await service.click();
    await expect(service).toHaveAttribute("aria-checked", "false");
    await expect.poll(async () => pence(await amount(total))).toBe(pence(subtotal));
    await service.click();
    await expect(service).toHaveAttribute("aria-checked", "true");
    const expected = (pence(subtotal) + pence(serviceAmount)) / 100;
    await pay.getByRole("button", { name: /^Cash/ }).click();
    await expect(pay.getByRole("status")).toHaveText(`A waiter is coming to collect £${expected.toFixed(2)}.`);
    await page.keyboard.press("Escape");

    const staff = await (await browser.newContext()).newPage();
    await staffPage(staff, TIKKA);
    await staff.goto(`${OWNER}/bills`);
    await staff.getByRole("button").filter({ hasText: "Table T1" }).click();
    const bill = staff.getByRole("dialog", { name: /^Table T1 · Bill no\. \d{4}$/ });
    await expect(bill.getByText(/1 × Chicken Tikka Masala/)).toBeVisible();
    await expect(bill.getByRole("radio", { name: /^Cash/ })).toBeChecked();
    await expect(bill.getByRole("switch", { name: /^Optional service \(10%\): £\d+\.\d{2}/ })).toHaveAttribute("aria-checked", "true");
    await bill.getByRole("button", { name: "Confirm received" }).click();

    await expect(staff).toHaveURL(PRINT(TIKKA));
    await expect(staff.locator("p").filter({ hasText: /^Optional service/ })).toHaveText(`Optional service£${serviceAmount.toFixed(2)}`);
    await expect(staff.locator("p").filter({ hasText: /^Total/ })).toHaveText(`Total£${expected.toFixed(2)}`);
    const [status, settled, svc] = sql(`SELECT status || '|' || total || '|' || service_charge_amount FROM bills WHERE id = '${billOf(id)}'`).split("|");
    expect(status).toBe("settled");
    expect(pence(Number(settled))).toBe(pence(expected));
    expect(pence(Number(svc))).toBe(pence(serviceAmount));
    await staff.context().close();
  });

  test("Noor & Za'atar in Arabic: right to left from the first byte, Latin digits, English kitchen and bill", async ({ page, browser }) => {
    test.setTimeout(120_000);
    await openTable(NOOR, "T1");
    await openTableMenu(page, noor.T1.qr_token, "ar"); // taps "العربية", then "عرض القائمة"; lands on /ar/menu
    const html = await (await page.request.get(`${GUEST}/ar/menu`)).text();
    // The [lang] layout wraps every page in lang/dir in the server HTML, before any content renders.
    expect(html).toMatch(/<body[^>]*><div hidden="">.*?<\/div><div lang="ar" dir="rtl"/);
    await expect(page.getByRole("heading", { name: "مجبوس دجاج" })).toBeVisible();
    const menuText = await page.locator("body").innerText();
    expect(menuText).toMatch(/\d/);
    expect(menuText).not.toMatch(EASTERN_DIGITS);

    await page.getByRole("button", { name: "إضافة شاي كرك", exact: true }).click(); // ui.addDish
    const dish = page.getByRole("dialog", { name: "شاي كرك" });
    await dish.getByText("عادي", { exact: true }).click();
    await dish.getByRole("button", { name: /^إضافة إلى الطلب/ }).click(); // dish.addToOrder
    await expect(dish).toBeHidden();
    await page.getByRole("button", { name: /^عرض الطلب/ }).click(); // ui.checkout · count
    const cart = page.getByRole("dialog", { name: "طلبك" });
    await expect(cart).toBeVisible();
    expect(await cart.innerText()).not.toMatch(EASTERN_DIGITS);
    const id = await placeOrder(page, "ar"); // "تأكيد الطلب"
    await approveOrder(id);

    await page.getByRole("button", { name: "دفع الفاتورة" }).click(); // pay.button
    const pay = page.getByRole("dialog", { name: "دفع الفاتورة" });
    await expect(pay.getByTestId("pay-total")).toBeVisible();
    await expect(pay.getByRole("switch")).toHaveCount(0); // no service at Noor
    await pay.getByRole("button", { name: /^نقدًا/ }).click(); // pay.methods.cash
    await expect(pay.getByRole("status")).toHaveText(/^سيأتي نادل لتحصيل .*\d.*\.$/); // pay.cash
    expect(await pay.innerText()).not.toMatch(EASTERN_DIGITS);
    await page.keyboard.press("Escape");

    const kitchen = await (await browser.newContext()).newPage();
    await staffPage(kitchen, NOOR);
    await kitchen.goto(`${OWNER}/kitchen`);
    await expect(kitchen.getByRole("heading", { name: "TABLE T1" })).toBeVisible();
    await expect(kitchen.getByText(/^Karak Chai — Regular$/).first()).toBeVisible();
    expect(await kitchen.locator("body").innerText()).not.toMatch(ARABIC_SCRIPT);

    await kitchen.goto(`${OWNER}/bills`);
    await kitchen.getByRole("button").filter({ hasText: "Table T1" }).click();
    const bill = kitchen.getByRole("dialog", { name: /^Table T1 · Bill no\. \d{4}$/ });
    await expect(bill.getByText(/1 × Karak Chai/)).toBeVisible();
    await expect(bill.getByRole("switch")).toHaveCount(0);
    expect(await kitchen.locator("body").innerText()).not.toMatch(ARABIC_SCRIPT);
    await kitchen.context().close();
  });

  test("each venue offers only its own languages, and others fall back to the visit's language", async ({ browser }) => {
    const tikkaCtx = await browser.newContext();
    const t = await tikkaCtx.newPage();
    await t.goto(`${GUEST}/q/${tikka.T2.qr_token}`);
    await expect(t.getByRole("button", { name: "View Menu" })).toBeVisible();
    // English only: no language choice.
    await expect(t.getByRole("group", { name: "Language" })).toHaveCount(0);
    await expect(t.getByRole("button", { name: "English", exact: true })).toHaveCount(0);
    await openTable(TIKKA, "T2");
    await openTableMenu(t, tikka.T2.qr_token);
    await t.goto(`${GUEST}/ar/menu`);
    await expect(t).toHaveURL(/\/en\/menu$/);
    await tikkaCtx.close();

    const noorCtx = await browser.newContext();
    const n = await noorCtx.newPage();
    await n.goto(`${GUEST}/q/${noor.T2.qr_token}`);
    await expect(n.getByRole("group", { name: "Language" }).getByRole("button")).toHaveText(["English", "العربية"]);
    await openTable(NOOR, "T2");
    await openTableMenu(n, noor.T2.qr_token, "en");
    await n.goto(`${GUEST}/ur/menu`);
    await expect(n).toHaveURL(/\/en\/menu$/);
    await noorCtx.close();
  });
});

/** A full-page PNG kept in the test's output folder and attached to the report. */
async function shot(page: Page, name: string) {
  const path = test.info().outputPath(`${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await test.info().attach(name, { path, contentType: "image/png" });
}

test("screenshots of every venue's welcome, menu and sample bill", async ({ browser }) => {
  test.setTimeout(240_000);
  const { venues } = await demoInfo();
  expect(venues.map((v) => v.slug)).toEqual(expect.arrayContaining([TIKKA, NOOR]));
  for (const venue of venues) {
    const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const page = await context.newPage();
    await page.goto(`${GUEST}/q/${venue.qr_token}`);
    await page.getByRole("button", { name: "View Menu" }).click();
    await expect(page.getByTestId("welcome")).toBeVisible({ timeout: 10_000 });
    await shot(page, `${venue.slug}-welcome`);
    await skipWelcome(page);
    await expect(page.locator("main li").first()).toBeVisible();
    await shot(page, `${venue.slug}-menu`);

    // The latest settled bill of the venue: one with a bill number from a real settle if there is one,
    // else from the demo history (simulated bills carry no bill number).
    const billId = sql(
      `SELECT b.id FROM bills b JOIN restaurant r ON r.id = b.restaurant_id
       WHERE r.slug = '${venue.slug}' AND b.status = 'settled' ORDER BY b.bill_no IS NULL, b.settled_at DESC LIMIT 1`,
    );
    expect(billId, `${venue.slug} has a settled bill`).not.toBe("");
    await staffPage(page, venue.slug);
    await page.setViewportSize({ width: 600, height: 900 });
    await page.goto(`${OWNER}/bills/${billId}/print?venue=${venue.slug}`);
    await expect(page.locator("p").filter({ hasText: /^Total/ })).toBeVisible();
    await shot(page, `${venue.slug}-sample-bill`);
    await context.close();
  }
});
