import { VISIT_ENDED } from "./pay";

/** Same cap as MAX_ITEMS_PER_ORDER in services/api/src/schemas/orders.py (portions, all lines). */
export const MAX_ITEMS_PER_ORDER = 30;

/** The API's 429 detail while a phone is locked out after wrong table numbers (routers/orders.py). */
export const TOO_MANY_TRIES = "Too many tries. Please wait a minute and ask your waiter.";
/** The API's 429 detail once a visit has had too many wrong table numbers from all phones. */
export const ASK_WAITER = "Please ask your waiter to help you order.";

/**
 * What the order bar shows (GuestSessionStatusResponse.table_state): normal ordering, waiting for a
 * waiter to open the table, thanks for visiting (this phone ordered on a visit that ended), or scan again.
 */
export type TableMode = "open" | "waiting" | "closed" | "ended";

/** Mirrors GuestSessionStatusResponse: whether this phone may order at its table now. */
export interface GuestStatus {
  id: string;
  table_state: TableMode;
  code_required: boolean;
}

/**
 * Milliseconds until the next table status check, or null to stop. Only a waiting table (or an
 * unknown one) is checked again; errors back off 5, 10, 20, then 30 s.
 */
export function nextStatusCheck(r: { state?: TableMode; failures: number; signedOut?: boolean }): number | null {
  if (r.signedOut || (r.state && r.state !== "waiting")) return null;
  return Math.min(5000 * 2 ** r.failures, 30_000);
}

export type OrderOutcome =
  | "not_open"
  | "code"
  | "locked"
  | "ask_waiter"
  | "too_fast"
  | "too_big"
  | "ended"
  | "allergen"
  | "unavailable"
  | "choice_gone"
  | "choices_changed"
  | "already_sent"
  | "failed";

/** What a refused POST /api/orders means for the guest; never a raw status or error code on screen. */
export function orderOutcome(status: number, body: unknown): OrderOutcome {
  const detail = (body as { detail?: unknown } | null)?.detail;
  const error = (detail as { error?: unknown } | null)?.error;
  if (status === 403 && error === "code_required") return "code";
  if (status === 429) return detail === TOO_MANY_TRIES ? "locked" : detail === ASK_WAITER ? "ask_waiter" : "too_fast";
  if (status === 409) {
    if (error === "table_not_open") return "not_open";
    if (error === "allergen_ack_required") return "allergen";
    if (error === "unavailable_items") return "unavailable";
    if (error === "unavailable_choices") return "choice_gone";
    if (error === "already_sent") return "already_sent";
    if (detail === VISIT_ENDED) return "ended";
  }
  if (status === 422 && error === "choices_changed") return "choices_changed";
  if (status === 422 && Array.isArray(detail) && detail.some((d) => String(d?.msg).includes("big order"))) {
    return "too_big";
  }
  return "failed";
}

const detailOf = (body: unknown) =>
  ((body as { detail?: unknown } | null)?.detail ?? null) as Record<string, unknown> | null;

/** The order this phone already sent under the cart's key (409 already_sent). */
export function sentOrderId(body: unknown): string | null {
  const id = detailOf(body)?.order_id;
  return typeof id === "string" ? id : null;
}

/** The dishes the server refused as sold out (409 unavailable_items). */
export function soldOutIds(body: unknown): string[] {
  const items = detailOf(body)?.unavailable_items;
  return Array.isArray(items) ? items.map((i) => String(i?.menu_item_id)) : [];
}

/** The choices the server refused as sold out (409 unavailable_choices). */
export function soldOutChoices(body: unknown): { id: string; label: string }[] {
  const gone = detailOf(body)?.unavailable_choices;
  return Array.isArray(gone) ? gone.map((c) => ({ id: String(c?.choice_id), label: String(c?.label) })) : [];
}

/** The dish whose choices changed under the guest (422 choices_changed). */
export function changedDish(body: unknown): string | null {
  const id = detailOf(body)?.menu_item_id;
  return typeof id === "string" ? id : null;
}

export const cartQuantity = (items: { quantity: number }[]) => items.reduce((s, i) => s + i.quantity, 0);

/** The 4-digit table number after typing or pasting `raw` into box `index`; no gaps, extra digits dropped. */
export function typeDigits(code: string, index: number, raw: string): string {
  const at = Math.min(index, code.length);
  let digits = raw.replace(/\D/g, "");
  // Typing over a filled box gives "old+new": keep only the new digit.
  if (digits.length === 2 && code[at] !== undefined && digits[0] === code[at]) digits = digits.slice(1);
  return (code.slice(0, at) + digits).slice(0, 4);
}

// The table number lives only in memory for this visit (never in storage), so a retry resends it.
let tableNumber: string | null = null;
export const rememberedNumber = () => tableNumber;
export const rememberNumber = (n: string | null) => {
  tableNumber = n;
};

const RESTORED_KEY = "mise_restored_orders";
// Order ids only (never a session id); memory backs up storage in private mode.
const restored = new Set<string>();

/** True once per declined order, so going back to any of their pages never adds the dishes twice. */
export function claimRestore(orderId: string): boolean {
  try {
    for (const id of JSON.parse(sessionStorage.getItem(RESTORED_KEY) ?? "[]") as string[]) restored.add(id);
  } catch {
    // no storage or a bad value: memory alone
  }
  if (restored.has(orderId)) return false;
  restored.add(orderId);
  try {
    sessionStorage.setItem(RESTORED_KEY, JSON.stringify([...restored].slice(-20)));
  } catch {
    // no storage: memory alone
  }
  return true;
}

export type OrderStage = "confirming" | "cooking" | "ready" | "declined" | "closed" | "cancelled";

/** The guest's view of an order's status and, when cancelled, the guest-safe reason. */
export function orderStage(status: string, cancelReason?: string | null): OrderStage {
  if (status === "pending_approval") return "confirming";
  if (status === "bumped") return "ready";
  if (status === "cancelled") {
    if (cancelReason === "declined") return "declined";
    if (cancelReason === "table_closed") return "closed";
    return "cancelled";
  }
  return "cooking";
}
