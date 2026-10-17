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
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-600/60">
            {dict.ui.statusPlaced}
          </span>
        );
      case "bumped":
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-blue-950 text-blue-300 border border-blue-600/60">
            {dict.ui.statusBumped}
          </span>
        );
      case "cancelled":
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-600/60">
            {dict.ui.statusCancelled}
          </span>
        );
      default:
        return (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-zinc-800 text-zinc-300">
            {status || "..."}
          </span>
        );
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col justify-between">
      {/* Reconnecting banner (SSE down or reconnecting) */}
      {isReconnecting && (
        <div
          data-testid="reconnecting-banner"
          className="bg-amber-500 text-zinc-950 px-4 py-2 text-xs font-bold text-center flex items-center justify-center gap-2 sticky top-0 z-50 animate-pulse"
        >
          <span className="w-2 h-2 rounded-full bg-zinc-950" />
          {dict.ui.reconnecting}
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <header className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div>
            <h1 className="text-xl font-bold text-zinc-100">{dict.ui.orderStatus}</h1>
            <p className="text-xs text-zinc-500 font-mono mt-0.5">ID: {id}</p>
          </div>
          {order && getStatusBadge(order.status)}
        </header>

        {error && !order && (
          <div className="p-4 bg-rose-950/60 border border-rose-800 rounded-2xl text-xs text-rose-300">
            {error.message}
          </div>
        )}

        {order ? (
          <div className="space-y-6">
            {/* Status Summary Card */}
            <div className="p-5 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              {order.table_label && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-400">{dict.ui.table}</span>
                  <span className="font-medium text-emerald-400">{order.table_label}</span>
                </div>
              )}
              <div className="flex items-center justify-between text-sm">
                <span className="text-zinc-400">{dict.ui.placedAt}</span>
                <span className="text-xs text-zinc-300 font-mono">
                  {new Date(order.placed_at).toLocaleTimeString()}
                </span>
              </div>
            </div>

            {/* Items List */}
            <div className="rounded-2xl bg-zinc-900 border border-zinc-800 p-5 space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-400 border-b border-zinc-800 pb-2">
                {dict.ui.items}
              </h2>
              <div className="divide-y divide-zinc-800/80">
                {order.items.map((item) => (
                  <div key={item.id} className="py-2.5 flex items-start justify-between text-sm">
                    <div>
                      <div className="font-medium text-zinc-200">
                        {item.quantity}x {item.item_name}
                      </div>
                      {item.notes && (
                        <p className="text-xs text-zinc-500 italic mt-0.5">Note: {item.notes}</p>
                      )}
                    </div>
                    <span className="font-semibold text-zinc-300">
                      €{(Number(item.unit_price) * item.quantity).toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-zinc-800 flex items-center justify-between font-bold text-sm">
                <span className="text-zinc-400">{dict.ui.total}</span>
                <span className="text-emerald-400 text-base">
                  €{Number(order.total).toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-12 flex flex-col items-center justify-center gap-3">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-zinc-500">Connecting to order stream...</p>
          </div>
        )}

        <div className="pt-4 text-center">
          <Link
            href={`/${lang}/menu`}
            className="inline-block px-5 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-200 transition-all"
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
