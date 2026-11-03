/** Mirrors services/api/src/schemas/service_report.py. Durations are whole seconds, null without data. */
export type Stage = "first_order" | "approval" | "kitchen" | "bill";

export interface ServiceReport {
  day: string;
  tables_served: number;
  closed_without_bill: number;
  simulated_sittings: number;
  average_table_seconds: number | null;
  average_wait_seconds: Record<Stage, number | null>;
  busiest_hour: number | null;
  slowest_hour: { hour: number; average_table_seconds: number; slowest_stage: Stage | null } | null;
  alerts: { seated_no_order: number; approval_needed: number; order_no_bump: number; bill_not_settled: number };
  summary: string;
  summary_source: "llm" | "template";
}

export const STAGE_LABELS: Record<Stage, string> = {
  first_order: "First order",
  approval: "Waiter confirming the first order",
  kitchen: "Kitchen",
  bill: "Bill",
};

export const ALERT_LABELS: Record<keyof ServiceReport["alerts"], string> = {
  seated_no_order: "Seated with no order",
  approval_needed: "First order waiting for the waiter",
  order_no_bump: "Order waiting for the kitchen",
  bill_not_settled: "Bill waiting to be paid",
};

/** Whole minutes, rounded; "–" when there is no data. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "–";
  if (seconds < 60) return "under a minute";
  const m = Math.round(seconds / 60);
  return `${m} ${m === 1 ? "minute" : "minutes"}`;
}

/** A local hour as its one-hour span, e.g. 18 -> "18:00–19:00". */
export const hourSpan = (hour: number) =>
  `${String(hour).padStart(2, "0")}:00–${String((hour + 1) % 24).padStart(2, "0")}:00`;
