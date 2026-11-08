import { execFileSync } from "node:child_process";
import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

export const API = process.env.API_URL ?? "http://127.0.0.1:8000";
export const GUEST = process.env.GUEST_URL ?? "http://127.0.0.1:3000";
export const OWNER = process.env.OWNER_URL ?? "http://127.0.0.1:3001";
export const ANGEETHI = "angeethi-house";
export const KEHWA = "kehwa-and-crumb";

type Role = "owner" | "staff";

export async function demoApi(role: Role, venue?: string): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: API });
  const res = await ctx.post("/api/auth/demo-login", { data: venue ? { role, venue } : { role } });
  expect(res.ok(), "demo-login requires DEMO_MODE=true").toBeTruthy();
  return ctx;
}

export async function demoInfo() {
  const ctx = await request.newContext({ baseURL: API });
  const info = await (await ctx.get("/api/demo/info")).json();
  await ctx.dispose();
  return info as { venues: { slug: string; name: string; qr_token: string; table_label: string }[] };
}

/** Sign the browser context in as demo staff of one venue (cookie set through the owner app). */
export async function staffPage(page: Page, venue: string) {
  const res = await page.request.post(`${OWNER}/api/auth/demo-login`, { data: { role: "staff", venue } });
  expect(res.ok()).toBeTruthy();
}

export async function openTableMenu(page: Page, qrToken: string) {
  await page.goto(`${GUEST}/q/${qrToken}`);
  await page.getByRole("button", { name: "View Menu" }).click();
  await expect(page).toHaveURL(/\/en\/menu$/);
}

/** Tick the allergen acknowledgement when the open order sheet asks for it. */
export async function acknowledgeAllergens(page: Page) {
  const ack = page.getByText("I have spoken with staff and understand the allergen risks");
  if (await ack.isVisible()) await ack.click();
}

/** Confirm the cart; returns the order id from the order page's URL. */
export async function placeOrder(page: Page) {
  await acknowledgeAllergens(page);
  await page.getByRole("button", { name: "Confirm Order" }).click();
  await expect(page).toHaveURL(/\/en\/orders\/[0-9a-f-]{36}$/);
  return page.url().split("/").pop() ?? "";
}

/** Text on screen, not its copy in the order page's screen-reader live region (`sr-only`). */
export const shown = (page: Page, text: string) => page.getByText(text).and(page.locator(":not(.sr-only)"));

/** Confirm a table order and wait until the kitchen has it; a visit's first order is approved by staff first. */
export async function confirmOrder(page: Page) {
  const id = await placeOrder(page);
  if (sql(`SELECT status FROM orders WHERE id = '${id}'`) === "pending_approval") {
    await expect(shown(page, "Sent! Your waiter is confirming your order.")).toBeVisible();
    await approveOrder(id);
  }
  await expect(shown(page, "Confirmed — it's being cooked")).toBeVisible();
  return id;
}

/** Add one dish without sizes, open the order sheet and confirm it. */
export async function orderOne(page: Page, dish: string) {
  await page.getByRole("button", { name: `Add ${dish}`, exact: true }).click();
  await page.getByRole("button", { name: /View order/ }).click();
  return confirmOrder(page);
}

const docker = (args: string[]) => execFileSync("docker", ["compose", ...args], { encoding: "utf8" }).trim();

/**
 * One SQL statement against the stack's database, as in scripts/verify_phase1.sh: credentials
 * come from the postgres container's own environment (compose defaults), never from .env.
 * Used to read and backdate rows; there are no test-only endpoints.
 */
export const sql = (query: string) =>
  docker(["exec", "-T", "postgres", "sh", "-c", 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$0"', query]);

/** Per-IP demo-login limits would block repeated runs from one machine (as in verify_phase1.sh). */
export const clearDemoLimits = () =>
  docker(["exec", "-T", "redis", "sh", "-c", "redis-cli --scan --pattern 'rate_limit:demo*' | xargs -r redis-cli DEL"]);

export interface VenueTable {
  id: string;
  label: string;
  qr_token: string;
  kind: "table" | "counter";
}

/** Every table and counter QR of a venue, by label (owner route). */
export async function venueTables(slug: string): Promise<Record<string, VenueTable>> {
  const owner = await demoApi("owner");
  const res = await owner.get(`/api/restaurants/${slug}/tables`);
  expect(res.ok()).toBeTruthy();
  const tables = (await res.json()) as VenueTable[];
  await owner.dispose();
  return Object.fromEntries(tables.map((t) => [t.label, t]));
}

export const counterTable = async (slug: string) =>
  Object.values(await venueTables(slug)).find((t) => t.kind === "counter")!;

/** The pickup label the venue's next counter order gets today ("K-007"). */
export function nextPickupLabel(slug: string, prefix: string) {
  const max = sql(
    `SELECT coalesce(max(b.pickup_no), 0) FROM bills b JOIN restaurant r ON r.id = b.restaurant_id
     WHERE r.slug = '${slug}' AND b.pickup_day = (now() AT TIME ZONE r.timezone)::date`,
  );
  return `${prefix}-${String(Number(max) + 1).padStart(3, "0")}`;
}

/** The bill an order is on. */
export const billOf = (orderId: string) => sql(`SELECT bill_id FROM orders WHERE id = '${orderId}'`);

/**
 * Put a venue back to a quiet service through the staff API: cancel unpaid counter orders,
 * settle open table bills at their cash total, optionally hand out every waiting pay-it-forward
 * chai, bump every kitchen ticket, collect ready pickups, resolve calls, close every open table
 * and clear every table.
 */
export async function resetVenue(slug: string, opts: { drainPayForward?: boolean } = {}) {
  clearDemoLimits(); // stories run back to back: a fresh demo-login budget for each
  const staff = await demoApi("staff", slug);
  const base = `/api/restaurants/${slug}`;
  const json = async (path: string) => {
    const res = await staff.get(`${base}${path}`);
    expect(res.ok(), `GET ${path}`).toBeTruthy();
    return res.json();
  };
  for (const b of (await json("/bills?status=open&kind=counter")).bills) {
    const res = await staff.post(`${base}/bills/${b.id}/cancel`, { data: { reason: "e2e clean-up" } });
    expect(res.ok(), `cancel counter bill ${b.id}`).toBeTruthy();
  }
  for (const b of (await json("/bills?status=open&kind=table")).bills) {
    const bill = await json(`/bills/${b.id}`);
    const res = await staff.post(`${base}/bills/${b.id}/settle`, {
      data: { payment_method: "cash", expected_method: "cash", expected_total: bill.preview_standard.total },
    });
    expect(res.ok(), `settle open bill ${b.id}`).toBeTruthy();
  }
  if (opts.drainPayForward) {
    for (let i = 0; i < 100; i++) {
      const res = await staff.post(`${base}/pay-forward/give`, {
        data: { quantity: 1, idempotency_key: `e2e-drain-${Date.now()}-${i}` },
      });
      if (res.status() === 409) break; // "None waiting"
      expect(res.ok(), "give one").toBeTruthy();
    }
  }
  for (const o of (await json("/kitchen/orders")).orders.filter((o: { status: string }) => o.status === "placed")) {
    await staff.post(`${base}/kitchen/orders/${o.id}/bump`);
  }
  for (const b of (await json("/bills?status=settled&kind=counter&queue=true")).bills) {
    if (b.order_id && b.order_status === "bumped" && !b.collected_at) {
      await staff.post(`${base}/orders/${b.order_id}/collect`);
    }
  }
  for (const t of await floorTiles(staff, slug)) {
    if (t.call_id) await staff.post(`${base}/service-calls/${t.call_id}/resolve`);
    if (t.sitting_open) {
      // Settled bills closed their sittings; this closes the rest and cancels their waiting orders.
      const res = await staff.delete(`${base}/tables/${t.table_id}/sitting`);
      expect(res.ok(), `close table ${t.label}`).toBeTruthy();
    }
    if (t.state !== "free") {
      const res = await staff.post(`${base}/tables/${t.table_id}/clear`, { data: { force: true } });
      expect(res.ok(), `clear table ${t.label}`).toBeTruthy();
    }
  }
  await staff.dispose();
}

interface Tile {
  table_id: string;
  label: string;
  state: string;
  sitting_open: boolean;
  pending_order_ids: string[];
  call_id: string | null;
}

/** The Floor tiles of a venue (staff route). */
export async function floorTiles(staff: APIRequestContext, slug: string): Promise<Tile[]> {
  const res = await staff.get(`/api/restaurants/${slug}/floor`);
  expect(res.ok(), "GET floor").toBeTruthy();
  return (await res.json()).tiles;
}

/** Staff open a table for ordering, as "Open table" on the Floor; an already open table stays open. */
export async function openTable(slug: string, label: string) {
  const staff = await demoApi("staff", slug);
  const tile = (await floorTiles(staff, slug)).find((t) => t.label === label)!;
  if (!tile.sitting_open) {
    const res = await staff.post(`/api/restaurants/${slug}/tables/${tile.table_id}/sitting`);
    expect(res.ok(), `open table ${label}`).toBeTruthy();
  }
  await staff.dispose();
}

/** Staff approve a waiting first order, as "Approve" on its Floor tile (every order the tile shows). */
export async function approveOrder(orderId: string) {
  const [slug, tableId] = sql(
    `SELECT r.slug || '|' || o.table_id FROM orders o JOIN restaurant r ON r.id = o.restaurant_id WHERE o.id = '${orderId}'`,
  ).split("|");
  const staff = await demoApi("staff", slug);
  const tile = (await floorTiles(staff, slug)).find((t) => t.table_id === tableId)!;
  expect(tile.pending_order_ids).toContain(orderId);
  const res = await staff.post(`/api/restaurants/${slug}/tables/${tableId}/approve`, {
    data: { order_ids: tile.pending_order_ids },
  });
  expect(res.ok(), `approve ${orderId}`).toBeTruthy();
  await staff.dispose();
}

/** The Floor tile of one table. */
export const floorTile = (page: Page, label: string) =>
  page.getByRole("listitem").filter({ has: page.getByText(label, { exact: true }) });

/** Open a dish's page from its + button and add it with these picks (radio or checkbox names). */
export async function addWithChoices(page: Page, dish: string, picks: string[]) {
  await page.getByRole("button", { name: `Add ${dish}`, exact: true }).click();
  const sheet = page.getByRole("dialog", { name: dish });
  await expect(sheet).toBeVisible();
  for (const pick of picks) await sheet.getByText(pick, { exact: true }).click();
  await sheet.getByRole("button", { name: /Add to order/ }).click();
  await expect(sheet).toBeHidden();
}
