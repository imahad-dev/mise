// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import DailyBriefPage from "./page";

// Stable objects: the page's loader depends on them, so fresh ones every render would loop.
const { venueValue, slugRef } = vi.hoisted(() => ({
  venueValue: { venue: { slug: "v", currency: "GBP" } },
  slugRef: { current: "v" },
}));
vi.mock("../../../lib/venue", () => ({
  useVenue: () => venueValue,
  useSlugRef: () => slugRef,
}));
vi.mock("../../../components/ServiceReportCard", () => ({
  ServiceReportCard: () => null,
  SummarySourceChip: () => null,
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const brief = (top: { label: string; count: number }[]) => ({
  date: "2026-11-06", currency: "GBP", window_start: "2026-10-09", window_end: "2026-11-06",
  data_sources: { live: 10, simulated: 0 },
  kpis: { orders: 10, revenue: 100, aov: 10, contribution_margin: 60, margin_pct: 60 },
  menu_engineering: [], thresholds: { median_units: 1, median_unit_margin: 1 },
  payment_mix: null, prices_include_tax: false, tax_split_by_method: false,
  service_charge_collected: "0", pay_forward: { bought: 0, given: 0 },
  extras: { attach_rate_pct: 40, sales: 12.5, top },
  forecast: { method: null, model_name: null, history_days: 0, low_confidence: false, backtest: [], points: [] },
  actions: [], summary: "Fine.", summary_source: "template",
});

function stubBrief(top: { label: string; count: number }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url.includes("/ai/brief") ? new Response(JSON.stringify(brief(top))) : new Response("{}", { status: 404 }),
    ),
  );
}

describe("Brief extras tile", () => {
  it("shows extras sales, how often they are added and the top ones", async () => {
    stubBrief([{ label: "Extra milk", count: 7 }]);
    render(<DailyBriefPage />);
    await waitFor(() => expect(screen.getByText("Extras sales")).toBeTruthy());
    expect(screen.getByText(/Added to 40% of lines\. Top: Extra milk \(7\)/)).toBeTruthy();
  });

  it("hides the tile when nothing was added", async () => {
    stubBrief([]);
    render(<DailyBriefPage />);
    await waitFor(() => expect(screen.getByText("Fine.")).toBeTruthy());
    expect(screen.queryByText("Extras sales")).toBeNull();
  });
});
