import { VISIT_ENDED } from "./pay";

/** Same cap as MAX_ITEMS_PER_ORDER in services/api/src/schemas/orders.py (portions, all lines). */
export const MAX_ITEMS_PER_ORDER = 30;

/** The API's 429 detail while a phone is locked out after wrong table numbers (routers/orders.py). */
export const TOO_MANY_TRIES = "Too many tries. Please wait a minute and ask your waiter.";

/** Mirrors GuestSessionStatusResponse: whether this phone may order at its table now. */
export interface GuestStatus {
  id: string;
  sitting_open: boolean;
  code_required: boolean;
}

/** What the order bar shows: normal ordering, waiting for a waiter to open the table, or the visit is over. */
export type TableMode = "open" | "waiting" | "closed";

/** A closed table means "thanks for visiting" to a phone that ordered this visit, "a waiter is coming" to a new one. */
export const tableMode = (status: GuestStatus, ordered: boolean): TableMode =>
  status.sitting_open ? "open" : ordered ? "closed" : "waiting";

export type OrderOutcome =
  | "not_open"
  | "code"
  | "locked"
  | "too_fast"
  | "too_big"
  | "ended"
  | "allergen"
  | "unavailable"
  | "failed";

/** What a refused POST /api/orders means for the guest; never a raw status or error code on screen. */
export function orderOutcome(status: number, body: unknown): OrderOutcome {
  const detail = (body as { detail?: unknown } | null)?.detail;
  const error = (detail as { error?: unknown } | null)?.error;
  if (status === 403 && error === "code_required") return "code";
  if (status === 429) return detail === TOO_MANY_TRIES ? "locked" : "too_fast";
  if (status === 409) {
    if (error === "table_not_open") return "not_open";
    if (error === "allergen_ack_required") return "allergen";
    if (error === "unavailable_items") return "unavailable";
    if (detail === VISIT_ENDED) return "ended";
  }
  if (status === 422 && Array.isArray(detail) && detail.some((d) => String(d?.msg).includes("big order"))) {
    return "too_big";
  }
  return "failed";
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

const ORDERED_KEY = "mise_ordered_session";

/** Marks that this phone ordered in guest session `sessionId`; a new scan is a new session. */
export function markOrdered(sessionId: string): void {
  try {
    localStorage.setItem(ORDERED_KEY, sessionId);
  } catch {
    // private mode: the closed-table screen falls back to the waiting bar
  }
}

export function hasOrdered(sessionId: string): boolean {
  try {
    return localStorage.getItem(ORDERED_KEY) === sessionId;
  } catch {
    return false;
  }
}

const RESTORED_KEY = "mise_restored_order";

/** True once per declined order, so going back to its page never adds the dishes twice. */
export function claimRestore(orderId: string): boolean {
  try {
    if (localStorage.getItem(RESTORED_KEY) === orderId) return false;
    localStorage.setItem(RESTORED_KEY, orderId);
  } catch {
    // no storage: restore anyway
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
