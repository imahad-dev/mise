/** Mirrors services/api/src/schemas/floor.py. Decimals arrive as strings. */
export type FloorState = "free" | "seated" | "ordered" | "served" | "paying" | "needs_clearing" | "called";
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
}

export interface FloorResponse {
  tiles: FloorTile[];
  counts: { red: number; amber: number };
  thresholds: Record<string, [number, number]>;
  server_time: string;
  service_extra_label: string | null;
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
};

export const stateLabel = (state: FloorState) => STATES[state]?.label ?? state;
export const stateIcon = (state: FloorState) => STATES[state]?.icon ?? "?";

const LEVEL_ORDER: Record<FloorLevel, number> = { red: 0, amber: 1, none: 2 };

/** Red, then amber, then the rest; stable, so the server's label order survives within a level. */
export const sortTiles = (tiles: FloorTile[]) =>
  [...tiles].sort((a, b) => LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]);

export function levelClass(level: FloorLevel): string {
  if (level === "red") return "border-danger-fg bg-danger-bg text-danger-fg";
  if (level === "amber") return "border-warn-fg bg-warn-bg text-warn-fg";
  return "";
}

/** Text twin of the colour, so the level never relies on colour alone. */
export const levelText = (level: FloorLevel) => (level === "red" ? "Urgent" : level === "amber" ? "Due soon" : null);
