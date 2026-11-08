import { expect, test, type Browser, type Page } from "@playwright/test";
import {
  ANGEETHI,
  GUEST,
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

// Dish page stories (spec 2026-11-05): real taps on a 375 px phone at an open Angeethi table.

const PHONE = { viewport: { width: 375, height: 812 } };
const PRINT = /\/bills\/[0-9a-f-]{36}\/print\?venue=angeethi-house$/;
let T: Record<string, VenueTable> = {};

test.beforeEach(() => clearDemoLimits());

/** A phone at an open table, on the menu; `avoid` ticks allergens on the welcome screen first. */
async function phoneAt(browser: Browser, label: string, avoid: string[] = []): Promise<Page> {
  await openTable(ANGEETHI, label);
  const page = await (await browser.newContext(PHONE)).newPage();
  if (avoid.length === 0) {
    await openTableMenu(page, T[label].qr_token);
    return page;
  }
  await page.goto(`${GUEST}/q/${T[label].qr_token}`);
  for (const a of avoid) await page.getByRole("button", { name: new RegExp(`^${a}`) }).click();
  await page.getByRole("button", { name: "View Menu" }).click();
  await expect(page).toHaveURL(/\/en\/menu$/);
  return page;
}

async function staffBrowser(browser: Browser, path: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await staffPage(page, ANGEETHI);
  await page.goto(`${OWNER}${path}`);
  return page;
}

test.describe.serial("Dish choices: a phone guest makes it theirs", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("sent to what is missing, leave-out notice, Back, kitchen sees NO ONIONS, bill lists it", async ({ browser }) => {
    test.setTimeout(120_000);
    const page = await phoneAt(browser, "T1");
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
    const staff = await staffBrowser(browser, "/kitchen");
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
    await staff.getByRole("button").filter({ hasText: "Table T1" }).click();
    const bill = staff.getByRole("dialog", { name: /^Table T1 · Bill no\. \d{4}$/ });
    await expect(bill.getByText("Hot, No onions")).toBeVisible();
    await bill.getByRole("button", { name: "Confirm received" }).click();
    await expect(staff).toHaveURL(PRINT);
  });

  test("a chai with the Normal default adds in one tap", async ({ browser }) => {
    const page = await phoneAt(browser, "T2");
    await page.getByRole("button", { name: "Add Doodh Patti Chai", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(page.getByRole("dialog", { name: "Your Order" }).getByText("Normal", { exact: true })).toBeVisible();
  });

  test("extra milk warns a guest avoiding milk", async ({ browser }) => {
    const page = await phoneAt(browser, "T3", ["Milk"]);
    // Opened from the dish name this time.
    await page.getByRole("heading", { name: "Doodh Patti Chai" }).getByRole("button").click();
    const sheet = page.getByRole("dialog", { name: "Doodh Patti Chai" });
    const extra = sheet.locator("label").filter({ hasText: "Extra milk" });
    await expect(extra.getByTestId("allergen-chip-contains")).toContainText("Contains: Milk");
    await extra.click();
    await sheet.getByRole("button", { name: /Add to order/ }).click();
    await expect(sheet).toBeHidden();
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(page.getByText("Allergen Warning")).toBeVisible();
  });

  test("the phone-width dish page has no sideways scroll and a reachable action", async ({ browser }) => {
    const page = await phoneAt(browser, "T4");
    await page.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chicken Karahi" });
    await expect(sheet).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
    await expect(sheet.getByRole("button", { name: "Choose size" })).toBeInViewport();
  });
});
