"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge, Button, Card, PageHeader, Sheet, formatPrice } from "ui";
import { useVenue, useSlugRef } from "../../../lib/venue";
import { useSse } from "../../../hooks/use-sse";
import {
  PAYMENT_METHODS,
  apiError,
  billNo,
  localDateTime,
  type BillDetail,
  type BillSummary,
  type PaymentMethod,
  type TaxPreview,
} from "../../../lib/bill";

const RELOAD_EVENTS = new Set(["bill_opened", "bill_requested", "bill_settled", "order_placed"]);

function PreviewCard({ title, preview, currency }: { title: string; preview: TaxPreview | null; currency: string }) {
  return (
    <Card className="space-y-1 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{title}</p>
      {preview ? (
        <>
          <p className="text-sm text-ink-muted">
            Tax {Number((Number(preview.tax_rate) * 100).toFixed(2))}% · {formatPrice(Number(preview.tax_amount), currency)}
          </p>
          <p className="font-serif text-2xl font-bold text-ink">{formatPrice(Number(preview.total), currency)}</p>
        </>
      ) : (
        <p className="text-sm text-ink-muted">No tax rate configured</p>
      )}
    </Card>
  );
}

export default function BillsPage() {
  const { venue } = useVenue();
  const slug = venue?.slug;
  const slugRef = useSlugRef(slug);
  const router = useRouter();
  const [detail, setDetail] = useState<BillDetail | null>(null);
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The bill the sheet shows; late responses for any other bill are dropped.
  const selectedId = useRef<string | null>(null);
  const printHref = (id: string) => `/bills/${id}/print?venue=${encodeURIComponent(slug ?? "")}`;

  const fetchBills = useCallback(async (): Promise<{ bills: BillSummary[]; restaurant_timezone: string }> => {
    const res = await fetch(`/api/restaurants/${slug}/bills?status=open`);
    if (!res.ok) throw new Error(await apiError(res));
    return res.json();
  }, [slug]);

  const { data, error: listError, refetch } = useSse<{ bills: BillSummary[]; restaurant_timezone: string }>({
    url: slug ? `/api/restaurants/${slug}/kitchen/stream` : null,
    enabled: Boolean(slug),
    fetchState: fetchBills,
    // useSse already reloads the list on every stream message; bill events also refresh the open sheet.
    onMessage: (e) => {
      try {
        if (RELOAD_EVENTS.has(JSON.parse(e.data).event) && open && detail) void loadDetail(detail.id);
      } catch {
        // non-JSON keepalive
      }
    },
  });

  const loadDetail = async (id: string) => {
    const forSlug = slug;
    const stale = () => slugRef.current !== forSlug || selectedId.current !== id;
    try {
      const res = await fetch(`/api/restaurants/${forSlug}/bills/${id}`);
      if (stale()) return;
      if (!res.ok) {
        const message = await apiError(res);
        if (!stale()) setError(message);
        return;
      }
      const body = (await res.json()) as BillDetail;
      if (!stale()) setDetail(body);
    } catch {
      if (!stale()) setError("Couldn't load the bill. Try again.");
    }
  };

  const select = (id: string) => {
    selectedId.current = id;
    setDetail(null);
    setError(null);
    setMethod("cash");
    setReference("");
    setOpen(true);
    void loadDetail(id);
  };

  // "Open bill" on the Floor links here as /bills?bill={id}: open that bill's sheet once the venue is known.
  // window.location instead of useSearchParams, which would need a Suspense boundary for the build.
  const linkedBill = useRef(false);
  useEffect(() => {
    if (!slug || linkedBill.current) return;
    linkedBill.current = true;
    const id = new URLSearchParams(window.location.search).get("bill");
    if (id) select(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per page load
  }, [slug]);

  const settle = async () => {
    if (!detail) return;
    const forSlug = slug;
    const billId = detail.id;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/restaurants/${forSlug}/bills/${billId}/settle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payment_method: method,
          payment_reference: method === "cash" || !reference.trim() ? null : reference.trim(),
        }),
      });
      if (slugRef.current !== forSlug || selectedId.current !== billId) return;
      if (res.ok) {
        router.push(printHref(billId));
        return;
      }
      if (res.status === 409) {
        void refetch();
        void loadDetail(billId);
        return; // the reloaded detail shows "already settled" with its print link
      }
      setError(await apiError(res));
    } catch {
      setError("Network error. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const bills = data?.bills ?? [];
  const currency = venue?.currency ?? "PKR";

  return (
    <div className="space-y-6">
      <PageHeader title="Bills" subtitle="Open table bills. Mark one paid to print a sample bill." />

      {listError && !data && (
        <p role="alert" className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-xs text-danger-fg">
          {listError.message}
        </p>
      )}

      {data && bills.length === 0 ? (
        <Card className="p-12 text-center text-sm text-ink-muted">No open bills right now.</Card>
      ) : (
        <ul className="space-y-2">
          {bills.map((b) => (
            <li key={b.id}>
              <button
                type="button"
                onClick={() => select(b.id)}
                className="mise-card flex w-full flex-wrap items-center justify-between gap-3 text-left hover:border-terracotta"
              >
                <span>
                  <span className="block font-semibold text-ink">{b.table_label ? `Table ${b.table_label}` : "No table"}</span>
                  <span className="block text-xs text-ink-muted">
                    {billNo(b.bill_no)} · opened {localDateTime(b.opened_at, data?.restaurant_timezone ?? "UTC")} · {b.order_count}{" "}
                    {b.order_count === 1 ? "order" : "orders"}
                  </span>
                </span>
                <span className="flex items-center gap-3">
                  {b.bill_requested_at && <Badge className="bg-terracotta text-cream">Bill requested</Badge>}
                  <span className="font-semibold text-ink">{formatPrice(Number(b.subtotal), currency)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Sheet
        open={open}
        onClose={() => {
          selectedId.current = null;
          setOpen(false);
        }}
        title={detail ? `${detail.table_label ? `Table ${detail.table_label}` : "Bill"} · ${billNo(detail.bill_no)}` : "Bill"}
        footer={
          detail?.status === "open" && (
            <>
              <Button className="w-full" onClick={settle} disabled={busy}>
                {busy ? "Saving…" : "Mark paid"}
              </Button>
            </>
          )
        }
      >
        {error && (
          <p role="alert" className="text-sm text-danger-fg">
            {error}
          </p>
        )}
        {!detail ? (
          !error && <p className="text-sm text-ink-muted">Loading…</p>
        ) : (
          <>
            <ul className="divide-y divide-line text-sm">
              {detail.lines.map((l, i) => (
                <li key={i} className="flex justify-between gap-3 py-2">
                  <span className="text-ink">
                    {l.quantity} × {l.name}
                    {l.option_label && <span className="text-ink-muted"> — {l.option_label}</span>}
                  </span>
                  <span className="text-ink-muted">{formatPrice(Number(l.line_total), detail.currency)}</span>
                </li>
              ))}
            </ul>
            <p className="flex justify-between text-sm font-semibold text-ink">
              <span>Subtotal</span>
              <span>{formatPrice(Number(detail.subtotal), detail.currency)}</span>
            </p>

            {detail.status !== "open" ? (
              <p className="text-sm text-ink-muted">
                This bill is already settled.{" "}
                <Link href={printHref(detail.id)} className="font-semibold text-terracotta underline">
                  Open sample bill
                </Link>
              </p>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <PreviewCard title="Cash or bank transfer" preview={detail.preview_standard} currency={detail.currency} />
                  <PreviewCard title="Card, wallet or QR" preview={detail.preview_digital} currency={detail.currency} />
                </div>

                <fieldset className="space-y-2">
                  <legend className="text-sm font-semibold text-ink">Payment method</legend>
                  {PAYMENT_METHODS.map((m) => (
                    <label key={m.value} className="flex items-center gap-2 text-sm text-ink">
                      <input
                        type="radio"
                        name="payment_method"
                        value={m.value}
                        checked={method === m.value}
                        onChange={() => setMethod(m.value)}
                        className="accent-terracotta"
                      />
                      {m.label}
                    </label>
                  ))}
                </fieldset>

                {method !== "cash" && (
                  <label className="block space-y-1 text-sm text-ink">
                    <span>Reference (optional)</span>
                    <input
                      type="text"
                      value={reference}
                      maxLength={64}
                      onChange={(e) => setReference(e.target.value)}
                      className="w-full rounded-lg border border-line bg-paper px-3 py-2 focus:border-terracotta focus:outline-none focus:ring-1 focus:ring-terracotta"
                    />
                  </label>
                )}
              </>
            )}
          </>
        )}
      </Sheet>
    </div>
  );
}
