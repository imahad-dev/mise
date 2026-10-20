import { describe, expect, it } from "vitest";
import {
  eur,
  forecastTable,
  quadrantLayout,
  wapePct,
  type ForecastPoint,
  type MenuEngineeringItem,
} from "./analytics";

const item = (id: string, units: number, margin: number): MenuEngineeringItem => ({
  item_id: id,
  name: id,
  units,
  weekly_units: units / 4,
  revenue_eur: 0,
  unit_margin_eur: margin,
  contribution_eur: 0,
  menu_class: "star",
});

describe("quadrantLayout", () => {
  it("places high-unit items right and high-margin items up", () => {
    const { points, medianX, medianY } = quadrantLayout(
      [item("a", 100, 10), item("b", 0, 0)],
      { median_units: 50, median_unit_margin_eur: 5 },
      200,
      100,
      10,
    );
    expect(points[0].x).toBe(190);
    expect(points[1].x).toBe(10);
    expect(points[0].y).toBe(10); // top
    expect(points[1].y).toBe(90); // bottom
    expect(medianX).toBe(100);
    expect(medianY).toBe(50);
  });
});

describe("forecastTable", () => {
  const p = (id: string, date: string, daypart: "lunch" | "dinner", forecast: number) =>
    ({ item_id: id, name: id, date, daypart, forecast, lo: 0, hi: forecast + 1 }) as ForecastPoint;

  it("keeps one daypart, sorts items by total and aligns cells by date", () => {
    const { dates, rows } = forecastTable(
      [
        p("a", "2026-10-21", "dinner", 1),
        p("b", "2026-10-21", "dinner", 5),
        p("b", "2026-10-22", "dinner", 5),
        p("a", "2026-10-22", "lunch", 99),
      ],
      "dinner",
    );
    expect(dates).toEqual(["2026-10-21", "2026-10-22"]);
    expect(rows.map((r) => r.itemId)).toEqual(["b", "a"]);
    expect(rows[1].cells[1]).toBeNull();
  });
});

describe("formatting", () => {
  it("formats euros and WAPE", () => {
    expect(eur(1234.5)).toBe("€1,234.50");
    expect(wapePct(0.4123)).toBe("41.2%");
    expect(wapePct(null)).toBe("n/a");
  });
});
