"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge, Button, Card, PageHeader, Sheet, formatPrice } from "ui";
import { useVenue, useSlugRef } from "../../../lib/venue";
import { useSse } from "../../../hooks/use-sse";
import {
  PAYMENT_METHODS,
  VOID_REASONS,
  amountDueText,
  apiError,
  billNo,
  claimChip,
  claimWarning,
  localDateTime,
  paymentLabel,
  previewFor,
  settlePayload,
  voidReason,
  type BillDetail,
  type BillOrder,
  type BillSummary,
  type PaymentMethod,
} from "../../../lib/bill";

const RELOAD_EVENTS = new Set([
  "bill_opened",
  "bill_requested",
  "bill_settled",
  "bill_cancelled",
  "order_placed",
  "order_voided",
  "payment_claimed",
]);
const NEEDS_REFERENCE = new Set(["wallet", "raast", "bank_transfer"]);
const BILL_CHANGED = "The bill changed — check the new total";

export default function BillsPage() {
  const { venue } = useVenue();
  const slug = venue?.slug;
  const slugRef = useSlugRef(slug);
  const router = useRouter();
  const [detail, setDetail] = useState<BillDetail | null>(null);
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [reference, setReference] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [refusedReference, setRefusedReference] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"open" | "cancelled">("open");
  // Void sheet
  const [voidTarget, setVoidTarget] = useState<BillOrder | null>(null);
  const [voidChoice, setVoidChoice] = useState<(typeof VOID_REASONS)[number]>("Wrong table");
  const [voidOther, setVoidOther] = useState("");
  const [voidClaim, setVoidClaim] = useState<string | null>(null);
  const [voidError, setVoidError] = useState<string | null>(null);
  const [voidBusy, setVoidBusy] = useState(false);
  // The bill the sheet shows; late responses for any other bill are dropped.
  const selectedId = useRef<string | null>(null);
  // The bill whose method and reference were pre-filled from the claim (once per opening).
  const prefilled = useRef<string | null>(null);
  const printHref = (id: string) => `/bills/${id}/print?venue=${encodeURIComponent(slug ?? "")}`;

  const fetchBills = useCallback(async (): Promise<{ bills: BillSummary[]; restaurant_timezone: string }> => {
    const res = await fetch(`/api/restaurants/${slug}/bills?status=${view}`);
    if (!res.ok) throw new Error(await apiError(res));
    return res.json();
  }, [slug, view]);

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

  // useSse keeps the latest fetchState in a ref; switching tabs reloads with the new filter.
  useEffect(() => {
    if (slug) void refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the tab changes
  }, [view]);

  const show = (body: BillDetail) => {
    setDetail(body);
    if (prefilled.current !== body.id) {
      // Method pre-selected from the guest's claim; staff can change it.
      prefilled.current = body.id;
      const claimed = PAYMENT_METHODS.find((m) => m.value === body.claim?.method)?.value;
      setMethod(claimed ?? "cash");
      setReference(body.claim?.reference ?? "");
    }
  };

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
      if (!stale()) show(body);
    } catch {
      if (!stale()) setError("Couldn't load the bill. Try again.");
    }
  };

  const select = (id: string) => {
    selectedId.current = id;
    prefilled.current = null;
    setDetail(null);
    setError(null);
    setNotice(null);
    setMethod("cash");
    setReference("");
    setAcknowledged(false);
    setRefusedReference(false);
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
    const body = settlePayload(detail, method, reference, acknowledged);
    if (!body) {
      setError("No tax rate configured");
      return;
    }
    const forSlug = slug;
    const billId = detail.id;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`/api/restaurants/${forSlug}/bills/${billId}/settle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (slugRef.current !== forSlug || selectedId.current !== billId) return;
      if (res.ok) {
        router.push(printHref(billId));
        return;
      }
      if (res.status === 409) {
        const conflict = (await res.json().catch(() => null)) as { detail?: unknown; bill?: BillDetail } | null;
        void refetch();
        if (conflict?.detail === "Bill changed" && conflict.bill) {
          // The server's fresh bill replaces what staff saw; they confirm again against the new total.
          show(conflict.bill);
          setNotice(BILL_CHANGED);
          return;
        }
        const message = typeof conflict?.detail === "string" ? conflict.detail : "The bill changed. Check it again.";
        setError(message);
        if (message.startsWith("Reference already used")) setRefusedReference(true);
        else void loadDetail(billId); // "already settled" / "not open": the reload shows it
        return;
      }
      setError(await apiError(res));
    } catch {
      setError("Network error. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const openVoid = (order: BillOrder) => {
    setVoidTarget(order);
    setVoidChoice("Wrong table");
    setVoidOther("");
    setVoidClaim(null);
    setVoidError(null);
  };

  const sendVoid = async (acknowledgeClaim: boolean) => {
    if (!voidTarget || !detail) return;
    const reason = voidReason(voidChoice, voidOther);
    if (!reason) {
      setVoidError("Type a reason (up to 200 characters).");
      return;
    }
    const forSlug = slug;
    const billId = detail.id;
    setVoidBusy(true);
    setVoidError(null);
    try {
      const res = await fetch(`/api/restaurants/${forSlug}/orders/${voidTarget.order_id}/void`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason, acknowledge_claim: acknowledgeClaim }),
      });
      if (slugRef.current !== forSlug || selectedId.current !== billId) return;
      if (res.ok) {
        show((await res.json()) as BillDetail);
        setVoidTarget(null);
        void refetch();
        return;
      }
      if (res.status === 409) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown; claim?: unknown } | null;
        const message = typeof body?.detail === "string" ? body.detail : "The bill changed. Check it again.";
        if (body?.claim) {
          setVoidClaim(message); // void would cancel a bill the guest says they paid: ask first
          return;
        }
        setVoidError(message);
        void loadDetail(billId);
        return;
      }
      setVoidError(await apiError(res));
    } catch {
      setVoidError("Network error. Try again.");
    } finally {
      setVoidBusy(false);
    }
  };

  const bills = data?.bills ?? [];
  const currency = venue?.currency ?? "PKR";
  const selected = detail ? previewFor(detail, method) : null;
  const claimNow = detail?.claim ? previewFor(detail, detail.claim.method) : null;
  const due = detail ? amountDueText(detail.amount_due_after_claim, detail.currency) : null;
  const ref = method === "cash" ? "" : reference.trim();
  const reusedWarnings = detail
    ? [
        ...(detail.reused_reference_bill_no !== null
          ? [`Reference ${detail.claim?.reference ?? ""} was already used on ${billNo(detail.reused_reference_bill_no)} (settled).`]
          : []),
        ...(detail.reused_reference_open_bill_no !== null
          ? [`The same reference is claimed on open ${billNo(detail.reused_reference_open_bill_no)}.`]
          : []),
      ]
    : [];
  const needsAck = reusedWarnings.length > 0 || refusedReference;
  const sheetTitle = detail ? `${detail.table_label ? `Table ${detail.table_label}` : "Bill"} · ${billNo(detail.bill_no)}` : "Bill";

  return (
    <div className="space-y-6">
      <PageHeader title="Bills" subtitle="Open table bills. Confirm a payment to print a sample bill." />

      <div role="tablist" aria-label="Bills" className="flex gap-2">
        {(["open", "cancelled"] as const).map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={view === v ? "btn-primary" : "btn-ghost"}
          >
            {v === "open" ? "Open" : "Cancelled"}
          </button>
        ))}
      </div>

      {listError && !data && (
        <p role="alert" className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-xs text-danger-fg">
          {listError.message}
        </p>
      )}

      {data && bills.length === 0 ? (
        <Card className="p-12 text-center text-sm text-ink-muted">
          {view === "open" ? "No open bills right now." : "No cancelled bills."}
        </Card>
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
                  {b.status === "cancelled" && (
                    <span className="block text-xs text-ink-muted">Cancelled: {b.cancel_reason ?? "—"}</span>
                  )}
                  {b.status === "cancelled" && b.claim && (
                    <span className="block text-xs font-semibold text-danger-fg">{claimWarning(b.claim, currency)}</span>
                  )}
                </span>
                <span className="flex flex-wrap items-center gap-3">
                  {b.status === "open" && b.claim ? (
                    <Badge className="bg-terracotta text-cream">{claimChip(b.claim)}</Badge>
                  ) : (
                    b.bill_requested_at && <Badge className="bg-terracotta text-cream">Bill requested</Badge>
                  )}
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
        title={sheetTitle}
        footer={
          detail?.status === "open" && (
            <Button className="w-full" onClick={settle} disabled={busy || !selected || (needsAck && !acknowledged)}>
              {busy ? "Saving…" : "Confirm received"}
            </Button>
          )
        }
      >
        {notice && (
          <p role="alert" className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-sm font-semibold text-danger-fg">
            {notice}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger-fg">
            {error}
          </p>
        )}
        {!detail ? (
          !error && <p className="text-sm text-ink-muted">Loading…</p>
        ) : (
          <>
            {detail.status === "open" && (
              <div className="space-y-1 rounded-xl border border-line bg-paper-2 p-4 text-center">
                <p className="text-lg font-semibold text-ink">{sheetTitle}</p>
                <p className="font-serif text-4xl font-bold text-ink">
                  {selected ? formatPrice(Number(selected.total), detail.currency) : "No tax rate configured"}
                </p>
                <p className="text-lg text-ink">
                  {paymentLabel(method)}
                  {ref && <span className="font-mono"> · ref {ref}</span>}
                </p>
              </div>
            )}

            {detail.status === "open" && NEEDS_REFERENCE.has(method) && selected && (
              <p className="text-sm font-semibold text-ink">
                Check your JazzCash / bank app for ref {ref || "…"} and {formatPrice(Number(selected.total), detail.currency)} before
                confirming.
              </p>
            )}

            {detail.status === "open" && detail.claim && due && (
              <p className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-sm font-semibold text-danger-fg">
                Guest sent {formatPrice(Number(detail.claim.total), detail.currency)} · bill is now{" "}
                {claimNow ? formatPrice(Number(claimNow.total), detail.currency) : "—"} · {due}
              </p>
            )}

            {detail.status === "open" && needsAck && (
              <div className="space-y-2 rounded-xl border border-danger-fg bg-danger-bg p-3 text-sm text-danger-fg">
                {reusedWarnings.map((w) => (
                  <p key={w} className="font-semibold">
                    {w}
                  </p>
                ))}
                <label className="flex items-center gap-2 font-semibold">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                    className="accent-terracotta"
                  />
                  I&apos;ve checked — confirm anyway
                </label>
              </div>
            )}

            <ul className="space-y-3">
              {detail.orders.map((o) => (
                <li key={o.order_id} className="space-y-1 rounded-xl border border-line p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-ink">{o.device_label}</span>
                      {o.joined_late && (
                        <span className="chip chip-contains">
                          <span aria-hidden="true">⚠</span>Joined late
                        </span>
                      )}
                      <span className="text-xs text-ink-muted">{localDateTime(o.placed_at, detail.restaurant_timezone)}</span>
                    </span>
                    {detail.status === "open" && !o.voided && (o.status === "placed" || o.status === "bumped") && (
                      <Button variant="outline" aria-label={`Void ${o.device_label} order`} onClick={() => openVoid(o)}>
                        Void
                      </Button>
                    )}
                  </div>
                  {o.voided && <p className="text-xs font-semibold text-danger-fg">Voided: {o.void_reason ?? "—"}</p>}
                  <ul className={o.voided ? "text-ink-muted line-through" : "text-ink"}>
                    {o.lines.map((l, i) => (
                      <li key={i} className="flex justify-between gap-3">
                        <span>
                          {l.quantity} × {l.name}
                          {l.option_label && <span className="text-ink-muted"> — {l.option_label}</span>}
                        </span>
                        <span className="text-ink-muted">{formatPrice(Number(l.line_total), detail.currency)}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
            <p className="flex justify-between text-sm font-semibold text-ink">
              <span>Subtotal</span>
              <span>{formatPrice(Number(detail.subtotal), detail.currency)}</span>
            </p>

            {detail.status === "cancelled" ? (
              <div className="space-y-1 text-sm">
                <p className="text-ink-muted">
                  Cancelled: {detail.cancel_reason ?? "—"}
                  {detail.cancelled_by_name && ` · by ${detail.cancelled_by_name}`}
                  {detail.cancelled_at && ` · ${localDateTime(detail.cancelled_at, detail.restaurant_timezone)}`}
                </p>
                {detail.claim && <p className="font-semibold text-danger-fg">{claimWarning(detail.claim, detail.currency)}</p>}
              </div>
            ) : detail.status !== "open" ? (
              <p className="text-sm text-ink-muted">
                This bill is already settled{detail.settled_by_name && ` by ${detail.settled_by_name}`}.{" "}
                <Link href={printHref(detail.id)} className="font-semibold text-terracotta underline">
                  Open sample bill
                </Link>
              </p>
            ) : (
              <>
                <fieldset className="space-y-2">
                  <legend className="text-sm font-semibold text-ink">Payment method</legend>
                  {PAYMENT_METHODS.map((m) => {
                    const p = previewFor(detail, m.value);
                    return (
                      <label key={m.value} className="flex items-center justify-between gap-2 text-sm text-ink">
                        <span className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="payment_method"
                            value={m.value}
                            checked={method === m.value}
                            onChange={() => {
                              setMethod(m.value);
                              setNotice(null);
                            }}
                            className="accent-terracotta"
                          />
                          {m.label}
                          {p && (
                            <span className="text-xs text-ink-muted">tax {Number((Number(p.tax_rate) * 100).toFixed(2))}%</span>
                          )}
                        </span>
                        <span className="font-semibold">{p ? formatPrice(Number(p.total), detail.currency) : "—"}</span>
                      </label>
                    );
                  })}
                </fieldset>

                {method !== "cash" && (
                  <label className="block space-y-1 text-sm text-ink">
                    <span>Reference{NEEDS_REFERENCE.has(method) ? "" : " (optional)"}</span>
                    <input
                      type="text"
                      value={reference}
                      maxLength={64}
                      onChange={(e) => {
                        setReference(e.target.value);
                        setRefusedReference(false);
                        setAcknowledged(false);
                      }}
                      className="w-full rounded-lg border border-line bg-paper px-3 py-2 focus:border-terracotta focus:outline-none focus:ring-1 focus:ring-terracotta"
                    />
                  </label>
                )}
              </>
            )}
          </>
        )}
      </Sheet>

      <Sheet open={voidTarget !== null} onClose={() => setVoidTarget(null)} title={voidTarget ? `Void ${voidTarget.device_label} order` : "Void order"}>
        <label className="block space-y-1 text-sm text-ink">
          <span>Reason</span>
          <select
            value={voidChoice}
            onChange={(e) => {
              setVoidChoice(e.target.value as (typeof VOID_REASONS)[number]);
              setVoidClaim(null);
            }}
            className="w-full rounded-lg border border-line bg-paper px-3 py-2"
          >
            {VOID_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        {voidChoice === "Other" && (
          <label className="block space-y-1 text-sm text-ink">
            <span>Describe the reason</span>
            <input
              type="text"
              value={voidOther}
              maxLength={200}
              onChange={(e) => setVoidOther(e.target.value)}
              className="w-full rounded-lg border border-line bg-paper px-3 py-2 focus:border-terracotta focus:outline-none focus:ring-1 focus:ring-terracotta"
            />
          </label>
        )}
        {voidError && (
          <p role="alert" className="text-sm text-danger-fg">
            {voidError}
          </p>
        )}
        {voidClaim ? (
          <div className="space-y-2">
            <p role="alert" className="rounded-xl border border-danger-fg bg-danger-bg p-3 text-sm font-semibold text-danger-fg">
              {voidClaim}
            </p>
            <Button variant="danger" className="w-full" disabled={voidBusy} onClick={() => void sendVoid(true)}>
              Void and cancel bill
            </Button>
          </div>
        ) : (
          <Button variant="danger" className="w-full" disabled={voidBusy} onClick={() => void sendVoid(false)}>
            {voidBusy ? "Voiding…" : "Void order"}
          </Button>
        )}
      </Sheet>
    </div>
  );
}
