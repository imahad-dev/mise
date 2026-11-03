"use client";

import React, { use, useEffect, useState } from "react";
import Image from "next/image";
import { Button } from "ui";
import { VenueProvider, useVenue } from "../../../../lib/venue";
import { apiError, sampleBillPieces, type BillDetail, type BillRow } from "../../../../lib/bill";

function Row({ row, strong }: { row: BillRow; strong?: boolean }) {
  return (
    <p className={`flex justify-between gap-3 ${strong ? "font-bold" : ""}`}>
      <span>{row.label}</span>
      <span className="whitespace-nowrap">{row.amount}</span>
    </p>
  );
}

function PrintBill({ id, venueParam }: { id: string; venueParam: string | undefined }) {
  const { venues, venue, error: venueError } = useVenue();
  // The link from the Bills page names the venue; fall back to the selected one if it is not ours.
  const slug = venues.find((v) => v.slug === venueParam)?.slug ?? venue?.slug;
  const [bill, setBill] = useState<BillDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setBill(null);
    setError(null);
    fetch(`/api/restaurants/${slug}/bills/${id}`)
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) return setError(await apiError(res));
        setBill((await res.json()) as BillDetail);
      })
      .catch(() => !cancelled && setError("Couldn't load the bill."));
    return () => {
      cancelled = true;
    };
  }, [slug, id]);

  if (venueError === "unauthorized") return null; // the provider is redirecting to /login
  if (venueError || error) {
    return (
      <p role="alert" className="p-6 text-center text-sm text-danger-fg">
        {error ?? "Couldn't load your restaurants."}
      </p>
    );
  }
  if (!bill) return <p className="p-6 text-center text-sm text-ink-muted">Loading…</p>;
  if (bill.status !== "settled") return <p className="p-6 text-center text-sm text-ink">Not settled yet</p>;

  const p = sampleBillPieces(bill);
  return (
    <main className="mx-auto w-full max-w-[80mm] space-y-3 p-2 font-mono text-sm text-ink">
      <div className="space-y-0.5 text-center">
        <Image src="/brand/logo-mark.svg" alt="" width={24} height={24} className="mx-auto" />
        {p.header.map((line, i) => (
          <p key={i} className={i === 0 ? "font-bold" : ""}>
            {line}
          </p>
        ))}
      </div>
      <div className="space-y-1 border-y border-dashed border-ink py-2">
        {p.lines.map((r, i) => (
          <Row key={i} row={r} />
        ))}
      </div>
      <div className="space-y-1">
        {p.totals.map((r, i) => (
          <Row key={i} row={r} strong={i === p.totals.length - 1} />
        ))}
        <p>{p.payment}</p>
      </div>
      <p className="border-t border-dashed border-ink pt-2 text-center font-bold">{p.footer}</p>
      <Button className="w-full print:hidden" onClick={() => window.print()}>
        Print
      </Button>
    </main>
  );
}

export default function PrintBillPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ venue?: string | string[] }>;
}) {
  const { id } = use(params);
  const { venue } = use(searchParams);
  return (
    <VenueProvider>
      <PrintBill id={id} venueParam={typeof venue === "string" ? venue : undefined} />
    </VenueProvider>
  );
}
