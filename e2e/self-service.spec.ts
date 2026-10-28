import { expect, test, type Browser, type Page } from "@playwright/test";
import {
  ANGEETHI,
  GUEST,
  KEHWA,
  OWNER,
  billOf,
  clearDemoLimits,
  confirmOrder,
  counterTable,
  demoApi,
  floorTile,
  nextPickupLabel,
  openTableMenu,
  orderOne,
  placeOrder,
  resetVenue,
  sql,
  staffPage,
  venueTables,
  type VenueTable,
} from "./helpers";

// Spec §6.6: real-world self-service stories. Each story starts from a quiet venue (resetVenue)
// and uses its own table, so stories never see each other's bills.

const PAID = /^Paid · Bill no\. \d{4} · thank you/;
const PRINT = /\/bills\/[0-9a-f-]{36}\/print\?venue=angeethi-house$/;
// Guest pages poll their bill every 10 s; settles of table bills reach them on the next poll.
const POLL = { timeout: 20_000 };

let T: Record<string, VenueTable> = {};

test.beforeEach(() => clearDemoLimits()); // demo-login allows 20 per minute per IP

async function staffBrowser(browser: Browser, venue: string, path: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await staffPage(page, venue);
  await page.goto(`${OWNER}${path}`);
  return page;
}

/** A guest phone at an Angeethi table, on the menu. */
async function guestAt(browser: Browser, label: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await openTableMenu(page, T[label].qr_token);
  return page;
}

/** Open the Pay sheet, choose a digital method and report a payment with a reference. */
async function payDigital(page: Page, method: RegExp, reference: string) {
  await page.getByRole("button", { name: "Pay bill" }).click();
  const pay = page.getByRole("dialog", { name: "Pay bill" });
  await pay.getByRole("button", { name: method }).click();
  await expect(pay.getByText("Sample payment details — demo only. Do not send money.")).toBeVisible();
  await pay.getByLabel("Transaction ID from your payment app").fill(reference);
  await pay.getByRole("button", { name: "I've paid" }).click();
  await expect(pay.getByRole("status")).toHaveText("Payment sent — waiting for staff to confirm.");
  return pay;
}

/** The staff confirm sheet of one table's open bill. */
async function openTableBill(staff: Page, label: string) {
  await staff.getByRole("button").filter({ hasText: `Table ${label}` }).click();
  const dialog = staff.getByRole("dialog", { name: new RegExp(`^Table ${label} · Bill no\\. \\d{4}$`) });
  await expect(dialog.getByRole("button", { name: "Confirm received" })).toBeVisible();
  return dialog;
}

const ref = (tag: string) => `${tag}${Date.now()}`; // a fresh reference: reused ones are flagged

test.describe.serial("1. Angeethi family: order, water, Raast, confirm, print, clear", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("karahi and naan, a call for water, Raast with a reference, then Needs clearing → Free", async ({ browser }) => {
    const guest = await guestAt(browser, "T1");
    await guest.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    await guest.getByRole("button", { name: "Add Chicken Karahi 1 kg", exact: true }).click();
    await guest.getByRole("button", { name: "Add Naan", exact: true }).click();
    await guest.getByRole("button", { name: /View order/ }).click();
    await confirmOrder(guest);

    await guest.getByRole("button", { name: "Call waiter" }).click();
    await guest.getByRole("dialog", { name: "Call waiter" }).getByRole("button", { name: "Water, please" }).click();
    await expect(guest.getByRole("status").filter({ hasText: "Waiter called" })).toBeVisible();

    const staff = await staffBrowser(browser, ANGEETHI, "/floor");
    const tile = floorTile(staff, "T1");
    await expect(tile.getByText("Waiter called")).toBeVisible();
    await expect(tile.getByText("Water, please")).toBeVisible();
    await tile.getByRole("button", { name: "Done, T1" }).click();
    await expect(tile.getByText("Ordered")).toBeVisible();

    const reference = ref("RAAST");
    await payDigital(guest, /^Raast QR/, reference);
    await guest.keyboard.press("Escape");
    await expect(tile.getByText("Paying")).toBeVisible();

    await staff.goto(`${OWNER}/bills`);
    await expect(staff.getByText(`Guest paying: Raast QR · ref ${reference.slice(0, 8)}…`)).toBeVisible();
    const dialog = await openTableBill(staff, "T1");
    await expect(dialog.getByRole("radio", { name: /^Raast QR/ })).toBeChecked();
    await expect(dialog.getByText(`Guest claims: Raast QR · ref ${reference}`)).toBeVisible();
    await expect(dialog.getByText(`Check your JazzCash / bank app for ref ${reference} and`)).toBeVisible();
    await dialog.getByRole("button", { name: "Confirm received" }).click();

    await expect(staff).toHaveURL(PRINT);
    await expect(staff.getByText("Sales tax (illustrative) 8% — card, wallet or QR")).toBeVisible();
    await expect(staff.getByText("1 × Chicken Karahi — 1 kg")).toBeVisible();
    await expect(guest.getByText(PAID)).toBeVisible(POLL);

    await staff.goto(`${OWNER}/floor`);
    await expect(tile.getByText("Needs clearing")).toBeVisible();
    await tile.getByRole("button", { name: "Mark cleared, T1" }).click();
    await expect(tile.getByText("Free")).toBeVisible();
  });
});

test.describe.serial("2. Raast, then cash: staff confirm the cash total at 16%", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("the latest claim wins and settles at the standard rate", async ({ browser }) => {
    const guest = await guestAt(browser, "T2");
    const orderId = await orderOne(guest, "Raita");
    const pay = await payDigital(guest, /^Raast QR/, ref("RAAST"));
    await pay.getByRole("button", { name: /^Cash/ }).click();
    const status = pay.getByRole("status");
    await expect(status).toHaveText(/^A waiter is coming to collect Rs\s[\d,]+\.$/);
    const cashTotal = (await status.textContent())!.replace(/^A waiter is coming to collect /, "").replace(/\.$/, "");

    const staff = await staffBrowser(browser, ANGEETHI, "/bills");
    await expect(staff.getByText("Guest paying: cash")).toBeVisible();
    const dialog = await openTableBill(staff, "T2");
    const cash = dialog.getByRole("radio", { name: /^Cash/ });
    await expect(cash).toBeChecked();
    await expect(dialog.locator("label").filter({ has: staff.getByRole("radio", { name: /^Cash/ }) }).getByText("tax 16%")).toBeVisible();
    await expect(dialog.getByText(cashTotal, { exact: true }).first()).toBeVisible();
    await dialog.getByRole("button", { name: "Confirm received" }).click();

    await expect(staff).toHaveURL(PRINT);
    await expect(staff.getByText("Sales tax (illustrative) 16% — cash")).toBeVisible();
    const api = await demoApi("staff", ANGEETHI);
    const bill = await (await api.get(`/api/restaurants/${ANGEETHI}/bills/${billOf(orderId)}`)).json();
    expect([bill.status, bill.payment_method, bill.tax_rate]).toEqual(["settled", "cash", "0.1600"]);
    await api.dispose();
  });
});

test.describe.serial("3. Chai ordered while a payment is pending", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("still due is shown; the first confirm is refused and refreshed", async ({ browser }) => {
    const guest = await guestAt(browser, "T3");
    await orderOne(guest, "Raita");
    await payDigital(guest, /^Raast QR/, ref("RAAST"));
    await guest.keyboard.press("Escape");

    const staff = await (await browser.newContext()).newPage();
    await staffPage(staff, ANGEETHI);
    // No live updates on this screen: the sheet keeps the total staff saw, as on a slow phone.
    await staff.route("**/kitchen/stream", (route) => route.abort());
    await staff.goto(`${OWNER}/bills`);
    const dialog = await openTableBill(staff, "T3");
    await expect(dialog.getByRole("radio", { name: /^Raast QR/ })).toBeChecked();

    await guest.getByRole("link", { name: /Back to Menu/ }).click();
    await orderOne(guest, "Doodh Patti Chai");

    await dialog.getByRole("button", { name: "Confirm received" }).click();
    await expect(dialog.getByText("The bill changed — check the new total")).toBeVisible();
    await expect(dialog.getByText(/^Guest sent Rs\s[\d,]+ · bill is now Rs\s[\d,]+ · Rs\s[\d,]+ still due$/)).toBeVisible();
    await expect(staff).not.toHaveURL(PRINT);
    await expect(dialog.getByText("1 × Doodh Patti Chai")).toBeVisible();

    await dialog.getByRole("button", { name: "Confirm received" }).click();
    await expect(staff).toHaveURL(PRINT);
    await expect(staff.getByText("1 × Doodh Patti Chai")).toBeVisible();
  });
});

test.describe.serial("4. Kehwa counter: pay first, then collect", () => {
  test.beforeAll(() => resetVenue(KEHWA));

  test("nothing reaches the barista until cash is confirmed; Ready, Collected, Undo, Collected", async ({ browser }) => {
    const label = nextPickupLabel(KEHWA, "K");
    const guest = await (await browser.newContext()).newPage();
    await openTableMenu(guest, (await counterTable(KEHWA)).qr_token);
    await expect(guest.getByText("Counter order — pay first, then collect")).toBeVisible();
    await expect(guest.getByRole("button", { name: "Call waiter" })).toHaveCount(0);
    await guest.getByRole("button", { name: "Add Butter Croissant", exact: true }).click();
    await guest.getByRole("button", { name: /View order/ }).click();
    await placeOrder(guest);
    await expect(guest.getByText(label, { exact: true })).toBeVisible();
    await guest.getByRole("button", { name: "Pay bill" }).click();
    const pay = guest.getByRole("dialog", { name: "Pay at the counter or from your phone" });
    await pay.getByRole("button", { name: /^Cash/ }).click();
    await expect(pay.getByRole("status")).toHaveText(/^Pay Rs\s[\d,]+ at the counter\.$/);
    await guest.keyboard.press("Escape");

    const kitchen = await staffBrowser(browser, KEHWA, "/kitchen");
    await expect(kitchen.getByText("0 ORDERS ACTIVE")).toBeVisible();
    await expect(kitchen.getByRole("heading", { name: `PICKUP ${label}` })).toHaveCount(0);
    await expect(kitchen.getByRole("button", { name: "BUMP" })).toHaveCount(0);

    const staff = await staffBrowser(browser, KEHWA, "/bills");
    await staff.getByRole("tab", { name: "Counter" }).click();
    const awaiting = staff.getByRole("region", { name: "Awaiting payment" });
    await expect(awaiting.getByText(label, { exact: true })).toBeVisible();
    await expect(awaiting.getByText("Guest paying: cash")).toBeVisible();
    await awaiting.getByRole("button", { name: `Confirm received for ${label}` }).click();
    const sheet = staff.getByRole("dialog", { name: new RegExp(`^Pickup ${label} · Bill no\\. \\d{4}$`) });
    await expect(sheet.getByRole("radio", { name: /^Cash/ })).toBeChecked();
    await sheet.getByRole("button", { name: "Confirm received" }).click();
    await expect(sheet).toBeHidden();
    await expect(staff.getByRole("region", { name: "Preparing" }).getByText(label, { exact: true })).toBeVisible();
    await expect(guest.getByText("Paid — preparing your order")).toBeVisible(POLL);

    await expect(kitchen.getByRole("heading", { name: `PICKUP ${label}` })).toBeVisible();
    await kitchen.getByRole("button", { name: "BUMP" }).click();
    await expect(guest.getByText(`Ready — collect ${label} at the counter`)).toBeVisible(POLL);

    const ready = staff.getByRole("region", { name: "Ready" });
    await ready.getByRole("button", { name: `Collected ${label}` }).click();
    await ready.getByRole("button", { name: `Undo ${label} collected` }).click();
    await ready.getByRole("button", { name: `Collected ${label}` }).click();
    await expect(ready.getByRole("button", { name: `Undo ${label} collected` })).toBeVisible();
    await expect(guest.getByText("Collected · enjoy!")).toBeVisible(POLL);
  });
});

test.describe.serial("5. An unpaid counter order expires after 30 minutes", () => {
  test.beforeAll(() => resetVenue(KEHWA));

  test("backdated 31 minutes, it leaves the queue", async ({ browser }) => {
    const label = nextPickupLabel(KEHWA, "K");
    const guest = await (await browser.newContext()).newPage();
    await openTableMenu(guest, (await counterTable(KEHWA)).qr_token);
    await guest.getByRole("button", { name: "Add Butter Croissant", exact: true }).click();
    await guest.getByRole("button", { name: /View order/ }).click();
    const orderId = await placeOrder(guest);
    await expect(guest.getByText(label, { exact: true })).toBeVisible();

    const staff = await staffBrowser(browser, KEHWA, "/bills");
    await staff.getByRole("tab", { name: "Counter" }).click();
    const awaiting = staff.getByRole("region", { name: "Awaiting payment" });
    await expect(awaiting.getByText(label, { exact: true })).toBeVisible();

    sql(`UPDATE orders SET placed_at = placed_at - interval '31 minutes' WHERE id = '${orderId}'`);
    await staff.reload();
    await staff.getByRole("tab", { name: "Counter" }).click();
    await expect(awaiting.getByText("None")).toBeVisible();
    await expect(awaiting.getByText(label, { exact: true })).toHaveCount(0);
    await staff.getByRole("tab", { name: "Cancelled" }).click();
    await expect(staff.getByRole("button", { name: `Take late payment for ${label}` })).toBeVisible();

    await guest.reload();
    await expect(guest.getByText("This order was cancelled — please ask at the counter")).toBeVisible();
  });
});

test.describe.serial("6. Device labels, Joined late and a void", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("two family phones, then a late phone that staff void", async ({ browser }) => {
    const phone1 = await guestAt(browser, "F1");
    const first = await orderOne(phone1, "Naan");
    const phone2 = await guestAt(browser, "F1");
    await orderOne(phone2, "Garlic Naan");

    const staff = await staffBrowser(browser, ANGEETHI, "/bills");
    let dialog = await openTableBill(staff, "F1");
    await expect(dialog.getByText("Phone 1", { exact: true })).toBeVisible();
    await expect(dialog.getByText("Phone 2", { exact: true })).toBeVisible();
    await expect(dialog.getByText("Joined late")).toHaveCount(0);
    await staff.keyboard.press("Escape");

    // The family sat down 25 minutes ago.
    const bill = billOf(first);
    sql(`UPDATE bills SET opened_at = opened_at - interval '25 minutes' WHERE id = '${bill}'`);
    sql(`UPDATE orders SET placed_at = placed_at - interval '25 minutes' WHERE bill_id = '${bill}'`);
    const phone3 = await guestAt(browser, "F1");
    const late = await orderOne(phone3, "Cheese Naan");

    await staff.reload();
    dialog = await openTableBill(staff, "F1");
    await expect(dialog.getByText("Phone 3", { exact: true })).toBeVisible();
    await expect(dialog.getByText("Joined late")).toHaveCount(1);
    await dialog.getByRole("button", { name: "Void Phone 3 order" }).click();
    const voidSheet = staff.getByRole("dialog", { name: "Void Phone 3 order" });
    await expect(voidSheet.getByRole("combobox", { name: "Reason" })).toHaveValue("Wrong table");
    await voidSheet.getByRole("button", { name: "Void order" }).click();
    await expect(voidSheet).toBeHidden();
    await expect(dialog.getByText("Voided: Wrong table")).toBeVisible();

    await phone3.goto(`${GUEST}/en/orders/${late}`);
    // The order page says it; the closed Pay sheet carries the same line.
    await expect(phone3.getByText("Removed by staff: Cheese Naan ×1").first()).toBeVisible();
  });
});

test.describe.serial("7. Two staff confirm the same bill", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("one wins; the other sees it is already settled", async ({ browser }) => {
    const guest = await guestAt(browser, "T4");
    const orderId = await orderOne(guest, "Naan");

    const a = await staffBrowser(browser, ANGEETHI, "/bills");
    const b = await (await browser.newContext()).newPage();
    await staffPage(b, ANGEETHI);
    await b.route("**/kitchen/stream", (route) => route.abort()); // b has not seen a's settle yet
    await b.goto(`${OWNER}/bills`);
    const sheetA = await openTableBill(a, "T4");
    const sheetB = await openTableBill(b, "T4");

    await sheetA.getByRole("button", { name: "Confirm received" }).click();
    await expect(a).toHaveURL(PRINT);
    await sheetB.getByRole("button", { name: "Confirm received" }).click();
    await expect(sheetB.getByRole("alert").filter({ hasText: "Bill already settled" })).toBeVisible();
    await expect(sheetB.getByText(/This bill is already settled by /)).toBeVisible();
    await expect(sheetB.getByRole("button", { name: "Confirm received" })).toHaveCount(0);

    const settled = sql(`SELECT count(*) FROM audit_log WHERE event_type = 'bill_settled'
      AND payload->>'bill_id' = '${billOf(orderId)}'`);
    expect(settled).toBe("1");
  });
});

test.describe.serial("8. Pay-it-forward chai", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI, { drainPayForward: true });
    T = await venueTables(ANGEETHI);
  });

  test("a guest buys one; staff give it; the kitchen gets the ticket; none left", async ({ browser }) => {
    const guest = await guestAt(browser, "T5");
    await orderOne(guest, "Pay-it-forward chai");

    const staff = await staffBrowser(browser, ANGEETHI, "/floor");
    await expect(staff.getByText("No chai waiting")).toBeVisible();
    await staff.goto(`${OWNER}/bills`);
    const dialog = await openTableBill(staff, "T5");
    await expect(dialog.getByRole("radio", { name: /^Cash/ })).toBeChecked();
    await dialog.getByRole("button", { name: "Confirm received" }).click();
    await expect(staff).toHaveURL(PRINT);
    await expect(guest.getByText("You bought 1 chai for someone who needs it. Shukriya.")).toBeVisible(POLL);

    await staff.goto(`${OWNER}/floor`);
    await expect(staff.getByText("Pay-it-forward chai: 1 waiting")).toBeVisible();
    const give = staff.getByRole("button", { name: "Give one" });
    await give.click();
    await expect(staff.getByText("Given — the kitchen has the ticket.")).toBeVisible();
    await expect(staff.getByText("No chai waiting")).toBeVisible();
    await expect(give).toBeDisabled();

    const kitchen = await staffBrowser(browser, ANGEETHI, "/kitchen");
    await expect(kitchen.getByRole("heading", { name: "PAY-IT-FORWARD · Chai" })).toBeVisible();
  });
});

test.describe.serial("9. Guest screens at 360 px on slow 3G", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    T = await venueTables(ANGEETHI);
  });

  test("every screen fits and I've paid survives a dropped connection", async ({ browser }) => {
    test.setTimeout(300_000);
    const slow = { timeout: 60_000 };
    const context = await browser.newContext({ viewport: { width: 360, height: 780 } });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    // Chrome DevTools "Slow 3G".
    const slow3g = { offline: false, latency: 400, downloadThroughput: ((500 * 1024) / 8) * 0.8, uploadThroughput: ((500 * 1024) / 8) * 0.8 };
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", slow3g);
    const fits = async (screen: string) => {
      const width = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(width, `${screen} has no horizontal scroll at 360 px`).toBeLessThanOrEqual(360);
      await page.screenshot({ path: `test-results/screens/slow3g-${screen}.png` });
    };

    await page.goto(`${GUEST}/q/${T.T6.qr_token}`, slow);
    await expect(page.getByRole("button", { name: "View Menu" })).toBeVisible(slow);
    await fits("welcome");
    await page.getByRole("button", { name: "View Menu" }).click();
    await expect(page).toHaveURL(/\/en\/menu$/, slow);
    const add = page.getByRole("button", { name: "Add Naan", exact: true });
    await expect(add).toBeVisible(slow);
    await fits("menu");
    await add.click();
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(page.getByRole("dialog", { name: "Your Order" })).toBeVisible();
    await fits("order-sheet");
    const ack = page.getByText("I have spoken with staff and understand the allergen risks");
    if (await ack.isVisible()) await ack.click();
    await page.getByRole("button", { name: "Confirm Order" }).click();
    await expect(page).toHaveURL(/\/en\/orders\/[0-9a-f-]{36}$/, slow);
    const orderId = page.url().split("/").pop()!;
    await expect(page.getByText("Received by Kitchen")).toBeVisible(slow);
    await expect(page.getByRole("button", { name: "Pay bill" })).toBeVisible(slow);
    await fits("order");

    await page.getByRole("button", { name: "Call waiter" }).click();
    await expect(page.getByRole("dialog", { name: "Call waiter" })).toBeVisible();
    await fits("call-waiter");
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Pay bill" }).click();
    const pay = page.getByRole("dialog", { name: "Pay bill" });
    await expect(pay.getByRole("button", { name: /^JazzCash \/ Easypaisa/ })).toBeVisible();
    await fits("pay");
    await pay.getByRole("button", { name: /^JazzCash \/ Easypaisa/ }).click();
    await expect(pay.getByText("Sample payment details — demo only. Do not send money.")).toBeVisible();
    const reference = ref("JC");
    const field = pay.getByLabel("Transaction ID from your payment app");
    await field.fill(reference);
    await fits("pay-wallet");

    const bill = billOf(orderId);
    const claims = () =>
      sql(`SELECT count(*) FROM audit_log WHERE event_type = 'payment_claimed' AND payload->>'bill_id' = '${bill}'`);
    const paid = pay.getByRole("button", { name: "I've paid" });
    const lost = pay.getByRole("alert").filter({ hasText: "Couldn't reach the restaurant — tap again" });

    // Offline: the tap never leaves the phone; the typed reference stays.
    await cdp.send("Network.emulateNetworkConditions", { ...slow3g, offline: true });
    await paid.click();
    await expect(lost).toBeVisible(slow);
    await expect(field).toHaveValue(reference);
    expect(claims()).toBe("0");

    // Back online, but the answer to the next tap is lost: the claim lands, the phone sees an error.
    await cdp.send("Network.emulateNetworkConditions", slow3g);
    await page.route(
      "**/api/guest/bill/payment**",
      async (route) => {
        await route.fetch();
        await route.abort("connectionreset");
      },
      { times: 1 },
    );
    await paid.click();
    await expect.poll(claims, slow).toBe("1");
    await expect(lost).toBeVisible(slow);

    // The guest taps again: the same claim, not a second one.
    await paid.click();
    await expect(pay.getByRole("status")).toHaveText("Payment sent — waiting for staff to confirm.", slow);
    expect(claims()).toBe("1");
    await page.keyboard.press("Escape");

    const api = await demoApi("staff", ANGEETHI);
    const detail = await (await api.get(`/api/restaurants/${ANGEETHI}/bills/${bill}`)).json();
    expect(detail.claim.reference).toBe(reference);
    const wallet = detail.methods.find((m: { method: string }) => m.method === "wallet");
    const res = await api.post(`/api/restaurants/${ANGEETHI}/bills/${bill}/settle`, {
      data: { payment_method: "wallet", payment_reference: reference, expected_method: "wallet", expected_total: wallet.total },
    });
    expect(res.ok()).toBeTruthy();
    await api.dispose();
    await expect(page.getByText(PAID)).toBeVisible(slow);
    await fits("paid");
    await context.close();
  });
});
