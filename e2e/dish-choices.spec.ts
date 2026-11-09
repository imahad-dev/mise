import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import {
  ANGEETHI,
  GUEST,
  KEHWA,
  OWNER,
  addWithChoices,
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

// Dish page stories (spec 2026-11-05): real taps on a 375 px phone at an open table.

const PHONE = { viewport: { width: 375, height: 812 } };
const PRINT = /\/bills\/[0-9a-f-]{36}\/print\?venue=angeethi-house$/;
const tables: Record<string, Record<string, VenueTable>> = {};
let contexts: BrowserContext[] = [];

test.beforeEach(() => clearDemoLimits());
test.afterEach(async () => {
  for (const c of contexts) await c.close();
  contexts = [];
});

async function newPage(browser: Browser, options = {}): Promise<Page> {
  const context = await browser.newContext(options);
  contexts.push(context);
  return context.newPage();
}

/** A phone at an open table, on the menu; `avoid` ticks allergens on the welcome screen first. */
async function phoneAt(browser: Browser, slug: string, label: string, avoid: string[] = []): Promise<Page> {
  await openTable(slug, label);
  const page = await newPage(browser, PHONE);
  const qr = tables[slug][label].qr_token;
  if (avoid.length === 0) {
    await openTableMenu(page, qr);
    return page;
  }
  await page.goto(`${GUEST}/q/${qr}`);
  for (const a of avoid) await page.getByRole("button", { name: new RegExp(`^${a}`) }).click();
  await page.getByRole("button", { name: "View Menu" }).click();
  await expect(page).toHaveURL(/\/en\/menu$/);
  return page;
}

async function staffBrowser(browser: Browser, slug: string, path: string): Promise<Page> {
  const page = await newPage(browser);
  await staffPage(page, slug);
  await page.goto(`${OWNER}${path}`);
  return page;
}

/** The staff confirm sheet of one table's open bill. */
async function openTableBill(staff: Page, label: string) {
  await staff.getByRole("button").filter({ hasText: `Table ${label}` }).click();
  return staff.getByRole("dialog", { name: new RegExp(`^Table ${label} · Bill no\\. \\d{4}$`) });
}

/** Nothing on the page scrolls sideways at phone width. */
async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test.describe.serial("Dish choices: a phone guest makes it theirs", () => {
  test.beforeAll(async () => {
    for (const slug of [ANGEETHI, KEHWA]) {
      await resetVenue(slug);
      tables[slug] = await venueTables(slug);
    }
  });

  test("sent to what is missing, leave-out notice, Back, kitchen sees NO ONIONS, bill lists it", async ({ browser }) => {
    test.setTimeout(120_000);
    const page = await phoneAt(browser, ANGEETHI, "T1");
    await page.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chicken Karahi" });
    await expect(sheet).toBeVisible();

    // The action names what is missing and takes the guest there.
    await sheet.getByRole("button", { name: "Choose size" }).click();
    await expect(sheet.locator("#group-size")).toBeFocused();
    await sheet.getByText("1 kg", { exact: true }).click();
    await sheet.getByRole("button", { name: "Choose Spice" }).click();
    await expect(sheet.getByRole("group", { name: /^Spice/ })).toBeFocused();
    await sheet.getByText("Hot", { exact: true }).click();
    await expect(sheet.getByRole("button", { name: /^Add to order · Rs/ })).toBeVisible();

    await expect(sheet.getByText("Leaving something out doesn't make a dish safe")).toBeVisible();

    // The phone's Back closes the sheet and stays on the menu.
    await page.goBack();
    await expect(sheet).toBeHidden();
    await expect(page).toHaveURL(/\/en\/menu$/);
    await expect(page.getByRole("heading", { name: "Angeethi House" })).toBeVisible();

    await addWithChoices(page, "Chicken Karahi", ["1 kg", "Hot", "Onions"]);
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(page.getByRole("dialog", { name: "Your Order" }).getByText("Hot, No onions")).toBeVisible();
    const id = await placeOrder(page);
    await approveOrder(id);

    // The kitchen cannot miss a leave-out: it is in capitals.
    const staff = await staffBrowser(browser, ANGEETHI, "/kitchen");
    const no = staff.getByText("NO Onions", { exact: true });
    await expect(no).toBeVisible();
    await expect(no).toHaveCSS("text-transform", "uppercase");

    // Settle as staff (story 10): the bill lists the choice.
    await page.getByRole("button", { name: "Pay bill" }).click();
    const pay = page.getByRole("dialog", { name: "Pay bill" });
    await pay.getByRole("button", { name: /^Cash/ }).click();
    await expect(pay.getByRole("status")).toHaveText(/^A waiter is coming to collect Rs\s[\d,]+\.$/);
    await page.keyboard.press("Escape");

    await staff.goto(`${OWNER}/bills`);
    const bill = await openTableBill(staff, "T1");
    await expect(bill.getByText("Hot, No onions")).toBeVisible();
    await bill.getByRole("button", { name: "Confirm received" }).click();
    await expect(staff).toHaveURL(PRINT);
  });

  test("a chai with the Normal default adds in one tap", async ({ browser }) => {
    const page = await phoneAt(browser, ANGEETHI, "T2");
    await page.getByRole("button", { name: "Add Doodh Patti Chai", exact: true }).click();
    const bar = page.getByRole("button", { name: /View order · 1/ });
    await expect(bar).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await bar.click();
    await expect(page.getByRole("dialog", { name: "Your Order" }).getByText("Normal", { exact: true })).toBeVisible();
  });

  test("an extra with nuts warns a guest avoiding tree nuts and stops at the acknowledgement", async ({ browser }) => {
    test.setTimeout(120_000);
    // The cappuccino has no tree nuts; its Almond milk extra has.
    const page = await phoneAt(browser, KEHWA, "T1", ["Tree Nuts"]);
    const cart = page.getByRole("dialog", { name: "Your Order" });

    // Control: a paid extra without nuts is priced in the cart, and nothing says Contains.
    await addWithChoices(page, "Cappuccino", ["Regular", "Extra shot"]);
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(cart.getByText(/Extra shot \+Rs\s[\d,]+/)).toBeVisible();
    await expect(cart.getByTestId("allergen-chip-contains")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(cart).toBeHidden();

    // Opened from the dish name this time: the Almond milk row says what it contains.
    await page.getByRole("heading", { name: "Cappuccino", exact: true }).getByRole("button").click();
    const sheet = page.getByRole("dialog", { name: "Cappuccino" });
    const almond = sheet.locator("label").filter({ hasText: "Almond milk" });
    await expect(almond.getByTestId("allergen-chip-contains")).toContainText("Tree Nuts");
    await sheet.getByText("Regular", { exact: true }).click();
    await almond.click();
    await sheet.getByRole("button", { name: /Add to order/ }).click();
    await expect(sheet).toBeHidden();

    await page.getByRole("button", { name: /View order/ }).click();
    await expect(cart.getByTestId("allergen-chip-contains")).toHaveCount(1);
    await expect(cart.getByTestId("allergen-chip-contains")).toContainText("Tree Nuts");
    await expect(cart.getByText(/Almond milk \+Rs\s[\d,]+/)).toBeVisible();
    await expect(cart.getByText("Allergen Warning")).toBeVisible();
    await expect(cart.getByText("I have spoken with staff and understand the allergen risks")).toBeVisible();
    await expect(cart.getByRole("button", { name: "Confirm Order" })).toBeDisabled();
    const id = await placeOrder(page);
    await approveOrder(id);

    // The staff bill lists both extras with their prices.
    const staff = await staffBrowser(browser, KEHWA, "/bills");
    const bill = await openTableBill(staff, "T1");
    await expect(bill.getByText(/Extra shot \+Rs\s[\d,]+/)).toBeVisible();
    await expect(bill.getByText(/Almond milk \+Rs\s[\d,]+/)).toBeVisible();
  });

  test("the phone-width menu, dish page and cart have no sideways scroll; the action is reachable", async ({ browser }) => {
    const page = await phoneAt(browser, ANGEETHI, "T4");
    await noSidewaysScroll(page);

    await page.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chicken Karahi" });
    await expect(sheet).toBeVisible();
    await noSidewaysScroll(page);
    expect(await sheet.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true);
    await expect(sheet.getByRole("button", { name: "Choose size" })).toBeInViewport();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();

    await page.getByRole("button", { name: "Add Naan", exact: true }).click();
    await page.getByRole("button", { name: /View order/ }).click();
    const cart = page.getByRole("dialog", { name: "Your Order" });
    await expect(cart).toBeVisible();
    await noSidewaysScroll(page);
    expect(await cart.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true);
  });
});
