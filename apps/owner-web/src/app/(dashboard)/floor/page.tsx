"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, Card, PageHeader, formatPrice } from "ui";
import { useVenue, useSlugRef } from "../../../lib/venue";
import { useSse } from "../../../hooks/use-sse";
import { apiError } from "../../../lib/bill";
import {
  elapsed,
  formatElapsed,
  isStale,
  levelClass,
  levelText,
  sortTiles,
  stateIcon,
  stateLabel,
  type FloorResponse,
  type FloorTile,
} from "../../../lib/floor";

// The one refusal that clearing anyway (force) may override; an open bill must be settled first.
const NEW_GUESTS = "New guests are already seated";

interface Loaded {
  floor: FloorResponse;
  loadedAt: number;
}

export default function FloorPage() {
  const { venue } = useVenue();
  const slug = venue?.slug;
  const slugRef = useSlugRef(slug);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // A refused "Mark cleared": the server's reason, and whether clearing anyway is allowed.
  const [refusedClear, setRefusedClear] = useState<{ table: FloorTile; message: string } | null>(null);

  const fetchFloor = useCallback(async (): Promise<Loaded> => {
    const res = await fetch(`/api/restaurants/${slug}/floor`);
    if (!res.ok) throw new Error(await apiError(res));
    return { floor: (await res.json()) as FloorResponse, loadedAt: Date.now() };
  }, [slug]);

  // useSse reloads on every kitchen-stream message (calls, clears, orders, bills) and drops stale responses.
  const { data, error, refetch } = useSse<Loaded>({
    url: slug ? `/api/restaurants/${slug}/kitchen/stream` : null,
    enabled: Boolean(slug),
    fetchState: fetchFloor,
  });

  useEffect(() => {
    if (!slug) return;
    const reload = setInterval(() => void refetch(), 30_000);
    return () => clearInterval(reload);
  }, [slug, refetch]);

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    setActionError(null);
    setRefusedClear(null);
  }, [slug]);

  /** POST and reload; null when the venue changed meanwhile or the network failed. */
  const post = async (key: string, path: string, body?: object): Promise<Response | null> => {
    const forSlug = slug;
    setBusy(key);
    setActionError(null);
    setRefusedClear(null);
    try {
      const res = await fetch(`/api/restaurants/${forSlug}${path}`, {
        method: "POST",
        ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      if (slugRef.current !== forSlug) return null;
      void refetch();
      return res;
    } catch {
      if (slugRef.current === forSlug) setActionError("Network error. Try again.");
      return null;
    } finally {
      setBusy(null);
    }
  };

  const resolve = async (t: FloorTile) => {
    const res = await post(t.table_id, `/service-calls/${t.call_id}/resolve`);
    // 409: someone else already resolved it, which is what this tap wanted.
    if (res && !res.ok && res.status !== 409) setActionError(await apiError(res));
  };

  const clear = async (t: FloorTile, force = false) => {
    const res = await post(t.table_id, `/tables/${t.table_id}/clear`, force ? { force: true } : undefined);
    if (!res || res.ok) return;
    if (res.status === 409) setRefusedClear({ table: t, message: await apiError(res) });
    else setActionError(await apiError(res));
  };

  const currency = venue?.currency ?? "PKR";
  const tiles = data ? sortTiles(data.floor.tiles) : [];
  const ageMs = data ? now - data.loadedAt : 0;

  const timer = (t: FloorTile) =>
    data && t.since ? formatElapsed(elapsed(t.since, data.floor.server_time, now, data.loadedAt)) : null;

  return (
    <div className="space-y-6">
      <PageHeader title="Floor" subtitle="Every table at a glance. Red first, then amber." />

      {data && isStale(ageMs) && (
        <p role="status" className="rounded-xl border border-warn-fg bg-warn-bg p-3 text-xs font-semibold text-warn-fg">
          Reconnecting — last updated over 45 s ago
          <span aria-hidden="true"> ({Math.round(ageMs / 1000)} s)</span>
        </p>
      )}
      {error && !data && (
        <p role="alert" className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-xs text-danger-fg">
          {error.message}
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-xs text-danger-fg">
          {actionError}
        </p>
      )}
      {refusedClear && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-warn-fg bg-warn-bg p-3 text-sm text-warn-fg">
          <span className="font-semibold">
            {refusedClear.table.label}: {refusedClear.message}
          </span>
          {refusedClear.message === NEW_GUESTS && (
            <Button disabled={busy !== null} onClick={() => clear(refusedClear.table, true)}>
              Clear anyway
            </Button>
          )}
          <button type="button" className="btn-ghost" onClick={() => setRefusedClear(null)}>
            Dismiss
          </button>
        </div>
      )}

      {data && tiles.length === 0 ? (
        <Card className="p-12 text-center text-sm text-ink-muted">No tables yet. Add them under Tables &amp; QR.</Card>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {tiles.map((t) => {
            const level = levelText(t.level);
            const time = timer(t);
            return (
              <li key={t.table_id}>
                <Card className={`flex h-full flex-col gap-2 p-4 ${levelClass(t.level)}`}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-serif text-2xl font-bold">{t.label}</span>
                    {level && <span className="text-xs font-semibold uppercase tracking-wider">{level}</span>}
                  </div>
                  <p className="flex items-center gap-2 text-sm font-semibold">
                    <span aria-hidden="true">{stateIcon(t.state)}</span>
                    {stateLabel(t.state)}
                    {time && <span className="ml-auto font-mono tabular-nums">{time}</span>}
                  </p>
                  {t.reason_label && <p className="text-sm">{t.reason_label}</p>}
                  {t.running_total !== null && (
                    <p className="text-sm">{formatPrice(Number(t.running_total), currency)}</p>
                  )}
                  <div className="mt-auto flex flex-wrap gap-2 pt-1">
                    {t.state === "called" && t.call_id && (
                      <Button
                        aria-label={`Done, ${t.label}`}
                        disabled={busy !== null}
                        onClick={() => resolve(t)}
                      >
                        Done
                      </Button>
                    )}
                    {t.state === "needs_clearing" && (
                      <Button
                        aria-label={`Mark cleared, ${t.label}`}
                        disabled={busy !== null}
                        onClick={() => clear(t)}
                      >
                        Mark cleared
                      </Button>
                    )}
                    {t.bill_id && (
                      <Link href={`/bills?bill=${t.bill_id}`} aria-label={`Open bill, ${t.label}`} className="btn-ghost">
                        Open bill
                      </Link>
                    )}
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
