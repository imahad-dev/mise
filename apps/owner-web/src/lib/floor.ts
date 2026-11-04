/** Mirrors services/api/src/schemas/floor.py. Decimals arrive as strings. */
export type FloorState = "free" | "seated" | "ordered" | "served" | "paying" | "needs_clearing" | "called" | "approval_needed";
export type FloorLevel = "none" | "amber" | "red";

export interface FloorTile {
  table_id: string;
  label: string;
  state: FloorState;
  level: FloorLevel;
  since: string | null;
  reason: string | null;
  reason_label: string | null;
  running_total: string | null;
  bill_id: string | null;
  call_id: string | null;
  sitting_open: boolean;
  waiting_for_open: boolean; // guests scanned before staff opened the table
  pending_order_ids: string[]; // sent back as-is to approve or decline exactly what the tile showed
  pending_order_total: string | null;
  pending_order_items: number | null; // sum of quantities
}

export interface FloorResponse {
  tiles: FloorTile[];
  counts: { red: number; amber: number };
  thresholds: Record<string, [number, number]>;
  server_time: string;
  service_extra_label: string | null;
  pay_forward_balance: number;
}

/** Milliseconds since `since` on the server's clock: the client clock only measures time since the load. */
export function elapsed(sinceIso: string, serverTimeIso: string, clientNowMs: number, loadedAtMs: number): number {
  const serverNow = Date.parse(serverTimeIso) + (clientNowMs - loadedAtMs);
  return Math.max(0, serverNow - Date.parse(sinceIso));
}

export function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const STATES: Record<FloorState, { label: string; icon: string }> = {
  free: { label: "Free", icon: "○" },
  seated: { label: "Seated, no order", icon: "◐" },
  ordered: { label: "Ordered", icon: "◷" },
  served: { label: "Served", icon: "✓" },
  paying: { label: "Paying", icon: "▤" },
  needs_clearing: { label: "Needs clearing", icon: "↺" },
  called: { label: "Waiter called", icon: "!" },
  approval_needed: { label: "Approve order", icon: "△" },
};

export const stateLabel = (state: FloorState) => STATES[state]?.label ?? state;
export const stateIcon = (state: FloorState) => STATES[state]?.icon ?? "?";

/** Guests scanned before the table was opened; `time` is the tile's m:ss timer. */
export const waitingText = (time: string | null) =>
  time ? `Guests waiting to order · ${time}` : "Guests waiting to order";

/** The waiting order in plain words, e.g. "3 items · £12.50" (total already in the venue's currency). */
export const orderSummary = (items: number, total: string) => `${items} ${items === 1 ? "item" : "items"} · ${total}`;

const LEVEL_ORDER: Record<FloorLevel, number> = { red: 0, amber: 1, none: 2 };

/** Red, then amber, then the rest; stable, so the server's label order survives within a level. */
export const sortTiles = (tiles: FloorTile[]) =>
  [...tiles].sort((a, b) => LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]);

export function levelClass(level: FloorLevel): string {
  if (level === "red") return "border-danger-fg bg-danger-bg text-danger-fg";
  if (level === "amber") return "border-warn-fg bg-warn-bg text-warn-fg";
  return "";
}

export const STALE_MS = 45_000;

/** The last successful load is old enough to warn that the view may be out of date. */
export const isStale = (ageMs: number) => ageMs > STALE_MS;

/** Text twin of the colour, so the level never relies on colour alone. */
export const levelText = (level: FloorLevel) => (level === "red" ? "Urgent" : level === "amber" ? "Due soon" : null);

/** The pay-it-forward tile's headline: chai bought by guests and not yet handed out. */
export const payForwardText = (waiting: number) =>
  waiting > 0 ? `Pay-it-forward chai: ${waiting} waiting` : "No chai waiting";

/** A key for one intended "Give one"; randomUUID needs a secure context, so fall back on plain http. */
export const newGiveKey = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

/** Reuse the key on the next tap unless the server answered for sure (done, or refused with 409). */
export const keepGiveKey = (status: number | "network") => status === "network" || (status >= 300 && status !== 409);
