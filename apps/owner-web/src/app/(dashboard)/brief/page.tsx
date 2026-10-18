"use client";

import React, { useEffect, useState } from "react";

interface ActionItem {
  type: string;
  item: string;
  reason: string;
}

interface DailyBrief {
  date: string;
  summary: string;
  actions: ActionItem[];
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

export default function DailyBriefPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadBrief() {
      try {
        const res = await fetch(`/api/restaurants/${slug}/ai/brief`);
        if (!res.ok) {
          throw new Error(`Failed to load AI brief (${res.status})`);
        }
        const data = await res.json();
        setBrief(data);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    loadBrief();
  }, [slug]);

  // Hourly cover & revenue distribution data for chart
  const hours = [
    { hour: "12:00", actual: 38, forecast: 42, revenue: 1140 },
    { hour: "13:00", actual: 64, forecast: 60, revenue: 1920 },
    { hour: "14:00", actual: 45, forecast: 40, revenue: 1350 },
    { hour: "18:00", actual: 52, forecast: 50, revenue: 1820 },
    { hour: "19:00", actual: 88, forecast: 82, revenue: 3080 },
    { hour: "20:00", actual: 96, forecast: 90, revenue: 3360 },
    { hour: "21:00", actual: 70, forecast: 75, revenue: 2450 },
  ];

  const maxVal = Math.max(...hours.map((h) => Math.max(h.actual, h.forecast)));

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          AI <span className="gradient-text">Daily Operations Brief</span>
        </h1>
        <p className="text-xs text-[#8FA3B3] mt-1">
          Automated executive summary, demand forecasting, and yield actions powered by AMD Token Factory
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-[#EF4444]/15 border border-[#EF4444]/40 text-xs text-[#EF4444]">
          {error}
        </div>
      )}

      {loading ? (
        <div className="mise-card p-12 text-center text-[#8FA3B3] animate-pulse">
          Analyzing service history, reservations, and inventory signals...
        </div>
      ) : (
        <>
          {/* Executive Summary Card */}
          <div className="glass-panel p-6 sm:p-8 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#38BDF8]/15 pb-4">
              <div>
                <span className="text-xs font-mono uppercase tracking-widest text-[#22D3EE]">
                  Intelligence Report
                </span>
                <h2 className="text-xl font-bold text-[#F3F8FC]">
                  Service Summary — {brief?.date || "Today"}
                </h2>
              </div>
              <div className="chip chip-safe">
                ● 10-min Cache Active
              </div>
            </div>

            <p className="text-sm leading-relaxed text-[#F3F8FC]">
              {brief?.summary || "Operations tracking smoothly across all service stations."}
            </p>
          </div>

          {/* Revenue & Cover Chart (Blue & Cyan bars, Orange forecast line, Green positive change) */}
          <div className="mise-card p-6 space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-[#F3F8FC]">
                  Covers & Demand Forecast
                </h3>
                <p className="text-xs text-[#8FA3B3]">
                  Hourly distribution comparison: Actual (blue/cyan) vs. Projected demand (orange line)
                </p>
              </div>
              <div className="flex items-center gap-4 text-xs font-semibold">
                <span className="flex items-center gap-1.5 text-[#22D3EE]">
                  <span className="w-3 h-3 rounded-sm bg-gradient-to-t from-[#2F7BFF] to-[#22D3EE]" /> Actual Covers
                </span>
                <span className="flex items-center gap-1.5 text-[#FF9F2E]">
                  <span className="w-3 h-0.5 bg-[#FF9F2E]" /> Forecast Line
                </span>
                <span className="flex items-center gap-1.5 text-[#34D399]">
                  ▲ +8.4% WoW
                </span>
              </div>
            </div>

            {/* Custom SVG / Bar Chart */}
            <div className="relative pt-6 pb-2">
              <div className="grid grid-cols-7 gap-3 sm:gap-6 items-end h-56 border-b border-[#38BDF8]/15 pb-2">
                {hours.map((h) => {
                  const barHeight = Math.round((h.actual / maxVal) * 180);
                  const forecastTop = Math.round((h.forecast / maxVal) * 180);
                  return (
                    <div key={h.hour} className="flex flex-col items-center gap-2 group relative">
                      {/* Tooltip */}
                      <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-12 z-10 bg-[#070B10] border border-[#22D3EE]/40 px-2 py-1 rounded text-[11px] whitespace-nowrap shadow-xl">
                        {h.actual} covers / €{h.revenue}
                      </div>

                      {/* Forecast marker dot */}
                      <div
                        className="w-2.5 h-2.5 rounded-full bg-[#FF9F2E] border-2 border-[#070B10] absolute z-10"
                        style={{ bottom: `${forecastTop + 32}px` }}
                        title={`Forecast: ${h.forecast}`}
                      />

                      {/* Bar */}
                      <div
                        style={{ height: `${barHeight}px` }}
                        className="w-full max-w-[42px] rounded-t-xl bg-gradient-to-t from-[#2F7BFF] to-[#22D3EE] opacity-90 group-hover:opacity-100 transition-all shadow-lg shadow-cyan-950/20"
                      />

                      <span className="text-[11px] font-mono text-[#8FA3B3]">
                        {h.hour}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Actionable Recommendations */}
          <div className="space-y-4">
            <h3 className="text-base font-bold text-[#F3F8FC]">
              Prescribed Operational Actions
            </h3>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {(brief?.actions || [
                {
                  type: "prep",
                  item: "Truffle Tagliolini",
                  reason: "Anticipate +30% dinner rush demand; increase pasta prep by 15 portions.",
                },
                {
                  type: "staffing",
                  item: "Sauté Station",
                  reason: "Bottleneck expected between 19:30-21:00; dedicate second commis chef.",
                },
                {
                  type: "upsell",
                  item: "Chianti Classico Riserva",
                  reason: "Pairing recommendation with Bistecca elevated wine revenue by €420 yesterday.",
                },
              ]).map((action, idx) => (
                <div key={idx} className="mise-card p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="chip chip-unverified uppercase">
                      {action.type}
                    </span>
                    <span className="text-xs text-[#34D399] font-bold">High Impact</span>
                  </div>
                  <h4 className="text-base font-extrabold text-[#F3F8FC]">
                    {action.item}
                  </h4>
                  <p className="text-xs leading-relaxed text-[#8FA3B3]">
                    {action.reason}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
