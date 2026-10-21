"use client";

import React, { use, useCallback } from "react";
import Link from "next/link";
import { ChatPanel } from "../../../../components/chat-panel";
import { useSse } from "../../../../hooks/use-sse";
import { getDictionary } from "../../../../i18n";

interface OrderItem {
  id: string;
  item_name: string;
  quantity: number;
  unit_price: string | number;
  notes?: string | null;
  allergen_status: string;
}

interface OrderDetails {
  id: string;
  table_label?: string | null;
  status: "placed" | "bumped" | "cancelled" | string;
  total: string | number;
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
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-safe-bg text-terracotta border border-terracotta">
            {dict.ui.statusPlaced}
          </span>
        );
      case "bumped":
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-paper-2 text-terracotta border border-terracotta/60">
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
          {order && getStatusBadge(order.status)}
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
                      </div>
                      {item.notes && (
                        <p className="text-xs text-ink-muted italic mt-0.5">Note: {item.notes}</p>
                      )}
                    </div>
                    <span className="font-semibold text-ink-muted">
                      €{(Number(item.unit_price) * item.quantity).toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-line flex items-center justify-between font-bold text-sm">
                <span className="text-ink-muted">{dict.ui.total}</span>
                <span className="text-terracotta text-base">
                  €{Number(order.total).toFixed(2)}
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
