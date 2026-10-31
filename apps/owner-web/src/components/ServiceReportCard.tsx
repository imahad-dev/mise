"use client";

import React, { useEffect, useState } from "react";
import { Card, StatTile } from "ui";
import { apiError } from "../lib/bill";
import {
  ALERT_LABELS,
  STAGE_LABELS,
  formatDuration,
  hourSpan,
  type ServiceReport,
  type Stage,
} from "../lib/service-report";

/** Where a summary's words came from; shared with the Brief's own summary. */
export function SummarySourceChip({ source }: { source: "llm" | "template" }) {
  return (
    <span className={`chip ${source === "llm" ? "chip-safe" : "chip-unverified"}`}>
      {source === "llm" ? "AI-written, numbers checked against facts" : "Template summary"}
    </span>
  );
}

/** How service went on one day. Mount with key={slug} so a venue switch starts fresh. Owners only: a staff 403 hides the card. */
export function ServiceReportCard({ slug }: { slug: string | undefined }) {
  // "" asks the server for the venue's today; the answer's day then fills the picker.
  const [day, setDay] = useState("");
  const [today, setToday] = useState("");
  const [report, setReport] = useState<ServiceReport | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The first answer fills `day`; that report is already loaded, so don't fetch it again.
    if (!slug || (report && report.day === day)) return;
    let live = true; // drop answers for a venue or day no longer shown
    setError(null);
    fetch(`/api/restaurants/${slug}/service-report${day ? `?day=${day}` : ""}`)
      .then(async (res) => {
        if (!live) return;
        if (res.status === 403) return setHidden(true);
        if (!res.ok) throw new Error(await apiError(res));
        const data = (await res.json()) as ServiceReport;
        setReport(data);
        if (!day) {
          setDay(data.day);
          setToday(data.day);
        }
      })
      .catch((err: unknown) => {
        if (live) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      live = false;
    };
  }, [slug, day, report]);

  if (hidden) return null;
  const r = report && report.day === day ? report : null;

  return (
    <Card className="p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-ink">Service report</h3>
          <p className="text-xs text-ink-muted">Tables closed on this day, and how long each step took.</p>
        </div>
        <label className="space-y-1 text-xs text-ink-muted">
          <span className="block">Day</span>
          <input
            type="date"
            className="rounded-lg bg-paper border border-line px-3 py-2 min-h-[44px] text-sm text-ink"
            value={day}
            max={today || undefined}
            onChange={(e) => e.target.value && setDay(e.target.value)}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="p-3 rounded-xl bg-danger-bg border border-danger-fg text-xs text-danger-fg">
          {error}
        </p>
      )}

      {!r ? (
        !error && <p className="text-xs text-ink-muted animate-pulse">Loading…</p>
      ) : r.tables_served === 0 ? (
        <p className="text-sm text-ink-muted">No tables served on this day.</p>
      ) : (
        <>
          <div className="space-y-2">
            <SummarySourceChip source={r.summary_source} />
            <p className="text-sm leading-relaxed text-ink">{r.summary}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile label="Tables served" value={String(r.tables_served)} />
            <StatTile label="Average time per table" value={formatDuration(r.average_table_seconds)} />
            <StatTile
              label="Busiest hour"
              value={r.busiest_hour === null ? "–" : hourSpan(r.busiest_hour)}
            />
          </div>

          <div>
            <h4 className="text-sm font-bold text-ink">Average wait</h4>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              {(Object.keys(STAGE_LABELS) as Stage[]).map((s) => (
                <React.Fragment key={s}>
                  <dt className="text-ink-muted">{STAGE_LABELS[s]}</dt>
                  <dd className="text-ink">{formatDuration(r.average_wait_seconds[s])}</dd>
                </React.Fragment>
              ))}
            </dl>
          </div>

          {r.slowest_hour && (
            <p className="text-sm text-ink">
              Slowest hour: {hourSpan(r.slowest_hour.hour)}, {formatDuration(r.slowest_hour.average_table_seconds)} per
              table
              {r.slowest_hour.slowest_stage && `; slowest step: ${STAGE_LABELS[r.slowest_hour.slowest_stage]}`}
            </p>
          )}

          <div>
            <h4 className="text-sm font-bold text-ink">Red alerts</h4>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              {(Object.keys(ALERT_LABELS) as (keyof ServiceReport["alerts"])[]).map((k) => (
                <React.Fragment key={k}>
                  <dt className="text-ink-muted">{ALERT_LABELS[k]}</dt>
                  <dd className="text-ink font-mono">{r.alerts[k]}</dd>
                </React.Fragment>
              ))}
            </dl>
          </div>
        </>
      )}

      {r && (r.simulated_sittings > 0 || r.closed_without_bill > 0) && (
        <div className="text-xs text-ink-muted">
          {r.simulated_sittings > 0 && <p>Simulated tables: {r.simulated_sittings}</p>}
          {r.closed_without_bill > 0 && <p>Closed without a bill: {r.closed_without_bill}</p>}
        </div>
      )}
    </Card>
  );
}
