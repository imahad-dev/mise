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
      <div className="flex items-center justify-between border-b border-[#38BDF8]/15 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">
            Menu Items & <span className="gradient-text">Verification</span>
          </h1>
          <p className="text-xs text-[#8FA3B3] mt-1">
            Manage dish availability, unit costs, and verify allergen & dietary declarations.
          </p>
        </div>
        <span className="text-xs font-mono text-[#8FA3B3]">{items.length} items total</span>
      </div>

      <div className="mise-card p-0 divide-y divide-[#38BDF8]/10 overflow-hidden">
        {items.map((item) => {
          const primaryName = item.translations[0]?.name || "Unnamed Item";
          const isVerified = item.allergen_verified && item.dietary_verified;
          const isBusy = actionInProgress !== null;

          return (
            <div
              key={item.id}
              className={`p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors ${
                !item.available ? "bg-[#070B10]/60 opacity-70" : "hover:bg-white/[0.02]"
              }`}
            >
              {/* Item Info */}
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#22D3EE]">
                    {item.category}
                  </span>
                  <span className="text-[#8FA3B3]/40">•</span>
                  <h2 className="text-sm font-bold text-[#F3F8FC]">{primaryName}</h2>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-xs text-[#8FA3B3] font-mono">
                  <span>Price: €{Number(item.price).toFixed(2)}</span>
                  <span>Unit Cost: <strong className="text-[#F3F8FC]">€{Number(item.unit_cost).toFixed(2)}</strong></span>
                  {item.allergens.length > 0 && (
                    <span className="chip chip-contains text-[10px]">
                      Contains: {item.allergens.join(", ")}
                    </span>
                  )}
                </div>

                {/* Verification Flags */}
                <div className="flex items-center gap-2 pt-1">
                  <span
                    className={`chip text-[10px] ${
                      item.allergen_verified ? "chip-safe" : "chip-unverified"
                    }`}
                  >
                    {item.allergen_verified ? "✓ Allergens Verified" : "⚠️ Allergens Unverified"}
                  </span>
                  <span
                    className={`chip text-[10px] ${
                      item.dietary_verified ? "chip-safe" : "chip-unverified"
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
                  className={`min-h-[44px] px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                    item.available
                      ? "bg-[#0D141B] text-[#F3F8FC] border-[#38BDF8]/20 hover:border-[#38BDF8]/50"
                      : "bg-[#EF4444]/15 text-[#EF4444] border-[#EF4444]/40 hover:bg-[#EF4444]/25"
                  }`}
                >
                  {item.available ? "Active (Available)" : "Sold Out (Disabled)"}
                </button>

                {/* Verify Button */}
                {!isVerified ? (
                  <button
                    onClick={() => handleVerify(item)}
                    disabled={isBusy}
                    className="btn-primary !min-h-[44px] !py-1.5 !px-3.5 text-xs"
                  >
                    Verify Item
                  </button>
                ) : (
                  <button
                    onClick={() => handleVerify(item)}
                    disabled={isBusy}
                    title="Re-verify item"
                    className="btn-ghost !min-h-[44px] !py-1.5 !px-3 text-xs"
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
