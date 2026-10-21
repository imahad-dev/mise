"use client";

import React, { useEffect, useState } from "react";
import { eur, type DataSources } from "@/lib/analytics";

type Scenario = "price_change" | "promotion" | "demand_surge";

interface Totals {
  revenue_eur: number;
  margin_eur: number;
}

interface WhatIfResult {
  scenario: Scenario;
  item: string | null;
  window_start: string;
  window_end: string;
  data_sources: DataSources;
  baseline: Totals;
  result: Totals;
  delta: Totals;
  assumptions: string[];
  explanation: string;
  explanation_source: "llm" | "template";
}

interface MenuOption {
  id: string;
  name: string;
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

const SCENARIOS: { id: Scenario; label: string; desc: string }[] = [
  { id: "price_change", label: "Price change", desc: "Change one item's price; demand reacts via elasticity." },
  { id: "promotion", label: "Promotion", desc: "Discount one item; demand reacts via promotion elasticity." },
  { id: "demand_surge", label: "Demand surge", desc: "Multiply every item's weekly demand." },
];

const signed = (v: number) => `${v >= 0 ? "+" : "−"}${eur(Math.abs(v))}`;

export default function WhatIfPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [items, setItems] = useState<MenuOption[]>([]);
  const [scenario, setScenario] = useState<Scenario>("price_change");
  const [itemId, setItemId] = useState("");
  const [changePct, setChangePct] = useState("5");
  const [discountPct, setDiscountPct] = useState("20");
  const [multiplier, setMultiplier] = useState("1.3");
  const [elasticity, setElasticity] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/restaurants/${slug}/menu-items`)
      .then((r) => (r.ok ? r.json() : []))
      .then(
        (data: { id: string; translations: { language: string; name: string }[] }[]) => {
          const opts = data.map((m) => ({
            id: m.id,
            name: (m.translations.find((t) => t.language === "en") ?? m.translations[0])?.name ?? m.id,
          }));
          setItems(opts);
          if (opts.length) setItemId(opts[0].id);
        },
      )
      .catch(() => setItems([]));
  }, [slug]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const body: Record<string, unknown> = { scenario };
    if (scenario !== "demand_surge") body.item_id = itemId;
    if (scenario === "price_change") body.change_pct = Number(changePct);
    if (scenario === "promotion") body.discount_pct = Number(discountPct);
    if (scenario === "demand_surge") body.multiplier = Number(multiplier);
    if (scenario !== "demand_surge" && elasticity.trim()) body.elasticity = Number(elasticity);
    try {
      const res = await fetch(`/api/restaurants/${slug}/ai/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string" ? detail.detail : `What-if failed (${res.status})`,
        );
      }
      setResult(await res.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const field = "w-full rounded-lg bg-paper border border-line px-3 py-2 min-h-[44px] text-sm";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          What-if <span className="text-terracotta">Calculator</span>
        </h1>
        <p className="text-xs text-ink-muted mt-1">
          Deterministic weekly estimate from the last 28 days of sales at current menu prices.
          The AI model may only explain the result; it never produces the numbers.
        </p>
      </div>

      <form onSubmit={submit} className="mise-card p-6 space-y-5">
        <fieldset className="grid gap-3 md:grid-cols-3">
          <legend className="text-xs font-bold text-terracotta uppercase tracking-wider mb-2">
            Scenario
          </legend>
          {SCENARIOS.map((s) => (
            <label
              key={s.id}
              className={`mise-card p-4 cursor-pointer space-y-1 ${
                scenario === s.id ? "border-terracotta ring-1 ring-terracotta" : ""
              }`}
            >
              <input
                type="radio"
                name="scenario"
                value={s.id}
                checked={scenario === s.id}
                onChange={() => setScenario(s.id)}
                className="mr-2"
              />
              <span className="font-bold text-ink">{s.label}</span>
              <p className="text-xs text-ink-muted">{s.desc}</p>
            </label>
          ))}
        </fieldset>

        <div className="grid gap-4 md:grid-cols-3">
          {scenario !== "demand_surge" && (
            <label className="space-y-1 text-xs text-ink-muted">
              Menu item
              <select className={field} value={itemId} onChange={(e) => setItemId(e.target.value)} required>
                {items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {scenario === "price_change" && (
            <label className="space-y-1 text-xs text-ink-muted">
              Price change (%)
              <input className={field} type="number" step="0.5" min={-90} max={100} value={changePct}
                onChange={(e) => setChangePct(e.target.value)} required />
            </label>
          )}
          {scenario === "promotion" && (
            <label className="space-y-1 text-xs text-ink-muted">
              Discount (%)
              <input className={field} type="number" step="1" min={1} max={90} value={discountPct}
                onChange={(e) => setDiscountPct(e.target.value)} required />
            </label>
          )}
          {scenario === "demand_surge" && (
            <label className="space-y-1 text-xs text-ink-muted">
              Demand multiplier
              <input className={field} type="number" step="0.05" min={0.1} max={5} value={multiplier}
                onChange={(e) => setMultiplier(e.target.value)} required />
            </label>
          )}
          {scenario !== "demand_surge" && (
            <label className="space-y-1 text-xs text-ink-muted">
              Elasticity (optional)
              <input className={field} type="number" step="0.1" min={-10} max={0} value={elasticity}
                placeholder={scenario === "price_change" ? "-0.8 (default)" : "-2.0 (default)"}
                onChange={(e) => setElasticity(e.target.value)} />
            </label>
          )}
        </div>

        <button type="submit" disabled={loading} className="btn-primary min-h-[44px]">
          {loading ? "Calculating…" : "Calculate"}
        </button>
      </form>

      {error && (
        <div role="alert" className="p-4 rounded-xl bg-danger-bg border border-danger-fg text-xs text-danger-fg">
          {error}
        </div>
      )}

      {result && !loading && (
        <div className="space-y-6">
          {result.data_sources.simulated > 0 && (
            <div role="status" className="p-4 rounded-xl bg-warn-bg border border-warn-fg/30 text-xs text-warn-fg font-semibold">
              Baseline uses {result.data_sources.simulated} simulated demo orders
              ({result.window_start} to {result.window_end}).
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            {(["baseline", "result", "delta"] as const).map((k) => (
              <div key={k} className="stat-tile space-y-2">
                <span className="text-xs text-ink-muted uppercase font-semibold">
                  {k === "baseline" ? "Baseline / week" : k === "result" ? "Scenario / week" : "Change / week"}
                </span>
                <div className="text-sm text-ink">
                  Revenue{" "}
                  <span className="font-extrabold text-xl">
                    {k === "delta" ? signed(result[k].revenue_eur) : eur(result[k].revenue_eur)}
                  </span>
                </div>
                <div className="text-sm text-ink">
                  Margin{" "}
                  <span className={`font-extrabold text-xl ${k === "delta" ? (result.delta.margin_eur >= 0 ? "text-olive" : "text-danger-fg") : ""}`}>
                    {k === "delta" ? signed(result[k].margin_eur) : eur(result[k].margin_eur)}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="mise-card p-5 space-y-2">
            <h3 className="text-base font-bold text-ink">Assumptions</h3>
            <ul className="list-disc pl-5 text-xs text-ink-muted space-y-1">
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>

          <div className="mise-card p-5 space-y-2">
            <span className={`chip ${result.explanation_source === "llm" ? "chip-safe" : "chip-unverified"}`}>
              {result.explanation_source === "llm" ? "AI explanation, numbers checked" : "Template explanation"}
            </span>
            <p className="text-sm text-ink leading-relaxed">{result.explanation}</p>
          </div>
        </div>
      )}
    </div>
  );
}
