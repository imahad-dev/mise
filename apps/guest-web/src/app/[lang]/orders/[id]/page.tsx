"use client";

import React, { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CallWaiter } from "../../../../components/CallWaiter";
import { PaySheet } from "../../../../components/PaySheet";
import { ChatPanel } from "../../../../components/chat-panel";
import { useSse } from "../../../../hooks/use-sse";
import { getDictionary } from "../../../../i18n";
import { Button, formatPrice } from "ui";
import { orderStage } from "../../../../lib/ordering";
import { VISIT_ENDED, billState, claimMessage, counterState, paidText, payForwardThanks, type GuestBill } from "../../../../lib/pay";

interface OrderItem {
  id: string;
  item_name: string;
  option_label?: string | null;
  quantity: number;
  unit_price: string | number;
  notes?: string | null;
  allergen_status: string;
}

/**
 * This order's bill (its own counter bill, or the table bill it is on): polled every 10 s while
 * open or while a paid counter order is still on its way, every 30 s otherwise.
 */
function useGuestBill(orderId: string) {
  const [bill, setBill] = useState<GuestBill | null>(null);
  const [ended, setEnded] = useState(false);
  const pickup = counterState(bill);
  const slow = Boolean(bill && bill.status !== "open" && pickup !== "preparing" && pickup !== "ready");

  const load = useCallback(
    () =>
      fetch(`/api/guest/bill?order_id=${encodeURIComponent(orderId)}`)
        .then(async (r) => {
          if (r.status === 404) setBill(null);
          else if (r.ok) setBill((await r.json()) as GuestBill);
          // other errors: keep the last known bill
        })
        .catch(() => {}),
    [orderId],
  );

  useEffect(() => {
    void load();
    const timer = setInterval(load, slow ? 30_000 : 10_000);
    // Phones throttle background timers: catch up as soon as the guest looks again.
    const visible = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("focus", visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("focus", visible);
    };
  }, [slow, load]);

  return { bill, setBill, ended, setEnded, reload: load };
}

interface OrderDetails {
  id: string;
  table_label?: string | null;
  status: "pending_approval" | "placed" | "bumped" | "cancelled" | string;
  cancel_reason?: "declined" | "table_closed" | "voided" | null;
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
  const router = useRouter();
  // Set by the menu when the first order was over the venue's cap: the waiter will check it.
  const [big, setBig] = useState(false);
  useEffect(() => setBig(new URLSearchParams(window.location.search).has("big")), []);
  const { bill, setBill, ended, setEnded, reload } = useGuestBill(id);
  const [paying, setPaying] = useState(false);
  const state = billState(bill, ended);
  const counter = counterState(bill);
  const paid = bill ? paidText(bill, dict, lang) : null;
  const thanks = bill ? payForwardThanks(bill, dict) : null;
  // Settled or cancelled while the sheet is open: nothing left to pay, so close it.
  useEffect(() => {
    if (bill && bill.status !== "open") setPaying(false);
  }, [bill]);

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
    // Paid, ready, collected, cancelled or revived: the bill tells the guest, so reload it now.
    onMessage: () => void reload(),
  });

  const stage = order ? orderStage(order.status, order.cancel_reason) : null;
  // A counter order's progress is told by its pickup card instead.
  const stageText =
    !stage || counter || order?.status === "awaiting_payment"
      ? null
      : {
          confirming: dict.order.confirming,
          cooking: dict.ui.statusPlaced,
          ready: dict.ui.statusBumped,
          declined: dict.order.declined,
          closed: dict.order.thanks,
          cancelled: dict.ui.statusCancelled,
        }[stage];
  // Declined: back to the menu with the dishes in the cart, so nothing is lost.
  useEffect(() => {
    if (stage === "declined") router.replace(`/${lang}/menu?restore=${encodeURIComponent(id)}`);
  }, [stage, router, lang, id]);

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
        {/* Always mounted, so a screen reader hears each change of the order's status. */}
        <p aria-live="polite" className="sr-only">
          {stageText}
        </p>
        <header className="border-b border-line pb-4 space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-ink">{dict.ui.orderStatus}</h1>
              <p className="text-xs text-ink-muted font-mono mt-0.5 break-all">ID: {id}</p>
            </div>
            <CallWaiter lang={lang} />
          </div>
          {order && !counter && stage !== "confirming" && stage !== "declined" && stage !== "closed" && (
            <div>{getStatusBadge(order.status)}</div>
          )}
        </header>

        {error && !order && (
          <div className="p-4 bg-danger-bg border border-danger-fg/40 rounded-2xl text-xs text-danger-fg">
            {error.message}
          </div>
        )}

        {stage === "closed" || stage === "declined" ? (
          <div className="p-6 rounded-2xl bg-card border border-line text-center space-y-4">
            <p className="text-xl font-semibold text-ink">
              {stage === "closed" ? dict.order.thanks : dict.order.declined}
            </p>
            <Link
              href={`/${lang}/menu`}
              className="btn-primary inline-flex min-h-12 items-center justify-center px-6 text-base"
            >
              {dict.ui.backToMenu}
            </Link>
          </div>
        ) : order ? (
          <div className="space-y-6">
            {stage === "confirming" && (
              <div className="p-5 rounded-2xl bg-card border border-terracotta/60 space-y-2">
                <p className="text-lg font-semibold text-ink">{dict.order.confirming}</p>
                {big && <p className="text-base text-ink">{dict.order.bigFirst}</p>}
              </div>
            )}
            {/* Status Summary Card */}
            <div className="p-5 rounded-2xl bg-card border border-line space-y-4">
              {order.table_label && !counter && (
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

            {stage === "confirming" ? null : bill && counter ? (
              <div className="p-5 rounded-2xl bg-card border border-line text-center text-ink space-y-3">
                <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">{dict.counter.pickupNumber}</p>
                <p className="font-serif text-6xl font-bold tabular-nums text-ink">{bill.pickup_label}</p>
                {/* One polite region: announced once per state change. */}
                <p
                  aria-live="polite"
                  className={
                    counter === "ready"
                      ? "text-2xl font-bold text-terracotta"
                      : counter === "cancelled"
                        ? "text-sm font-semibold text-danger-fg"
                        : "text-sm font-semibold"
                  }
                >
                  {counter === "awaiting" &&
                    (bill.claim ? claimMessage(bill.claim, dict, lang, bill.currency, true) : dict.counter.payPrompt)}
                  {counter === "preparing" && dict.counter.preparing}
                  {counter === "ready" && dict.counter.ready.replace("{label}", bill.pickup_label ?? "")}
                  {counter === "collected" && dict.counter.collected}
                  {counter === "cancelled" && dict.counter.cancelled}
                </p>
                {paid && <p className="text-sm text-ink-muted">{paid}</p>}
                {thanks && <p className="text-sm">{thanks}</p>}
                {counter === "awaiting" && (
                  <Button className="w-full" onClick={() => setPaying(true)}>
                    {dict.pay.button}
                  </Button>
                )}
              </div>
            ) : (
            <div className="p-5 rounded-2xl bg-card border border-line text-sm text-ink space-y-3">
              {/* One polite region: the text changes only when the bill's state does. */}
              <p aria-live="polite" className={state === "cancelled" || state === "ended" ? "font-semibold text-danger-fg" : ""}>
                {state === "none" && dict.pay.noBill}
                {state === "paid" && dict.bill.paid.replace("{billNo}", String(bill?.bill_no ?? "").padStart(4, "0"))}
                {state === "paid" && paid && <span className="block mt-1 font-semibold">{paid}</span>}
                {state === "paid" && thanks && <span className="block mt-1">{thanks}</span>}
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
            )}
            {bill && (
              <PaySheet
                lang={lang}
                bill={bill}
                orderId={id}
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
                <span className="text-ink-muted">{paid ? dict.pay.subtotal : dict.ui.total}</span>
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

        {stage !== "closed" && stage !== "declined" && (
        <div className="pt-4 text-center">
          <Link
            href={`/${lang}/menu`}
            className="inline-block px-5 py-2.5 rounded-xl bg-paper-2 hover:bg-paper-2 text-xs font-medium text-ink transition-all"
          >
            ← {dict.ui.backToMenu}
          </Link>
        </div>
        )}
      </main>

      {/* Floating Chat Assistant */}
      <ChatPanel locale={lang} />
    </div>
  );
}
