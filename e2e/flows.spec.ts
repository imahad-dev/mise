import { expect, request, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";

const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const GUEST = process.env.GUEST_URL ?? "http://127.0.0.1:3000";
const OWNER = process.env.OWNER_URL ?? "http://127.0.0.1:3001";
const ANGEETHI = "angeethi-house";
const KEHWA = "kehwa-and-crumb";

type Role = "owner" | "staff";

async function demoApi(role: Role, venue?: string): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: API });
  const res = await ctx.post("/api/auth/demo-login", { data: venue ? { role, venue } : { role } });
  expect(res.ok(), "demo-login requires DEMO_MODE=true").toBeTruthy();
  return ctx;
}

async function demoInfo() {
  const ctx = await request.newContext({ baseURL: API });
  const info = await (await ctx.get("/api/demo/info")).json();
  await ctx.dispose();
  return info as { venues: { slug: string; name: string; qr_token: string; table_label: string }[] };
}

/** Sign the browser context in as demo staff of one venue (cookie set through the owner app). */
async function staffPage(page: Page, venue: string) {
  const res = await page.request.post(`${OWNER}/api/auth/demo-login`, { data: { role: "staff", venue } });
  expect(res.ok()).toBeTruthy();
}

async function openTableMenu(page: Page, qrToken: string) {
  await page.goto(`${GUEST}/q/${qrToken}`);
  await page.getByRole("button", { name: "View Menu" }).click();
  await expect(page).toHaveURL(/\/en\/menu$/);
}

async function confirmOrder(page: Page) {
  const ack = page.getByText("I have spoken with staff and understand the allergen risks");
  if (await ack.isVisible()) await ack.click();
  await page.getByRole("button", { name: "Confirm Order" }).click();
  await expect(page).toHaveURL(/\/en\/orders\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Received by Kitchen")).toBeVisible();
  return page.url().split("/").pop() ?? "";
}

// One story, in order: a guest at Angeethi House orders a sized dish and asks for the bill, the
// kitchen bumps it, staff settle the bill and print the sample bill, the owner switches venues and
// reads the brief, a café guest orders, and staff of one venue cannot see the other.
test.describe.serial("two venues: guest, kitchen, bills, owner", () => {
  let orderId = "";
  let guestState: Awaited<ReturnType<BrowserContext["storageState"]>> | undefined;

  test.beforeAll(async () => {
    // Start clean: bump open tickets and settle open bills so only this story's show up.
    for (const slug of [ANGEETHI, KEHWA]) {
      const staff = await demoApi("staff", slug);
      const open = await (await staff.get(`/api/restaurants/${slug}/kitchen/orders`)).json();
      for (const o of open.orders.filter((o: { status: string }) => o.status === "placed")) {
        await staff.post(`/api/restaurants/${slug}/kitchen/orders/${o.id}/bump`);
      }
      const bills = await (await staff.get(`/api/restaurants/${slug}/bills?status=open`)).json();
      for (const b of bills.bills) {
        const res = await staff.post(`/api/restaurants/${slug}/bills/${b.id}/settle`, {
          data: { payment_method: "cash" },
        });
        expect(res.ok(), `settle open bill ${b.id}`).toBeTruthy();
      }
      await staff.dispose();
    }
  });

  test("guest at Angeethi House orders a sized karahi and requests the bill", async ({ page }) => {
    const venue = (await demoInfo()).venues.find((v) => v.slug === ANGEETHI)!;
    await openTableMenu(page, venue.qr_token);
    await expect(page.getByRole("heading", { name: "Angeethi House" })).toBeVisible();
    await expect(page.getByText(`Table: ${venue.table_label}`)).toBeVisible();
    await expect(page.getByText("Prices exclude sales tax, which is added to your bill.")).toBeVisible();
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({ path: "test-results/screens/guest-menu-phone.png", fullPage: true });

    await page.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    const size = page.getByRole("button", { name: "Add Chicken Karahi 1 kg", exact: true });
    await expect(size).toBeVisible();
    await page.screenshot({ path: "test-results/screens/size-sheet-phone.png" });
    await size.click();
    await expect(size).toBeHidden();
    await page.getByRole("button", { name: "Add Naan", exact: true }).click();

    const orderBar = page.getByRole("button", { name: /View order/ });
    await orderBar.click();
    // Order sheet is a native modal dialog: Esc closes it and focus returns to the bar.
    const sheet = page.getByRole("dialog", { name: "Your Order" });
    await expect(sheet).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(orderBar).toBeFocused();
    await orderBar.click();
    await page.screenshot({ path: "test-results/screens/order-sheet-phone.png" });

    orderId = await confirmOrder(page);
    await page.getByRole("button", { name: "Request bill" }).click();
    await expect(page.getByText("Bill requested — a waiter will bring it to your table.")).toBeVisible();
    guestState = await page.context().storageState();
  });

  test("kitchen shows the 1 kg karahi and bumps it", async ({ page }) => {
    expect(orderId).not.toBe("");
    await page.goto(`${OWNER}/login`);
    await page.getByRole("button", { name: "Open kitchen display (demo staff)" }).click();
    await expect(page).toHaveURL(/\/kitchen$/);

    const bump = page.getByRole("button", { name: "BUMP" });
    await expect(bump).toHaveCount(1);
    await expect(page.getByText("1 kg")).toBeVisible();
    await page.screenshot({ path: "test-results/screens/kitchen-desktop.png", fullPage: true });
    await bump.click();
    await expect(bump).toHaveCount(0);

    const staff = await demoApi("staff", ANGEETHI);
    const orders = await (await staff.get(`/api/restaurants/${ANGEETHI}/kitchen/orders`)).json();
    expect(orders.orders.find((o: { id: string }) => o.id === orderId)?.status).toBe("bumped");
    await staff.dispose();
  });

  test("staff settle the requested bill by card and print the sample bill", async ({ page, browser }) => {
    await staffPage(page, ANGEETHI);
    await page.goto(`${OWNER}/bills`);
    await page.getByRole("button", { name: /Bill requested/ }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Cash or bank transfer")).toBeVisible();
    await expect(dialog.getByText("Card, wallet or QR")).toBeVisible();
    await expect(dialog.getByText(/Tax 16% ·/)).toBeVisible();
    await expect(dialog.getByText(/Tax 8% ·/)).toBeVisible();
    await dialog.getByLabel("Card", { exact: true }).check();
    await dialog.getByLabel("Reference (optional)").fill("AUTH1");
    await dialog.getByRole("button", { name: "Mark paid" }).click();

    await expect(page).toHaveURL(/\/bills\/[0-9a-f-]{36}\/print\?venue=angeethi-house$/);
    await expect(page.getByText(/^Bill no\. \d{4}$/)).toBeVisible();
    await expect(page.getByText("Sales tax (illustrative) 8% — card, wallet or QR")).toBeVisible();
    await expect(
      page.getByText("Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority."),
    ).toBeVisible();
    await expect(page.getByText("1 × Chicken Karahi — 1 kg")).toBeVisible();
    await page.screenshot({ path: "test-results/screens/sample-bill.png", fullPage: true });

    // The guest's order page shows the paid bill.
    expect(guestState).toBeDefined();
    const guest = await browser.newContext({ storageState: guestState });
    const guestPage = await guest.newPage();
    await guestPage.goto(`${GUEST}/en/orders/${orderId}`);
    await expect(guestPage.getByText(/^Paid · Bill no\. \d{4} · thank you$/)).toBeVisible();
    await guest.close();
  });

  test("owner switches venue and reads the brief and a what-if", async ({ page }) => {
    await page.goto(`${OWNER}/login`);
    await page.getByRole("button", { name: "Enter as demo owner" }).click();
    await expect(page).not.toHaveURL(/\/login$/);

    const switcher = page.getByRole("combobox", { name: "Venue" });
    await expect(switcher.getByRole("option")).toHaveText([/Angeethi House/, /Kehwa & Crumb/]);
    await switcher.selectOption(KEHWA);
    await expect(page.getByText("Real-time kitchen stream for restaurant: Kehwa & Crumb")).toBeVisible();

    await page.goto(`${OWNER}/brief`);
    await expect(switcher).toHaveValue(KEHWA);
    await expect(page.getByRole("heading", { name: /Revenue Brief/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Payments and tax" })).toBeVisible();
    await expect(page.getByText("Average order value")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ranked actions" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "7-day demand forecast" })).toBeVisible();
    await page.screenshot({ path: "test-results/screens/owner-brief-desktop.png", fullPage: true });

    await page.goto(`${OWNER}/ai`);
    await page.getByLabel("Demand surge").check();
    await page.getByRole("button", { name: "Calculate" }).click();
    await expect(page.getByText("Change / week")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Assumptions" })).toBeVisible();
  });

  test("café guest orders a regular cappuccino; Kehwa kitchen shows it", async ({ page, browser }) => {
    const venue = (await demoInfo()).venues.find((v) => v.slug === KEHWA)!;
    await openTableMenu(page, venue.qr_token);
    await expect(page.getByRole("heading", { name: "Kehwa & Crumb" })).toBeVisible();
    await page.getByRole("button", { name: "Add Cappuccino", exact: true }).click();
    await page.getByRole("button", { name: "Add Cappuccino Regular", exact: true }).click();
    await page.getByRole("button", { name: /View order/ }).click();
    await confirmOrder(page);

    const kitchen = await browser.newContext();
    const kds = await kitchen.newPage();
    await staffPage(kds, KEHWA);
    await kds.goto(`${OWNER}/kitchen`);
    await expect(kds.getByRole("button", { name: "BUMP" })).toHaveCount(1);
    await expect(kds.getByText("Cappuccino")).toBeVisible();
    await expect(kds.getByText("Regular")).toBeVisible();
    await kitchen.close();
  });

  test("staff of one venue cannot read the other venue", async () => {
    const staff = await demoApi("staff", KEHWA);
    const res = await staff.get(`/api/restaurants/${ANGEETHI}/kitchen/orders`);
    expect(res.status()).toBe(404);
    await staff.dispose();
  });
});
