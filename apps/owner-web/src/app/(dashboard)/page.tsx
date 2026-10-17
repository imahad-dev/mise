"use client";

import React, { useCallback, useState } from "react";
import { useSse } from "../../hooks/use-sse";

interface KitchenOrderItem {
  id: string;
  menu_item_id: string;
  kitchen_name: string;
  quantity: number;
  notes?: string | null;
  allergens: string[];
  allergen_status: string;
  conflict_with_order_allergens: boolean;
  matched_allergens: string[];
}

interface KitchenOrder {
  id: string;
  restaurant_id: string;
  table_id?: string | null;
  table_label?: string | null;
  status: string;
  allergens_to_avoid: string[];
  dietary_preferences: string[];
  allergen_conflict_acknowledged: boolean;
  placed_at: string;
  bumped_at?: string | null;
  items: KitchenOrderItem[];
}

interface OrdersResponse {
  orders: KitchenOrder[];
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

export default function DashboardOrdersPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchOrders = useCallback(async (): Promise<OrdersResponse> => {
    const res = await fetch(`/api/restaurants/${slug}/kitchen/orders`);
    if (!res.ok) {
      throw new Error(`Failed to load kitchen orders (${res.status})`);
    }
    return res.json();
  }, [slug]);

  const {
    data,
    isConnected,
    isReconnecting,
    error,
    refetch,
  } = useSse<OrdersResponse>({
    url: `/api/restaurants/${slug}/kitchen/stream`,
    fetchState: fetchOrders,
    pollingIntervalMs: 4000,
  });

  const handleBump = async (orderId: string) => {
    setActionError(null);
    try {
      const res = await fetch(`/api/restaurants/${slug}/kitchen/orders/${orderId}/bump`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error(`Failed to bump order (${res.status})`);
      }
      await refetch();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRecall = async (orderId: string) => {
    setActionError(null);
    try {
      const res = await fetch(`/api/restaurants/${slug}/kitchen/orders/${orderId}/recall`, {
        method: "POST",
      });
      if (res.status === 409) {
        throw new Error("Recall window expired (must be within 60 seconds of bump).");
      }
      if (!res.ok) {
        throw new Error(`Failed to recall order (${res.status})`);
      }
      await refetch();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const orders = data?.orders || [];
  const placedOrders = orders.filter((o) => o.status === "placed");
  const recentlyBumped = orders.filter((o) => o.status === "bumped");

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-zinc-100 tracking-tight">Live Orders</h1>
          <p className="text-xs text-zinc-400 mt-1">
            Real-time kitchen stream for restaurant: <span className="text-emerald-400 font-mono">{slug}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isReconnecting ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-800 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              Reconnecting (Polling active)
            </span>
          ) : isConnected ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-300 border border-emerald-800">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              Live SSE Connected
            </span>
          ) : (
            <span className="text-xs text-zinc-500">Connecting...</span>
          )}
        </div>
      </div>

      {actionError && (
        <div className="p-3 bg-rose-950/70 border border-rose-800 rounded-xl text-xs text-rose-300">
          {actionError}
        </div>
      )}

      {error && !data && (
        <div className="p-4 bg-rose-950/60 border border-rose-800 rounded-2xl text-xs text-rose-300">
          {error.message}
        </div>
      )}

      {/* Stats summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-2xl bg-zinc-900 border border-zinc-800">
          <p className="text-xs text-zinc-400 uppercase font-bold tracking-wider">Active Placed</p>
          <p className="text-2xl font-bold text-zinc-100 mt-1">{placedOrders.length}</p>
        </div>
        <div className="p-4 rounded-2xl bg-zinc-900 border border-zinc-800">
          <p className="text-xs text-zinc-400 uppercase font-bold tracking-wider">Recently Bumped (60s)</p>
          <p className="text-2xl font-bold text-zinc-100 mt-1">{recentlyBumped.length}</p>
        </div>
        <div className="p-4 rounded-2xl bg-zinc-900 border border-zinc-800 col-span-2 sm:col-span-1">
          <p className="text-xs text-zinc-400 uppercase font-bold tracking-wider">Total Stream</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">{orders.length}</p>
        </div>
      </div>

      {/* Orders grid */}
      {orders.length === 0 ? (
        <div className="p-12 text-center rounded-3xl bg-zinc-900/50 border border-zinc-800/80 space-y-2">
          <p className="text-sm font-medium text-zinc-400">No active orders right now.</p>
          <p className="text-xs text-zinc-600">New orders placed by guests will appear instantly.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {orders.map((order) => {
            const isBumped = order.status === "bumped";
            return (
              <div
                key={order.id}
                className={`rounded-2xl border p-5 flex flex-col justify-between space-y-4 transition-all ${
                  isBumped
                    ? "bg-zinc-950/60 border-zinc-800 opacity-60"
                    : "bg-zinc-900 border-zinc-700/80 shadow-lg"
                }`}
              >
                {/* Header */}
                <div className="space-y-2">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-sm font-bold text-emerald-400">
                        {order.table_label ? `Table ${order.table_label}` : "No Table"}
                      </span>
                      <p className="text-[11px] font-mono text-zinc-500 mt-0.5">
                        {order.id.slice(0, 8)} • {new Date(order.placed_at).toLocaleTimeString()}
                      </p>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        isBumped
                          ? "bg-zinc-800 text-zinc-400"
                          : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                      }`}
                    >
                      {order.status}
                    </span>
                  </div>

                  {/* Allergen alert banner if order has guest avoidance */}
                  {order.allergens_to_avoid && order.allergens_to_avoid.length > 0 && (
                    <div className="p-2 rounded-lg bg-rose-950/50 border border-rose-800/50 text-[11px] text-rose-300">
                      ⚠️ Avoid: {order.allergens_to_avoid.join(", ")}
                    </div>
                  )}

                  {/* Items List */}
                  <div className="divide-y divide-zinc-800/80 pt-2">
                    {order.items.map((item) => (
                      <div key={item.id} className="py-2 space-y-1">
                        <div className="flex items-start justify-between text-xs">
                          <span className="font-semibold text-zinc-200">
                            {item.quantity}x {item.kitchen_name}
                          </span>
                          {item.conflict_with_order_allergens && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-rose-900 text-rose-200 font-bold">
                              CONFLICT
                            </span>
                          )}
                        </div>
                        {item.notes && (
                          <p className="text-[11px] text-amber-300 italic">Note: {item.notes}</p>
                        )}
                        {item.matched_allergens && item.matched_allergens.length > 0 && (
                          <p className="text-[10px] text-rose-400 font-medium">
                            Matches: {item.matched_allergens.join(", ")}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Actions */}
                <div className="pt-3 border-t border-zinc-800 flex items-center justify-between">
                  {!isBumped ? (
                    <button
                      onClick={() => handleBump(order.id)}
                      className="w-full py-2.5 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white font-bold text-xs shadow-md transition-all"
                    >
                      ✓ Bump Order
                    </button>
                  ) : (
                    <button
                      onClick={() => handleRecall(order.id)}
                      className="w-full py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-amber-400 border border-zinc-700 font-semibold text-xs transition-all"
                    >
                      ↺ Recall Order (60s)
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
