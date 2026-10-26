"use client";

import React, { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CallWaiter } from "../../../../components/CallWaiter";
import { PaySheet } from "../../../../components/PaySheet";
import { ChatPanel } from "../../../../components/chat-panel";
import { useSse } from "../../../../hooks/use-sse";
import { getDictionary } from "../../../../i18n";
import { Button, formatPrice } from "ui";
import { VISIT_ENDED, billState, claimMessage, type GuestBill } from "../../../../lib/pay";

interface OrderItem {
  id: string;
  item_name: string;
  option_label?: string | null;
  quantity: number;
  unit_price: string | number;
  notes?: string | null;
  allergen_status: string;
}

/** The table bill for this guest session: polled every 10 s while open, every 30 s otherwise (a new order opens a new bill). */
function useGuestBill() {
  const [bill, setBill] = useState<GuestBill | null>(null);
  const [ended, setEnded] = useState(false);
  const slow = Boolean(bill && bill.status !== "open");

  const load = useCallback(
    () =>
      fetch("/api/guest/bill")
        .then(async (r) => {
          if (r.status === 404) setBill(null);
          else if (r.ok) setBill((await r.json()) as GuestBill);
          // other errors: keep the last known bill
        })
        .catch(() => {}),
    [],
  );

  useEffect(() => {
    void load();
    const timer = setInterval(load, slow ? 30_000 : 10_000);
    return () => clearInterval(timer);
  }, [slow, load]);

  return { bill, setBill, ended, setEnded, reload: load };
}

interface OrderDetails {
  id: string;
  table_label?: string | null;
  status: "placed" | "bumped" | "cancelled" | string;
  total: string | number;
  currency: string;
  placed_at: string;
  bumped_at?: string | null;
  items: OrderItem[];
}

export default function OrderStatusPage({
  params,
}: {
  params: Promise<{ lang: string; id: string }>;
}) {
  const { lang, id } = use(params);
  const dict = getDictionary(lang);
  const { bill, setBill, ended, setEnded, reload } = useGuestBill();
  const [paying, setPaying] = useState(false);
  const state = billState(bill, ended);

  const fetchOrderState = useCallback(async (): Promise<OrderDetails> => {
    const res = await fetch(`/api/orders/${id}`);
    if (!res.ok) {
      throw new Error(`Failed to load order (${res.status})`);
    }
    return res.json();
  }, [id]);

  const {
    data: order,
    isReconnecting,
    error,
  } = useSse<OrderDetails>({
    url: `/api/orders/${id}/stream`,
    fetchState: fetchOrderState,
    pollingIntervalMs: 4000,
  });

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "placed":
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-safe-bg text-safe-fg border border-safe-fg/40">
            {dict.ui.statusPlaced}
          </span>
        );
      case "bumped":
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-paper-2 text-ink border border-terracotta/60">
            {dict.ui.statusBumped}
          </span>
        );
      case "cancelled":
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-danger-bg text-danger-fg border border-danger-fg/40">
            {dict.ui.statusCancelled}
          </span>
        );
      default:
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-paper-2 text-ink-muted">
            {status || "..."}
          </span>
        );
    }
  };

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col justify-between">
      {/* Reconnecting banner (SSE down or reconnecting) */}
      {isReconnecting && (
        <div
          data-testid="reconnecting-banner"
          className="bg-warn-fg text-cream px-4 py-2 text-xs font-bold text-center flex items-center justify-center gap-2 sticky top-0 z-50 animate-pulse"
        >
          <span className="w-2 h-2 rounded-full bg-paper" />
          {dict.ui.reconnecting}
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <header className="flex items-center justify-between border-b border-line pb-4">
          <div>
            <h1 className="text-xl font-bold text-ink">{dict.ui.orderStatus}</h1>
            <p className="text-xs text-ink-muted font-mono mt-0.5">ID: {id}</p>
          </div>
          <div className="flex items-center gap-2">
            <CallWaiter lang={lang} />
            {order && getStatusBadge(order.status)}
          </div>
        </header>

        {error && !order && (
          <div className="p-4 bg-danger-bg border border-danger-fg/40 rounded-2xl text-xs text-danger-fg">
            {error.message}
          </div>
        )}

        {order ? (
          <div className="space-y-6">
            {/* Status Summary Card */}
            <div className="p-5 rounded-2xl bg-card border border-line space-y-4">
              {order.table_label && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-ink-muted">{dict.ui.table}</span>
                  <span className="font-medium text-terracotta">{order.table_label}</span>
                </div>
              )}
              <div className="flex items-center justify-between text-sm">
                <span className="text-ink-muted">{dict.ui.placedAt}</span>
                <span className="text-xs text-ink-muted font-mono">
                  {new Date(order.placed_at).toLocaleTimeString()}
                </span>
              </div>
            </div>

            <div className="p-5 rounded-2xl bg-card border border-line text-sm text-ink space-y-3">
              {/* One polite region: the text changes only when the bill's state does. */}
              <p aria-live="polite" className={state === "cancelled" || state === "ended" ? "font-semibold text-danger-fg" : ""}>
                {state === "none" && dict.pay.noBill}
                {state === "paid" && dict.bill.paid.replace("{billNo}", String(bill?.bill_no ?? "").padStart(4, "0"))}
                {state === "cancelled" && dict.pay.cancelled}
                {state === "ended" && dict.pay.visitEnded}
                {state === "claimed" && bill?.claim && claimMessage(bill.claim, dict, lang, bill.currency)}
              </p>
              {bill?.voided.map((v, i) => (
                <p key={i} className="text-danger-fg">
                  {dict.pay.removed
                    .replace("{name}", v.option_label ? `${v.name} — ${v.option_label}` : v.name)
                    .replace("{qty}", String(v.quantity))}
                </p>
              ))}
              {(state === "open" || state === "claimed") && (
                <Button className="w-full" onClick={() => setPaying(true)}>
                  {dict.pay.button}
                </Button>
              )}
            </div>
            {bill && (
              <PaySheet
                lang={lang}
                bill={bill}
                open={paying}
                onClose={() => setPaying(false)}
                onUpdated={setBill}
                onConflict={(detail) => {
                  if (detail === VISIT_ENDED) setEnded(true);
                  setPaying(false);
                  void reload();
                }}
              />
            )}

            {/* Items List */}
            <div className="rounded-2xl bg-card border border-line p-5 space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-ink-muted border-b border-line pb-2">
                {dict.ui.items}
              </h2>
              <div className="divide-y divide-line">
                {order.items.map((item) => (
                  <div key={item.id} className="py-2.5 flex items-start justify-between text-sm">
                    <div>
                      <div className="font-medium text-ink">
                        {item.quantity}x {item.item_name}
                        {item.option_label && ` — ${item.option_label}`}
                      </div>
                      {item.notes && (
                        <p className="text-xs text-ink-muted italic mt-0.5">Note: {item.notes}</p>
                      )}
                    </div>
                    <span className="font-semibold text-ink-muted">
                      {formatPrice(Number(item.unit_price) * item.quantity, order.currency, lang)}
                    </span>
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-line flex items-center justify-between font-bold text-sm">
                <span className="text-ink-muted">{dict.ui.total}</span>
                <span className="text-terracotta text-base">
                  {formatPrice(Number(order.total), order.currency, lang)}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-12 flex flex-col items-center justify-center gap-3">
            <div className="w-6 h-6 border-2 border-terracotta border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-ink-muted">Connecting to order stream...</p>
          </div>
        )}

        <div className="pt-4 text-center">
          <Link
            href={`/${lang}/menu`}
            className="inline-block px-5 py-2.5 rounded-xl bg-paper-2 hover:bg-paper-2 text-xs font-medium text-ink transition-all"
          >
            ← {dict.ui.backToMenu}
          </Link>
        </div>
      </main>

      {/* Floating Chat Assistant */}
      <ChatPanel locale={lang} />
    </div>
  );
}
