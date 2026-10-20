// Types and pure helpers for the analytics brief and what-if pages.

export type MenuClass = "star" | "plowhorse" | "puzzle" | "dog";

export interface MenuEngineeringItem {
  item_id: string;
  name: string;
  units: number;
  weekly_units: number;
  revenue_eur: number;
  unit_margin_eur: number;
  contribution_eur: number;
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
  item: string;
  title: string;
  evidence: Record<string, number | string>;
  estimated_impact_eur_per_week: number | null;
  formula: string;
}

export interface DataSources {
  live: number;
  simulated: number;
}

export interface DailyBrief {
  date: string;
  window_start: string;
  window_end: string;
  data_sources: DataSources;
  kpis: {
    orders: number;
    revenue_eur: number;
    aov_eur: number;
    contribution_margin_eur: number;
    margin_pct: number;
  };
  menu_engineering: MenuEngineeringItem[];
  thresholds: { median_units: number; median_unit_margin_eur: number };
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
  star: "#34D399",
  plowhorse: "#38BDF8",
  puzzle: "#FF9F2E",
  dog: "#EF4444",
};

export const METHOD_LABELS: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  trailing_4w_mean: "4-week mean",
  hgb: "Gradient boosting",
};

export function eur(v: number): string {
  return `€${v.toLocaleString("en-IE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
  thresholds: { median_units: number; median_unit_margin_eur: number },
  width: number,
  height: number,
  pad: number,
): { points: QuadrantPoint[]; medianX: number; medianY: number } {
  const maxUnits = Math.max(1, thresholds.median_units, ...items.map((i) => i.units));
  const margins = items.map((i) => i.unit_margin_eur);
  const minM = Math.min(0, thresholds.median_unit_margin_eur, ...margins);
  const maxM = Math.max(minM + 1, thresholds.median_unit_margin_eur, ...margins);
  const sx = (u: number) => pad + (u / maxUnits) * (width - 2 * pad);
  const sy = (m: number) => height - pad - ((m - minM) / (maxM - minM)) * (height - 2 * pad);
  return {
    points: items.map((item) => ({ item, x: sx(item.units), y: sy(item.unit_margin_eur) })),
    medianX: sx(thresholds.median_units),
    medianY: sy(thresholds.median_unit_margin_eur),
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
