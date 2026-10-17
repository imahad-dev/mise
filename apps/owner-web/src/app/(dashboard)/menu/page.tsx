"use client";

import React, { useCallback, useEffect, useState } from "react";

interface MenuTranslation {
  language: string;
  name: string;
  description?: string | null;
}

interface OwnerMenuItem {
  id: string;
  restaurant_id: string;
  category: string;
  price: string | number;
  unit_cost: string | number;
  ingredients: string[];
  allergens: string[];
  allergen_verified: boolean;
  dietary_verified: boolean;
  is_vegetarian: boolean;
  is_vegan: boolean;
  is_gluten_free: boolean;
  available: boolean;
  translations: MenuTranslation[];
}

const DEFAULT_SLUG = process.env.NEXT_PUBLIC_RESTAURANT_SLUG || "trattoria-da-mario";

export default function MenuManagementPage() {
  const [slug] = useState(DEFAULT_SLUG);
  const [items, setItems] = useState<OwnerMenuItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const loadMenuItems = useCallback(async () => {
    try {
      const res = await fetch(`/api/restaurants/${slug}/menu-items`);
      if (!res.ok) {
        throw new Error(`Failed to load menu items (${res.status})`);
      }
      const data: OwnerMenuItem[] = await res.json();
      setItems(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void loadMenuItems();
  }, [loadMenuItems]);

  const handleToggleAvailable = async (item: OwnerMenuItem) => {
    setActionInProgress(item.id);
    try {
      const res = await fetch(`/api/restaurants/${slug}/menu-items/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ available: !item.available }),
      });
      if (!res.ok) {
        throw new Error(`Failed to update item availability (${res.status})`);
      }
      const updated: OwnerMenuItem = await res.json();
      setItems((prev) => prev.map((i) => (i.id === item.id ? updated : i)));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setActionInProgress(null);
    }
  };

  const handleVerify = async (item: OwnerMenuItem) => {
    setActionInProgress(item.id);
    try {
      const res = await fetch(`/api/restaurants/${slug}/menu-items/${item.id}/verify`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error(`Failed to verify item (${res.status})`);
      }
      const updated: OwnerMenuItem = await res.json();
      setItems((prev) => prev.map((i) => (i.id === item.id ? updated : i)));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setActionInProgress(null);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center">
        <div className="inline-block w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-zinc-500 mt-2">Loading menu items...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-rose-950/60 border border-rose-800 rounded-2xl text-xs text-rose-300">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-zinc-100 tracking-tight">Menu Items & Verification</h1>
          <p className="text-xs text-zinc-400 mt-1">
            Manage dish availability, unit costs, and verify allergen & dietary declarations.
          </p>
        </div>
        <span className="text-xs font-mono text-zinc-500">{items.length} items total</span>
      </div>

      <div className="divide-y divide-zinc-800/80 rounded-3xl bg-zinc-900 border border-zinc-800 overflow-hidden shadow-xl">
        {items.map((item) => {
          const primaryName = item.translations[0]?.name || "Unnamed Item";
          const isVerified = item.allergen_verified && item.dietary_verified;
          const isBusy = actionInProgress !== null;

          return (
            <div
              key={item.id}
              className={`p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors ${
                !item.available ? "bg-zinc-950/40 opacity-70" : "hover:bg-zinc-800/30"
              }`}
            >
              {/* Item Info */}
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                    {item.category}
                  </span>
                  <span className="text-zinc-600">•</span>
                  <h2 className="text-sm font-bold text-zinc-100">{primaryName}</h2>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-400 font-mono">
                  <span>Price: €{Number(item.price).toFixed(2)}</span>
                  <span>Unit Cost: <strong className="text-zinc-200">€{Number(item.unit_cost).toFixed(2)}</strong></span>
                  {item.allergens.length > 0 && (
                    <span className="text-rose-400">Allergens: {item.allergens.join(", ")}</span>
                  )}
                </div>

                {/* Verification Flags */}
                <div className="flex items-center gap-2 pt-1">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${
                      item.allergen_verified
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : "bg-amber-950 text-amber-300 border border-amber-800"
                    }`}
                  >
                    {item.allergen_verified ? "✓ Allergens Verified" : "⚠️ Allergens Unverified"}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${
                      item.dietary_verified
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : "bg-amber-950 text-amber-300 border border-amber-800"
                    }`}
                  >
                    {item.dietary_verified ? "✓ Dietary Verified" : "⚠️ Dietary Unverified"}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 self-end sm:self-center">
                {/* Available Toggle */}
                <button
                  onClick={() => handleToggleAvailable(item)}
                  disabled={isBusy}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    item.available
                      ? "bg-zinc-800 text-zinc-200 border-zinc-700 hover:bg-zinc-700"
                      : "bg-rose-950/60 text-rose-300 border-rose-800 hover:bg-rose-900/60"
                  }`}
                >
                  {item.available ? "Active (Available)" : "Sold Out (Disabled)"}
                </button>

                {/* Verify Button */}
                {!isVerified ? (
                  <button
                    onClick={() => handleVerify(item)}
                    disabled={isBusy}
                    className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-semibold text-xs shadow-md transition-all"
                  >
                    Verify Item
                  </button>
                ) : (
                  <button
                    onClick={() => handleVerify(item)}
                    disabled={isBusy}
                    title="Re-verify item"
                    className="px-2.5 py-1.5 rounded-xl bg-zinc-800 text-zinc-400 hover:text-zinc-200 text-xs font-medium"
                  >
                    Re-verify
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
