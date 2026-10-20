import { expect, request, test, type APIRequestContext } from "@playwright/test";

const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const GUEST = process.env.GUEST_URL ?? "http://127.0.0.1:3000";
const OWNER = process.env.OWNER_URL ?? "http://127.0.0.1:3001";
const SLUG = process.env.RESTAURANT_SLUG ?? "trattoria-da-mario";

async function demoApi(role: "owner" | "staff"): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: API });
  const res = await ctx.post("/api/auth/demo-login", { data: { role } });
  expect(res.ok(), "demo-login requires DEMO_MODE=true").toBeTruthy();
  return ctx;
}

// One story, in order: guest orders from a table QR, the kitchen sees and bumps it,
// the owner reads the brief and runs a what-if.
test.describe.serial("guest to kitchen to owner", () => {
  let orderId = "";

  test.beforeAll(async () => {
    // Bump any open tickets so the kitchen shows only the order this test places.
    const staff = await demoApi("staff");
    const open = await (await staff.get(`/api/restaurants/${SLUG}/kitchen/orders`)).json();
    for (const o of open.orders.filter((o: { status: string }) => o.status === "placed")) {
      await staff.post(`/api/restaurants/${SLUG}/kitchen/orders/${o.id}/bump`);
    }
    await staff.dispose();
  });

  test("guest scans the table QR, sees the menu and places an order", async ({ page }) => {
    const info = await (await (await request.newContext({ baseURL: API })).get("/api/demo/info")).json();

    await page.goto(`${GUEST}/q/${info.qr_token}`);
    await page.getByRole("button", { name: "View Menu" }).click();

    await expect(page).toHaveURL(/\/en\/menu$/);
    await expect(page.getByRole("heading", { name: "Trattoria da Mario" })).toBeVisible();
    await expect(page.getByText(`Table: ${info.table_label}`)).toBeVisible();

    await page.getByRole("button", { name: "Add" }).first().click();
    await page.getByRole("button", { name: /Review & Order/ }).click();

    const ack = page.getByText("I have spoken with staff and understand the allergen risks");
    if (await ack.isVisible()) await ack.click();
    await page.getByRole("button", { name: "Confirm Order" }).click();

    await expect(page).toHaveURL(/\/en\/orders\/[0-9a-f-]{36}$/);
    orderId = page.url().split("/").pop() ?? "";
    await expect(page.getByText("Received by Kitchen")).toBeVisible();
  });

  test("kitchen shows the ticket and bumps it", async ({ page }) => {
    expect(orderId).not.toBe("");
    await page.goto(`${OWNER}/login`);
    await page.getByRole("button", { name: "Open kitchen display (demo staff)" }).click();
    await expect(page).toHaveURL(/\/kitchen$/);

    const bump = page.getByRole("button", { name: "BUMP" });
    await expect(bump).toHaveCount(1);
    await bump.click();
    await expect(bump).toHaveCount(0);

    const staff = await demoApi("staff");
    const orders = await (await staff.get(`/api/restaurants/${SLUG}/kitchen/orders`)).json();
    const ours = orders.orders.find((o: { id: string }) => o.id === orderId);
    expect(ours?.status).toBe("bumped");
    await staff.dispose();
  });

  test("owner sees the revenue brief and runs a what-if", async ({ page }) => {
    await page.goto(`${OWNER}/login`);
    await page.getByRole("button", { name: "Enter as demo owner" }).click();
    await expect(page).not.toHaveURL(/\/login$/);

    await page.goto(`${OWNER}/brief`);
    await expect(page.getByRole("heading", { name: /Revenue Brief/ })).toBeVisible();
    await expect(page.getByText("Average order value")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ranked actions" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "7-day demand forecast" })).toBeVisible();

    await page.goto(`${OWNER}/ai`);
    await page.getByLabel("Demand surge").check();
    await page.getByRole("button", { name: "Calculate" }).click();
    await expect(page.getByText("Change / week")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Assumptions" })).toBeVisible();
  });
});
