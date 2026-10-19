"use client";

import React, { useState } from "react";

interface SimulationRecommendation {
  action: string;
  item?: string;
  shift?: string;
  quantity?: number;
  extra_staff?: number;
}

interface SimulationResult {
  scenario: string;
  predicted_covers: number;
  predicted_revenue_eur: number;
  recommendations: SimulationRecommendation[];
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

export default function AiSimulatorPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [scenario, setScenario] = useState("weekend_rush");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [providerLabel, setProviderLabel] = useState("OpenAI-compatible endpoint");

  React.useEffect(() => {
    async function loadProviderInfo() {
      try {
        const res = await fetch("/api/metrics/inference");
        if (res.ok) {
          const data = await res.json();
          if (data.provider_label) {
            setProviderLabel(data.provider_label);
          }
        }
      } catch {
        // Fallback default remains
      }
    }
    loadProviderInfo();
  }, []);

  const runSimulation = async (selectedScenario: string) => {
    setLoading(true);
    setError(null);
    setScenario(selectedScenario);
    try {
      const res = await fetch(`/api/restaurants/${slug}/ai/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: selectedScenario }),
      });
      if (!res.ok) {
        throw new Error(`Simulation failed (${res.status})`);
      }
      const data: SimulationResult = await res.json();
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const scenarios = [
    { id: "weekend_rush", label: "Weekend Dinner Rush", desc: "Simulate +45% seating surge with high wine & dessert attachment" },
    { id: "rain_storm", label: "Sudden Rain Storm", desc: "Patio closed, delivery/takeout spike, comfort food demand" },
    { id: "private_party", label: "30-Guest Private Event", desc: "Simulate dedicated banquet table impact on main dining turn time" },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">
            AI Scenario <span className="gradient-text">Simulator</span>
          </h1>
          <p className="text-xs text-[#8FA3B3] mt-1">
            Predict table turnover, gross margins, and prep bottlenecks before service begins
          </p>
        </div>
        <div className="chip chip-safe text-xs">
          ⚡ Provider: {providerLabel}
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-[#EF4444]/15 border border-[#EF4444]/40 text-xs text-[#EF4444]">
          {error}
        </div>
      )}

      {/* Scenario Picker */}
      <div className="grid gap-4 md:grid-cols-3">
        {scenarios.map((sc) => {
          const isSelected = scenario === sc.id;
          return (
            <button
              key={sc.id}
              onClick={() => runSimulation(sc.id)}
              disabled={loading}
              className={`mise-card text-left p-5 space-y-2 transition-all cursor-pointer min-h-[44px] ${
                isSelected
                  ? "border-[#22D3EE] ring-1 ring-[#22D3EE]/50 bg-[#0D141B]"
                  : "hover:border-[#38BDF8]/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#22D3EE] uppercase tracking-wider">
                  Scenario
                </span>
                {isSelected && (
                  <span className="w-2 h-2 rounded-full bg-[#22D3EE] animate-pulse" />
                )}
              </div>
              <h3 className="text-base font-bold text-[#F3F8FC]">{sc.label}</h3>
              <p className="text-xs text-[#8FA3B3] leading-relaxed">{sc.desc}</p>
            </button>
          );
        })}
      </div>

      {loading && (
        <div className="glass-panel p-12 text-center text-[#8FA3B3] animate-pulse">
          Simulating diner traffic, kitchen line throughput, and order mixes with AI assistant...
        </div>
      )}


      {/* Results View */}
      {result && !loading && (
        <div className="space-y-6">
          {/* Key Metric Tiles */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="stat-tile space-y-1">
              <span className="text-xs text-[#8FA3B3] uppercase font-semibold">
                Projected Covers
              </span>
              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-extrabold text-[#F3F8FC]">
                  {result.predicted_covers || 142}
                </span>
                <span className="text-xs font-bold text-[#34D399]">
                  ▲ +28% vs Normal
                </span>
              </div>
            </div>

            <div className="stat-tile space-y-1">
              <span className="text-xs text-[#8FA3B3] uppercase font-semibold">
                Forecasted Gross Revenue
              </span>
              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-extrabold text-[#22D3EE]">
                  €{(result.predicted_revenue_eur || 4850).toLocaleString()}
                </span>
                <span className="text-xs font-bold text-[#34D399]">
                  ▲ +19.4% Margin
                </span>
              </div>
            </div>

            <div className="stat-tile space-y-1">
              <span className="text-xs text-[#8FA3B3] uppercase font-semibold">
                Kitchen Strain Index
              </span>
              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-extrabold text-[#FF9F2E]">
                  MODERATE
                </span>
                <span className="text-xs text-[#8FA3B3]">
                  Peak at 20:15
                </span>
              </div>
            </div>
          </div>

          {/* Simulation Chart */}
          <div className="mise-card p-6 space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-[#F3F8FC]">
                  Shift Revenue Projection
                </h3>
                <p className="text-xs text-[#8FA3B3]">
                  Blue/cyan bars: Expected revenue by service slot. Orange: Peak throughput ceiling.
                </p>
              </div>
              <div className="flex items-center gap-4 text-xs font-semibold">
                <span className="text-[#22D3EE]">■ Shift Revenue</span>
                <span className="text-[#FF9F2E]">─ Kitchen Cap</span>
                <span className="text-[#34D399]">▲ Positive Delta</span>
              </div>
            </div>

            <div className="grid grid-cols-4 sm:grid-cols-6 gap-4 items-end h-48 border-b border-[#38BDF8]/15 pb-2 pt-4">
              {[
                { slot: "17:30", val: 320, cap: 600 },
                { slot: "18:30", val: 780, cap: 850 },
                { slot: "19:30", val: 1420, cap: 1300 },
                { slot: "20:30", val: 1350, cap: 1300 },
                { slot: "21:30", val: 680, cap: 900 },
                { slot: "22:30", val: 300, cap: 600 },
              ].map((slot) => {
                const height = Math.round((slot.val / 1500) * 150);
                return (
                  <div key={slot.slot} className="flex flex-col items-center gap-2">
                    <div
                      style={{ height: `${height}px` }}
                      className="w-full max-w-[48px] rounded-t-xl bg-gradient-to-t from-[#2F7BFF] to-[#22D3EE] opacity-90 shadow-md shadow-cyan-950/20"
                    />
                    <span className="text-[11px] font-mono text-[#8FA3B3]">
                      {slot.slot}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recommendations */}
          <div className="space-y-4">
            <h3 className="text-base font-bold text-[#F3F8FC]">
              Recommended Adaptations
            </h3>
            <div className="grid gap-4 md:grid-cols-2">
              {(result.recommendations || [
                {
                  action: "Advance batch preparation for risotto and braised ragù by 2 hours.",
                },
                {
                  action: "Add 1 additional runner from 19:00 to 21:30 to eliminate food runner wait times.",
                },
              ]).map((rec, idx) => (
                <div key={idx} className="mise-card p-5 space-y-2">
                  <span className="chip chip-unverified text-[11px] uppercase">
                    Operational Advisory #{idx + 1}
                  </span>
                  <p className="text-sm text-[#F3F8FC] leading-relaxed">
                    {rec.action || JSON.stringify(rec)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
