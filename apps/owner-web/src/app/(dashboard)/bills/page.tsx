"use client";

import React, { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, Button, Card, PageHeader, Sheet, formatPrice } from "ui";
import { useVenue, useSlugRef } from "../../../lib/venue";
import { useSse } from "../../../hooks/use-sse";
import {
  PAYMENT_METHODS,
  apiError,
  billNo,
  karachiDateTime,
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

  const fetchBills = useCallback(async (): Promise<{ bills: BillSummary[] }> => {
    const res = await fetch(`/api/restaurants/${slug}/bills?status=open`);
    if (!res.ok) throw new Error(await apiError(res));
    return res.json();
  }, [slug]);

  const { data, error: listError, refetch } = useSse<{ bills: BillSummary[] }>({
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
    const res = await fetch(`/api/restaurants/${forSlug}/bills/${id}`);
    if (slugRef.current !== forSlug) return;
    if (!res.ok) {
      setError(await apiError(res));
      return;
    }
    setDetail((await res.json()) as BillDetail);
  };

  const select = (id: string) => {
    setDetail(null);
    setError(null);
    setMethod("cash");
    setReference("");
    setOpen(true);
    void loadDetail(id);
  };

  const settle = async () => {
    if (!detail) return;
    const forSlug = slug;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/restaurants/${forSlug}/bills/${detail.id}/settle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payment_method: method,
          payment_reference: method === "cash" || !reference.trim() ? null : reference.trim(),
        }),
      });
      if (slugRef.current !== forSlug) return;
      if (res.ok) {
        router.push(`/bills/${detail.id}/print`);
        return;
      }
      setError(await apiError(res));
      if (res.status === 409) {
        void refetch();
        void loadDetail(detail.id);
      }
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
                    {billNo(b.bill_no)} · opened {karachiDateTime(b.opened_at)} · {b.order_count}{" "}
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
        onClose={() => setOpen(false)}
        title={detail ? `${detail.table_label ? `Table ${detail.table_label}` : "Bill"} · ${billNo(detail.bill_no)}` : "Bill"}
        footer={
          detail?.status === "open" && (
            <>
              {error && (
                <p role="alert" className="text-sm text-danger-fg">
                  {error}
                </p>
              )}
              <Button className="w-full" onClick={settle} disabled={busy}>
                {busy ? "Saving…" : "Mark paid"}
              </Button>
            </>
          )
        }
      >
        {!detail ? (
          error ? (
            <p role="alert" className="text-sm text-danger-fg">
              {error}
            </p>
          ) : (
            <p className="text-sm text-ink-muted">Loading…</p>
          )
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
              <p className="text-sm text-ink-muted">This bill is already settled.</p>
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
