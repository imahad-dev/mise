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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-line pb-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">
            Live <span className="text-terracotta">Orders Stream</span>
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Real-time kitchen stream for restaurant: <span className="text-terracotta font-mono">{slug}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isReconnecting ? (
            <span className="chip chip-unverified animate-pulse">
              <span className="w-2 h-2 rounded-full bg-warn-fg" />
              Reconnecting (Polling active)
            </span>
          ) : isConnected ? (
            <span className="chip chip-safe">
              <span className="w-2 h-2 rounded-full bg-olive animate-ping" />
              Live SSE Connected
            </span>
          ) : (
            <span className="text-xs text-ink-muted">Connecting...</span>
          )}
        </div>
      </div>

      {actionError && (
        <div className="p-3 bg-danger-bg border border-danger-fg rounded-xl text-xs text-danger-fg">
          {actionError}
        </div>
      )}

      {error && !data && (
        <div className="p-4 bg-danger-bg border border-danger-fg rounded-2xl text-xs text-danger-fg">
          {error.message}
        </div>
      )}

      {/* Stats summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="stat-tile">
          <p className="text-xs text-ink-muted uppercase font-bold tracking-wider">Active Placed</p>
          <p className="text-3xl font-extrabold text-ink mt-1">{placedOrders.length}</p>
        </div>
        <div className="stat-tile">
          <p className="text-xs text-ink-muted uppercase font-bold tracking-wider">Recently Bumped (60s)</p>
          <p className="text-3xl font-extrabold text-ink mt-1">{recentlyBumped.length}</p>
        </div>
        <div className="stat-tile col-span-2 sm:col-span-1">
          <p className="text-xs text-ink-muted uppercase font-bold tracking-wider">Total Stream</p>
          <p className="text-3xl font-extrabold text-terracotta mt-1">{orders.length}</p>
        </div>
      </div>

      {/* Orders grid */}
      {orders.length === 0 ? (
        <div className="p-12 text-center rounded-3xl mise-card space-y-2">
          <p className="text-sm font-semibold text-ink">No active orders right now.</p>
          <p className="text-xs text-ink-muted">New orders placed by guests will appear instantly.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {orders.map((order) => {
            const isBumped = order.status === "bumped";
            return (
              <div
                key={order.id}
                className={`mise-card flex flex-col justify-between space-y-4 transition-all ${
                  isBumped ? "opacity-60 bg-paper" : ""
                }`}
              >
                {/* Header */}
                <div className="space-y-2">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-base font-extrabold text-terracotta">
                        {order.table_label ? `Table ${order.table_label}` : "Takeout"}
                      </span>
                      <p className="text-[11px] font-mono text-ink-muted mt-0.5">
                        {order.id.slice(0, 8)} • {new Date(order.placed_at).toLocaleTimeString()}
                      </p>
                    </div>
                    <span
                      className={`chip ${isBumped ? "chip-unverified" : "chip-safe"}`}
                    >
                      {order.status}
                    </span>
                  </div>

                  {/* Allergen alert banner if order has guest avoidance */}
                  {order.allergens_to_avoid && order.allergens_to_avoid.length > 0 && (
                    <div className="p-2 rounded-lg bg-danger-bg border border-danger-fg text-xs text-danger-fg font-bold">
                      ⚠️ Avoid: {order.allergens_to_avoid.join(", ")}
                    </div>
                  )}

                  {/* Items List */}
                  <div className="divide-y divide-line pt-2">
                    {order.items.map((item) => (
                      <div key={item.id} className="py-2 space-y-1">
                        <div className="flex items-start justify-between text-xs">
                          <span className="font-semibold text-ink">
                            {item.quantity}x {item.kitchen_name}
                          </span>
                          {item.conflict_with_order_allergens && (
                            <span className="chip chip-contains text-[10px]">
                              CONFLICT
                            </span>
                          )}
                        </div>
                        {item.notes && (
                          <p className="text-[11px] text-warn-fg italic">Note: {item.notes}</p>
                        )}
                        {item.matched_allergens && item.matched_allergens.length > 0 && (
                          <p className="text-[10px] text-danger-fg font-medium">
                            Matches: {item.matched_allergens.join(", ")}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Actions */}
                <div className="pt-3 border-t border-line flex items-center justify-between">
                  {!isBumped ? (
                    <button
                      onClick={() => handleBump(order.id)}
                      className="btn-primary w-full"
                    >
                      ✓ Bump Order
                    </button>
                  ) : (
                    <button
                      onClick={() => handleRecall(order.id)}
                      className="btn-ghost w-full"
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
