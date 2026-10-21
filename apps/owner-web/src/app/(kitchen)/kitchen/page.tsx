"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSse } from "../../../hooks/use-sse";

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

export default function KitchenDisplayPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [pin, setPin] = useState("");
  const [authChecking, setAuthChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [soundEnabled, setSoundEnabled] = useState(false);
  const [serverTimeOffset, setServerTimeOffset] = useState(0);
  const [currentTime, setCurrentTime] = useState(Date.now());
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);
  const knownOrderIdsRef = useRef<Set<string>>(new Set());
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Initialize audio element
  useEffect(() => {
    audioRef.current = new Audio("/alert.wav");
  }, []);

  // Update clock every 5 seconds for age calculations
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);

  // Check initial authentication
  useEffect(() => {
    async function checkAuth() {
      try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
        }
      } catch {
        setIsAuthenticated(false);
      } finally {
        setAuthChecking(false);
      }
    }
    checkAuth();
  }, []);

  // Screen Wake Lock API: request on load and on visibilitychange
  useEffect(() => {
    async function requestWakeLock() {
      if (typeof navigator !== "undefined" && "wakeLock" in navigator) {
        try {
          wakeLockRef.current = await (navigator as Navigator & { wakeLock: { request: (type: string) => Promise<WakeLockSentinel> } }).wakeLock.request("screen");
        } catch {
          // Wake lock may fail if battery/permission restricts it
        }
      }
    }

    if (isAuthenticated) {
      void requestWakeLock();
      const onVisibilityChange = () => {
        if (document.visibilityState === "visible") {
          void requestWakeLock();
        }
      };
      document.addEventListener("visibilitychange", onVisibilityChange);
      return () => {
        document.removeEventListener("visibilitychange", onVisibilityChange);
        wakeLockRef.current?.release?.();
      };
    }
  }, [isAuthenticated]);

  // Fetch kitchen orders with server time offset tracking
  const fetchOrders = useCallback(async (): Promise<OrdersResponse> => {
    const res = await fetch(`/api/restaurants/${slug}/kitchen/orders`);
    if (res.status === 401 || res.status === 403) {
      setIsAuthenticated(false);
      throw new Error("Staff PIN required");
    }
    if (!res.ok) {
      throw new Error(`Failed to load kitchen stream (${res.status})`);
    }

    // Measure server time offset from Date response header to avoid clock skew
    const serverDateHeader = res.headers.get("date");
    if (serverDateHeader) {
      const serverDate = new Date(serverDateHeader).getTime();
      setServerTimeOffset(serverDate - Date.now());
    }

    const data: OrdersResponse = await res.json();
    return data;
  }, [slug]);

  // SSE hook with polling fallback
  const {
    data,
    isReconnecting,
    refetch,
  } = useSse<OrdersResponse>({
    url: isAuthenticated ? `/api/restaurants/${slug}/kitchen/stream` : null,
    fetchState: fetchOrders,
    pollingIntervalMs: 4000,
    enabled: isAuthenticated,
  });

  // Check for new orders to trigger audible alert
  useEffect(() => {
    if (!data?.orders) return;
    const currentOrders = data.orders.filter((o) => o.status === "placed");
    let hasNewOrder = false;

    currentOrders.forEach((order) => {
      if (!knownOrderIdsRef.current.has(order.id)) {
        hasNewOrder = true;
        knownOrderIdsRef.current.add(order.id);
      }
    });

    if (hasNewOrder && soundEnabled && audioRef.current) {
      audioRef.current.play().catch(() => {
        // Autoplay may be blocked if user has not interacted
      });
    }
  }, [data, soundEnabled]);

  // Staff PIN submission handler
  const handlePinSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "staff", secret: pin }),
      });
      if (!res.ok) {
        throw new Error("Invalid Staff PIN");
      }
      setIsAuthenticated(true);
      setPin("");
    } catch (err: unknown) {
      setLoginError(err instanceof Error ? err.message : String(err));
    }
  };

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

  if (authChecking) {
    return (
      <div className="min-h-screen bg-espresso text-cream flex items-center justify-center">
        <p className="text-xl font-bold">Initializing Kitchen System...</p>
      </div>
    );
  }

  // Staff PIN Login Screen if unauthenticated
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-espresso text-cream flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-kds-card border-2 border-cream/10 rounded-3xl p-8 space-y-6">
          <div className="text-center space-y-2">
            <h1 className="text-3xl font-black tracking-tight text-cream">KITCHEN DISPLAY</h1>
            <p className="text-sm text-kds-muted">Enter Staff PIN to access kitchen orders</p>
          </div>

          {loginError && (
            <div className="p-3 bg-kds-late/20 border border-kds-late text-kds-late text-sm font-bold text-center rounded-xl">
              {loginError}
            </div>
          )}

          <form onSubmit={handlePinSubmit} className="space-y-6">
            <input
              type="password"
              inputMode="numeric"
              maxLength={8}
              autoFocus
              placeholder="Enter PIN..."
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              className="w-full text-center text-4xl tracking-widest py-4 bg-kds-card border-2 border-cream/10 rounded-2xl text-cream font-mono focus:outline-none focus:border-kds-fresh"
            />
            <button
              type="submit"
              className="w-full py-4 rounded-2xl bg-kds-fresh hover:opacity-90 text-espresso font-black text-xl shadow-lg active:scale-95 transition-all"
            >
              ACCESS KITCHEN
            </button>
          </form>
        </div>
      </div>
    );
  }

  const allOrders = data?.orders || [];
  const placedOrders = allOrders.filter((o) => o.status === "placed");
  // Find the most recently bumped order (within 60s)
  const mostRecentBumped = allOrders
    .filter((o) => o.status === "bumped" && o.bumped_at)
    .sort((a, b) => new Date(b.bumped_at!).getTime() - new Date(a.bumped_at!).getTime())[0];

  const nowServer = currentTime + serverTimeOffset;

  let recallRemainingSeconds = 0;
  if (mostRecentBumped && mostRecentBumped.bumped_at) {
    const elapsedBumpSeconds = Math.floor(
      (nowServer - new Date(mostRecentBumped.bumped_at).getTime()) / 1000
    );
    recallRemainingSeconds = Math.max(0, 60 - elapsedBumpSeconds);
  }

  return (
    <div className="min-h-screen bg-espresso text-cream flex flex-col p-4 sm:p-6 space-y-6">
      {/* Action Error Banner */}
      {actionError && (
        <div className="p-4 bg-kds-late/20 border-2 border-kds-late text-kds-late text-sm font-bold rounded-2xl flex items-center justify-between">
          <span>⚠️ {actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="text-xs px-2 py-1 rounded bg-kds-late/20 hover:bg-kds-late/40"
          >
            ✕
          </button>
        </div>
      )}

      {/* Connection Lost Banner */}
      {isReconnecting && (
        <div
          data-testid="kitchen-connection-lost-banner"
          className="bg-kds-late text-espresso py-3 px-6 rounded-2xl text-center text-lg font-black tracking-wide uppercase flex items-center justify-center gap-3 animate-pulse shadow-2xl"
        >
          <span className="w-3 h-3 rounded-full bg-espresso animate-ping" />
          CONNECTION INTERRUPTED — POLLING FALLBACK ACTIVE
        </div>
      )}

      {/* Top Controls Bar */}
      <header className="flex flex-wrap items-center justify-between gap-4 bg-kds-card p-4 rounded-2xl border border-cream/10">
        <div className="flex items-center gap-4">
          <span className="font-serif text-2xl font-black tracking-wider text-kds-fresh">KITCHEN</span>
          <span className="text-sm text-kds-muted font-mono">
            {new Date(nowServer).toLocaleTimeString()}
          </span>
          <span className="px-3 py-1 rounded-full bg-kds-card text-xs font-bold text-kds-muted">
            {placedOrders.length} ORDERS ACTIVE
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Sound Alert Toggle */}
          <button
            onClick={() => {
              const next = !soundEnabled;
              setSoundEnabled(next);
              if (next && audioRef.current) {
                audioRef.current.play().catch(() => {});
              }
            }}
            className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 border transition-all ${
              soundEnabled
                ? "bg-kds-fresh/20 text-kds-fresh border-kds-fresh"
                : "bg-kds-card text-kds-muted border-cream/10 hover:border-cream/10"
            }`}
          >
            <span>{soundEnabled ? "🔊 Sound Enabled" : "🔇 Enable Sound"}</span>
          </button>

          {/* Recall Button for most recently bumped order (visible for 60s) */}
          {mostRecentBumped && recallRemainingSeconds > 0 && (
            <button
              onClick={() => handleRecall(mostRecentBumped.id)}
              className="px-5 py-2.5 rounded-xl bg-kds-warn hover:opacity-90 text-espresso font-black text-sm uppercase tracking-wide shadow-lg animate-pulse"
            >
              ↺ RECALL TABLE {mostRecentBumped.table_label || ""} ({recallRemainingSeconds}s)
            </button>
          )}
        </div>
      </header>

      {/* Main Order Tickets Display */}
      {placedOrders.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center rounded-3xl bg-kds-card border border-cream/10">
          <p className="text-3xl font-black text-kds-muted">ALL TICKETS CLEARED</p>
          <p className="text-sm text-kds-muted mt-2">Standing by for incoming orders.</p>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 items-start">
          {placedOrders.map((order) => {
            const placedTime = new Date(order.placed_at).getTime();
            const elapsedMinutes = Math.max(0, Math.floor((nowServer - placedTime) / 60000));

            // Age colors:
            // - fresh (<10 min): thick green border
            // - warning (>=10 min): thick amber border
            // - critical (>=20 min): thick red border
            let ageBorder = "border-l-8 border-l-kds-fresh";
            let ageBadge = "bg-kds-fresh text-espresso";
            if (elapsedMinutes >= 20) {
              ageBorder = "border-l-8 border-l-kds-late ring-1 ring-kds-late/40";
              ageBadge = "bg-kds-late text-espresso font-black animate-pulse";
            } else if (elapsedMinutes >= 10) {
              ageBorder = "border-l-8 border-l-kds-warn";
              ageBadge = "bg-kds-warn text-espresso font-black";
            }

            return (
              <div
                key={order.id}
                className={`rounded-2xl bg-kds-card border border-cream/10 p-5 flex flex-col justify-between space-y-4 shadow-2xl transition-all ${ageBorder}`}
              >
                {/* Ticket Header */}
                <div className="space-y-2 border-b border-cream/10 pb-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h2 className="text-2xl font-black tracking-tight text-cream">
                        {order.table_label ? `TABLE ${order.table_label}` : "TAKEOUT"}
                      </h2>
                      <p className="text-xs font-mono text-kds-muted">
                        {new Date(order.placed_at).toLocaleTimeString()}
                      </p>
                    </div>

                    {/* Age Minutes as Text */}
                    <span className={`px-2.5 py-1 rounded-lg text-xs font-bold uppercase ${ageBadge}`}>
                      {elapsedMinutes} min ago
                    </span>
                  </div>

                  {/* Guest allergens to avoid summary banner - SOLID RED */}
                  {order.allergens_to_avoid && order.allergens_to_avoid.length > 0 && (
                    <div className="p-2.5 rounded-xl bg-kds-late text-espresso text-xs font-black uppercase tracking-wide shadow-md">
                      🚨 GUEST ALLERGIES: {order.allergens_to_avoid.join(", ")}
                    </div>
                  )}
                </div>

                {/* Items List */}
                <div className="space-y-3 flex-1 py-1">
                  {order.items.map((item) => (
                    <div
                      key={item.id}
                      className={`p-3 rounded-xl border ${
                        item.conflict_with_order_allergens
                          ? "bg-kds-late/20 border-kds-late text-cream ring-1 ring-kds-late"
                          : "bg-kds-card border-cream/10 text-cream"
                      }`}
                    >
                      <div className="flex items-baseline justify-between text-base font-black">
                        <span className="text-xl text-kds-accent font-mono">{item.quantity}x</span>
                        <span className="flex-1 text-right text-lg text-cream">{item.kitchen_name}</span>
                      </div>

                      {/* Prominent Solid Red Allergy Banner on Affected Items */}
                      {item.conflict_with_order_allergens && (
                        <div className="mt-2 py-1.5 px-2.5 rounded-lg bg-kds-late text-espresso text-xs font-black uppercase text-center tracking-wider shadow-sm">
                          ⚠️ ALLERGY WARNING: {item.matched_allergens.join(", ")}
                        </div>
                      )}

                      {item.notes && (
                        <p className="mt-1.5 text-xs text-kds-warn font-bold italic bg-espresso p-2 rounded-lg border border-kds-warn">
                          NOTE: {item.notes}
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                {/* One Large Bump Button */}
                <div className="pt-2">
                  <button
                    onClick={() => handleBump(order.id)}
                    className="w-full min-h-[48px] rounded-xl bg-kds-accent py-3.5 text-lg font-black uppercase tracking-wider text-espresso shadow-xl transition-all hover:opacity-90 active:scale-95"
                  >
                    BUMP
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
