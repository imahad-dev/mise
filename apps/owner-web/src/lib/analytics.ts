// Types and pure helpers for the analytics brief and what-if pages.
import { formatPrice } from "ui";

export type MenuClass = "star" | "plowhorse" | "puzzle" | "dog";

export interface MenuEngineeringItem {
  item_id: string;
  /** Set on a portion/size row: one row per (dish, option). */
  option_id: string | null;
  name: string;
  units: number;
  weekly_units: number;
  revenue: number;
  unit_margin: number;
  contribution: number;
  menu_class: MenuClass;
}

export interface ForecastPoint {
  date: string;
  item_id: string;
  name: string;
  daypart: "lunch" | "dinner";
  forecast: number;
  lo: number;
  hi: number;
}

export interface BacktestMetric {
  method: string;
  wape: number | null;
  mae: number | null;
  n_points: number;
}

export interface BriefAction {
  rank: number;
  type: "promote_puzzle" | "reprice_plowhorse" | "review_dog" | "prep_target";
  item_id: string | null;
  option_id: string | null;
  item: string;
  title: string;
  evidence: Record<string, number | string>;
  estimated_impact_per_week: number | null;
  formula: string;
}

export interface DataSources {
  live: number;
  simulated: number;
}

/** Decimal amounts arrive as strings ("240.00"). Standard = cash, bank transfer. */
export interface PaymentMix {
  bills: { standard: number; digital: number };
  revenue_share: { standard: number; digital: number };
  digital_revenue_pct: number;
  tax_by_rate: { rate: string; tax: string }[];
  digital_tax_saving: string;
}

export interface DailyBrief {
  date: string;
  currency: string;
  window_start: string;
  window_end: string;
  data_sources: DataSources;
  kpis: {
    orders: number;
    revenue: number;
    aov: number;
    contribution_margin: number;
    margin_pct: number;
  };
  menu_engineering: MenuEngineeringItem[];
  thresholds: { median_units: number; median_unit_margin: number };
  payment_mix: PaymentMix;
  /** Pay-it-forward chai over the last 7 days; not revenue. */
  pay_forward: { bought: number; given: number };
  forecast: {
    method: string | null;
    model_name: string | null;
    history_days: number;
    low_confidence: boolean;
    backtest: BacktestMetric[];
    points: ForecastPoint[];
  };
  actions: BriefAction[];
  summary: string;
  summary_source: "llm" | "template";
}

export const CLASS_COLORS: Record<MenuClass, string> = {
  star: "#4A5D3A",
  plowhorse: "#6B5A48",
  puzzle: "#B5462B",
  dog: "#8A1C12",
};

export const METHOD_LABELS: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  trailing_4w_mean: "4-week mean",
  hgb: "Gradient boosting",
};

export function money(v: number, currency: string): string {
  return formatPrice(v, currency);
}

/** 0.6667 -> "66.7%" */
export function sharePct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export function wapePct(v: number | null | undefined): string {
  return v == null ? "n/a" : `${(v * 100).toFixed(1)}%`;
}

export interface QuadrantPoint {
  item: MenuEngineeringItem;
  x: number;
  y: number;
}

/** Map items to SVG coordinates: x = units sold, y = unit margin (higher is up). */
export function quadrantLayout(
  items: MenuEngineeringItem[],
  thresholds: { median_units: number; median_unit_margin: number },
  width: number,
  height: number,
  pad: number,
): { points: QuadrantPoint[]; medianX: number; medianY: number } {
  const maxUnits = Math.max(1, thresholds.median_units, ...items.map((i) => i.units));
  const margins = items.map((i) => i.unit_margin);
  const minM = Math.min(0, thresholds.median_unit_margin, ...margins);
  const maxM = Math.max(minM + 1, thresholds.median_unit_margin, ...margins);
  const sx = (u: number) => pad + (u / maxUnits) * (width - 2 * pad);
  const sy = (m: number) => height - pad - ((m - minM) / (maxM - minM)) * (height - 2 * pad);
  return {
    points: items.map((item) => ({ item, x: sx(item.units), y: sy(item.unit_margin) })),
    medianX: sx(thresholds.median_units),
    medianY: sy(thresholds.median_unit_margin),
  };
}

export interface ForecastRow {
  itemId: string;
  name: string;
  total: number;
  cells: (ForecastPoint | null)[];
}

/** Rows of the top items (by 7-day total) for one daypart, one cell per forecast date. */
export function forecastTable(
  points: ForecastPoint[],
  daypart: "lunch" | "dinner",
  limit = 10,
): { dates: string[]; rows: ForecastRow[] } {
  const selected = points.filter((p) => p.daypart === daypart);
  const dates = [...new Set(selected.map((p) => p.date))].sort();
  const byItem = new Map<string, ForecastRow>();
  for (const p of selected) {
    const row =
      byItem.get(p.item_id) ??
      { itemId: p.item_id, name: p.name, total: 0, cells: dates.map(() => null) };
    row.cells[dates.indexOf(p.date)] = p;
    row.total += p.forecast;
    byItem.set(p.item_id, row);
  }
  const rows = [...byItem.values()].sort((a, b) => b.total - a.total).slice(0, limit);
  return { dates, rows };
}
