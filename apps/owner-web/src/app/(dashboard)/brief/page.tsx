"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  CLASS_COLORS,
  METHOD_LABELS,
  eur,
  forecastTable,
  quadrantLayout,
  wapePct,
  type DailyBrief,
  type MenuClass,
} from "@/lib/analytics";

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";
const W = 560;
const H = 320;
const PAD = 36;

function KpiTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat-tile space-y-1">
      <span className="text-xs text-[#8FA3B3] uppercase font-semibold">{label}</span>
      <div className="text-3xl font-extrabold text-[#F3F8FC]">{value}</div>
      {sub && <div className="text-xs text-[#8FA3B3]">{sub}</div>}
    </div>
  );
}

function Quadrant({ brief }: { brief: DailyBrief }) {
  const { points, medianX, medianY } = quadrantLayout(
    brief.menu_engineering,
    brief.thresholds,
    W,
    H,
    PAD,
  );
  const labels: [MenuClass, string, number, number][] = [
    ["puzzle", "Puzzles", PAD + 4, PAD - 8],
    ["star", "Stars", W - PAD - 4, PAD - 8],
    ["dog", "Dogs", PAD + 4, H - 8],
    ["plowhorse", "Plowhorses", W - PAD - 4, H - 8],
  ];
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-auto"
      role="img"
      aria-label="Menu engineering quadrant: units sold versus unit margin"
    >
      <rect x={PAD} y={PAD} width={W - 2 * PAD} height={H - 2 * PAD} fill="#070B10" />
      <line x1={medianX} x2={medianX} y1={PAD} y2={H - PAD} stroke="#8FA3B3" strokeDasharray="4 4" />
      <line x1={PAD} x2={W - PAD} y1={medianY} y2={medianY} stroke="#8FA3B3" strokeDasharray="4 4" />
      {labels.map(([cls, text, x, y]) => (
        <text
          key={cls}
          x={x}
          y={y}
          fontSize="11"
          fill={CLASS_COLORS[cls]}
          textAnchor={x > W / 2 ? "end" : "start"}
        >
          {text}
        </text>
      ))}
      {points.map((p) => (
        <circle key={p.item.item_id} cx={p.x} cy={p.y} r={6} fill={CLASS_COLORS[p.item.menu_class]}>
          <title>
            {`${p.item.name}: ${p.item.units} sold, ${eur(p.item.unit_margin_eur)} margin per unit (${p.item.menu_class})`}
          </title>
        </circle>
      ))}
      <text x={W / 2} y={H - PAD + 18} fontSize="11" fill="#8FA3B3" textAnchor="middle">
        Units sold →
      </text>
      <text
        x={12}
        y={H / 2}
        fontSize="11"
        fill="#8FA3B3"
        textAnchor="middle"
        transform={`rotate(-90 12 ${H / 2})`}
      >
        Unit margin →
      </text>
    </svg>
  );
}

function BacktestBadge({ forecast }: { forecast: DailyBrief["forecast"] }) {
  if (forecast.low_confidence || !forecast.backtest.length) {
    return (
      <span className="chip chip-unverified">
        Low confidence: {forecast.history_days} days of history, not backtested
      </span>
    );
  }
  const chosen = forecast.backtest.find((b) => b.method === forecast.method);
  const naive = forecast.backtest.find((b) => b.method === "seasonal_naive");
  return (
    <span className="chip chip-safe">
      Backtest WAPE {wapePct(chosen?.wape)} ({METHOD_LABELS[forecast.method ?? ""] ?? forecast.method})
      vs seasonal naive {wapePct(naive?.wape)}
    </span>
  );
}

export default function DailyBriefPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [daypart, setDaypart] = useState<"lunch" | "dinner">("dinner");
  const [error, setError] = useState<string | null>(null);

  const loadBrief = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/restaurants/${slug}/ai/brief`);
      if (!res.ok) throw new Error(`Failed to load brief (${res.status})`);
      setBrief(await res.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    loadBrief();
    fetch("/api/auth/config")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDemoMode(Boolean(d?.demo_mode)))
      .catch(() => setDemoMode(false));
  }, [loadBrief]);

  const generateDemoData = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(`/api/restaurants/${slug}/demo/simulate-orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days: 56 }),
      });
      if (!res.ok) throw new Error(`Failed to generate demo data (${res.status})`);
      await loadBrief();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  };

  const simulated = brief?.data_sources.simulated ?? 0;
  const table = brief ? forecastTable(brief.forecast.points, daypart) : null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">
            Daily <span className="gradient-text">Revenue Brief</span>
          </h1>
          <p className="text-xs text-[#8FA3B3] mt-1">
            Computed from order history
            {brief ? ` (${brief.window_start} to ${brief.window_end})` : ""}. Numbers come from
            analytics, never from the AI model.
          </p>
        </div>
        {demoMode && (
          <button
            type="button"
            onClick={generateDemoData}
            disabled={generating}
            className="btn-primary min-h-[44px]"
          >
            {generating ? "Generating…" : "Generate demo data"}
          </button>
        )}
      </div>

      {simulated > 0 && (
        <div
          role="status"
          className="p-4 rounded-xl bg-[#FF9F2E]/15 border border-[#FF9F2E]/40 text-xs text-[#FF9F2E] font-semibold"
        >
          Simulated data: {simulated} of {simulated + (brief?.data_sources.live ?? 0)} orders in
          this window are synthetic demo orders, not real sales.
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-[#EF4444]/15 border border-[#EF4444]/40 text-xs text-[#EF4444]">
          {error}
        </div>
      )}

      {loading && !brief ? (
        <div className="mise-card p-12 text-center text-[#8FA3B3] animate-pulse">
          Crunching order history…
        </div>
      ) : (
        brief && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <KpiTile
                label="Revenue"
                value={eur(brief.kpis.revenue_eur)}
                sub={`${brief.kpis.orders} orders`}
              />
              <KpiTile label="Average order value" value={eur(brief.kpis.aov_eur)} />
              <KpiTile
                label="Contribution margin"
                value={eur(brief.kpis.contribution_margin_eur)}
                sub={`${brief.kpis.margin_pct}% of revenue`}
              />
            </div>

            <div className="glass-panel p-6 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-bold text-[#F3F8FC]">Summary — {brief.date}</h2>
                <span className={`chip ${brief.summary_source === "llm" ? "chip-safe" : "chip-unverified"}`}>
                  {brief.summary_source === "llm"
                    ? "AI-written, numbers checked against facts"
                    : "Template summary"}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-[#F3F8FC]">{brief.summary}</p>
            </div>

            <div className="space-y-4">
              <h3 className="text-base font-bold text-[#F3F8FC]">Ranked actions</h3>
              {brief.actions.length === 0 && (
                <p className="text-xs text-[#8FA3B3]">No actions until there is order history.</p>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                {brief.actions.map((a) => (
                  <div key={a.rank} className="mise-card p-5 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="chip chip-unverified uppercase">
                        #{a.rank} {a.type.replace("_", " ")}
                      </span>
                      {a.estimated_impact_eur_per_week != null && (
                        <span className="text-xs font-bold text-[#34D399]">
                          est. {a.estimated_impact_eur_per_week >= 0 ? "+" : ""}
                          {eur(a.estimated_impact_eur_per_week)}/week
                        </span>
                      )}
                    </div>
                    <h4 className="text-base font-extrabold text-[#F3F8FC]">{a.title}</h4>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      {Object.entries(a.evidence).map(([k, v]) => (
                        <React.Fragment key={k}>
                          <dt className="text-[#8FA3B3]">{k.replaceAll("_", " ")}</dt>
                          <dd className="text-[#F3F8FC] font-mono">{String(v)}</dd>
                        </React.Fragment>
                      ))}
                    </dl>
                    <p className="text-[11px] text-[#8FA3B3] font-mono">Formula: {a.formula}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mise-card p-6 space-y-4">
              <div>
                <h3 className="text-base font-bold text-[#F3F8FC]">Menu engineering</h3>
                <p className="text-xs text-[#8FA3B3]">
                  Dashed lines are the medians: {brief.thresholds.median_units} units and{" "}
                  {eur(brief.thresholds.median_unit_margin_eur)} margin per unit. Hover a dot for
                  details.
                </p>
              </div>
              {brief.menu_engineering.length ? (
                <Quadrant brief={brief} />
              ) : (
                <p className="text-xs text-[#8FA3B3]">No sales in this window.</p>
              )}
            </div>

            <div className="mise-card p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-bold text-[#F3F8FC]">7-day demand forecast</h3>
                  <p className="text-xs text-[#8FA3B3]">
                    Units per item; range is the 80% interval from backtest errors. Promotions
                    are assumed off.
                  </p>
                </div>
                <BacktestBadge forecast={brief.forecast} />
              </div>
              <div className="flex gap-2" role="group" aria-label="Daypart">
                {(["lunch", "dinner"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={daypart === d}
                    onClick={() => setDaypart(d)}
                    className={`${daypart === d ? "btn-primary" : "btn-ghost"} min-h-[44px] capitalize`}
                  >
                    {d}
                  </button>
                ))}
              </div>
              {table && table.rows.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-[#8FA3B3] text-left">
                        <th scope="col" className="py-2 pr-3">Item</th>
                        {table.dates.map((d) => (
                          <th scope="col" key={d} className="py-2 px-2 font-mono">
                            {d.slice(5)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {table.rows.map((r) => (
                        <tr key={r.itemId} className="border-t border-[#38BDF8]/10">
                          <th scope="row" className="py-2 pr-3 text-left text-[#F3F8FC] font-semibold">
                            {r.name}
                          </th>
                          {r.cells.map((c, i) => (
                            <td key={i} className="py-2 px-2 font-mono text-[#F3F8FC]">
                              {c ? (
                                <>
                                  {c.forecast.toFixed(1)}
                                  <span className="block text-[10px] text-[#8FA3B3]">
                                    {c.lo.toFixed(0)}–{c.hi.toFixed(0)}
                                  </span>
                                </>
                              ) : (
                                "–"
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-[#8FA3B3]">No forecast yet.</p>
              )}
            </div>
          </>
        )
      )}
    </div>
  );
}
