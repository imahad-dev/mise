"use client";

import React, { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AllergenChip } from "../../../components/allergen-chip";
import { ChatPanel } from "../../../components/chat-panel";
import { getDictionary } from "../../../i18n";
import {
  addToCart,
  calculateCartTotal,
  clearCart,
  getCart,
  hasAllergenRisk,
  saveCart,
  setAllergenAcknowledged,
  updateCartItemQuantity,
  type CartState,
} from "../../../lib/cart";

interface MenuItem {
  id: string;
  category: string;
  price: string | number;
  name: string;
  description?: string | null;
  ingredients: string[];
  allergens: string[];
  allergen_status: "contains" | "unverified" | "no_declared_match";
  matched_allergens?: string[];
  allergen_verified: boolean;
  dietary_verified: boolean;
  is_vegetarian: boolean;
  is_vegan: boolean;
  is_gluten_free: boolean;
  available: boolean;
}

interface MenuResponse {
  restaurant: {
    id: string;
    name: string;
    currency: string;
  };
  table_id?: string | null;
  table_label?: string | null;
  items: MenuItem[];
}

export default function GuestMenuPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = use(params);
  const router = useRouter();
  const dict = getDictionary(lang);

  const [menu, setMenu] = useState<MenuResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cart, setCart] = useState<CartState>(getCart());
  const [cartOpen, setCartOpen] = useState(false);
  const [submittingOrder, setSubmittingOrder] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);

  // Load menu from /api/guest/menu
  useEffect(() => {
    async function loadMenu() {
      try {
        const res = await fetch("/api/guest/menu");
        if (res.status === 401) {
          router.push("/");
          return;
        }
        if (!res.ok) {
          throw new Error(`Failed to load menu (${res.status})`);
        }
        const data = await res.json();
        setMenu(data);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    loadMenu();
  }, [router]);

  const handleAddToCart = (item: MenuItem) => {
    const updated = addToCart({
      menuItemId: item.id,
      name: item.name,
      price: Number(item.price),
      allergenStatus: item.allergen_status,
      matchedAllergens: item.matched_allergens || [],
    });
    setCart({ ...updated });
  };

  const handleUpdateQuantity = (menuItemId: string, qty: number, notes?: string) => {
    const updated = updateCartItemQuantity(menuItemId, qty, notes);
    setCart({ ...updated });
  };

  const handleAckChange = (ack: boolean) => {
    const updated = setAllergenAcknowledged(ack);
    setCart({ ...updated });
  };

  const handleCheckout = async () => {
    if (cart.items.length === 0) return;

    const risk = hasAllergenRisk(cart);
    if (risk && !cart.acknowledged) {
      setOrderError(dict.ui.allergenAckCheckbox);
      return;
    }

    setSubmittingOrder(true);
    setOrderError(null);

    try {
      const payload = {
        idempotency_key: cart.idempotencyKey,
        items: cart.items.map((i) => ({
          menu_item_id: i.menuItemId,
          quantity: i.quantity,
          notes: i.notes || null,
        })),
        acknowledge_allergen_risk: cart.acknowledged,
      };

      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.status === 409) {
        const errJson = await res.json().catch(() => null);
        if (errJson?.detail?.error === "allergen_ack_required") {
          setOrderError(dict.ui.allergenWarningDescription);
          setCart((c) => {
            const next = { ...c, acknowledged: false };
            saveCart(next);
            return next;
          });
          return;
        }
        const conflictMsg =
          typeof errJson?.detail === "string" ? errJson.detail : "Order conflict. Please retry.";
        throw new Error(conflictMsg);
      }

      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        const generalMsg =
          typeof errJson?.detail === "string"
            ? errJson.detail
            : `Failed to place order (${res.status})`;
        throw new Error(generalMsg);
      }

      const orderData = await res.json();
      clearCart();
      router.push(`/${lang}/orders/${orderData.id}`);
    } catch (err: unknown) {
      setOrderError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmittingOrder(false);
    }
  };

  // Group items by category
  const categories = Array.from(new Set(menu?.items.map((i) => i.category) || []));
  const cartTotal = calculateCartTotal(cart);
  const cartCount = cart.items.reduce((s, i) => s + i.quantity, 0);
  const requiresAck = hasAllergenRisk(cart);

  const formatPrice = useCallback(
    (amount: number) => {
      const currency = menu?.restaurant?.currency || "EUR";
      try {
        return new Intl.NumberFormat(lang, {
          style: "currency",
          currency,
        }).format(amount);
      } catch {
        return `€${amount.toFixed(2)}`;
      }
    },
    [lang, menu?.restaurant?.currency]
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-zinc-400">Loading menu...</p>
        </div>
      </div>
    );
  }

  if (error || !menu) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-zinc-900 border border-zinc-800 rounded-2xl p-6 text-center space-y-4">
          <p className="text-sm text-rose-400">{error || "Unable to display menu."}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-zinc-800 text-xs font-medium rounded-xl hover:bg-zinc-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 pb-28">
      {/* Top Bar */}
      <header className="sticky top-0 z-30 bg-zinc-950/90 backdrop-blur-md border-b border-zinc-800 px-4 py-3 sm:px-6">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-base font-bold text-zinc-100">{menu.restaurant.name}</h1>
            {menu.table_label && (
              <p className="text-xs text-emerald-400 font-medium">
                Table: {menu.table_label}
              </p>
            )}
          </div>
          <button
            onClick={() => setCartOpen(true)}
            className="relative px-3.5 py-1.5 rounded-full bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-xs font-semibold flex items-center gap-2"
          >
            <span>🛒 {dict.ui.cartTitle}</span>
            {cartCount > 0 && (
              <span className="bg-emerald-500 text-zinc-950 px-1.5 py-0.5 rounded-full text-[10px] font-bold">
                {cartCount}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-3xl mx-auto px-4 py-4 sm:px-6 space-y-6">
        {/* Mandatory Staff Notice */}
        <div className="rounded-xl p-3 bg-amber-950/40 border border-amber-900/40 text-xs text-amber-300 leading-relaxed flex items-start gap-2">
          <span className="text-sm">⚠️</span>
          <p>{dict.staffNotice}</p>
        </div>

        {/* Categories & Items */}
        {categories.map((cat) => {
          const catItems = menu.items.filter((i) => i.category === cat);
          return (
            <section key={cat} className="space-y-3">
              <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400 border-b border-zinc-800/80 pb-1">
                {cat}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {catItems.map((item) => {
                  const isAvailable = item.available !== false;
                  return (
                    <div
                      key={item.id}
                      className={`p-4 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 flex flex-col justify-between transition-all ${
                        isAvailable ? "hover:border-zinc-700" : "opacity-50"
                      }`}
                    >
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-semibold text-sm text-zinc-100">{item.name}</h3>
                          <span className="text-sm font-bold text-emerald-400 whitespace-nowrap">
                            {formatPrice(Number(item.price))}
                          </span>
                        </div>

                        {item.description && (
                          <p className="text-xs text-zinc-400 leading-relaxed">
                            {item.description}
                          </p>
                        )}

                        {/* Dietary badges */}
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {item.is_vegetarian && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
                              🌱 {dict.dietary.vegetarian}
                            </span>
                          )}
                          {item.is_vegan && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
                              🌿 {dict.dietary.vegan}
                            </span>
                          )}
                          {item.is_gluten_free && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
                              🌾 {dict.dietary.gluten_free}
                            </span>
                          )}
                        </div>

                        {/* Server-derived Allergen Status Chip */}
                        <div className="pt-1">
                          <AllergenChip
                            status={item.allergen_status}
                            matchedAllergens={item.matched_allergens}
                            locale={lang}
                          />
                        </div>
                      </div>

                      {/* Add button */}
                      <div className="pt-4 flex items-center justify-end">
                        {isAvailable ? (
                          <button
                            onClick={() => handleAddToCart(item)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-medium text-xs shadow-md transition-all"
                          >
                            <span>+</span>
                            <span>{dict.ui.addToCart}</span>
                          </button>
                        ) : (
                          <span className="text-xs text-zinc-500 font-medium italic">
                            {dict.ui.unavailable}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </main>

      {/* Floating Bottom Cart Bar */}
      {cartCount > 0 && !cartOpen && (
        <div className="fixed bottom-4 left-4 right-4 z-20 max-w-md mx-auto">
          <button
            onClick={() => setCartOpen(true)}
            className="w-full py-3 px-5 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm shadow-xl shadow-emerald-950 flex items-center justify-between transition-all active:scale-[0.99]"
          >
            <div className="flex items-center gap-2">
              <span className="bg-emerald-700 px-2 py-0.5 rounded-lg text-xs">
                {cartCount}
              </span>
              <span>{dict.ui.checkout}</span>
            </div>
            <span className="font-bold">{formatPrice(cartTotal)}</span>
          </button>
        </div>
      )}

      {/* Cart Modal / Drawer */}
      {cartOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="bg-zinc-900 border border-zinc-800 w-full max-w-lg rounded-t-3xl sm:rounded-3xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl">
            {/* Header */}
            <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-900">
              <h2 className="text-base font-bold text-zinc-100">{dict.ui.cartTitle}</h2>
              <button
                onClick={() => setCartOpen(false)}
                className="text-zinc-400 hover:text-zinc-100 p-1 text-sm"
              >
                ✕
              </button>
            </div>

            {/* Cart Items */}
            <div className="p-5 overflow-y-auto space-y-4 flex-1">
              {orderError && (
                <div className="p-3 bg-rose-950/70 border border-rose-800 rounded-xl text-xs text-rose-300">
                  {orderError}
                </div>
              )}

              {cart.items.length === 0 ? (
                <p className="text-zinc-500 text-center py-8 text-sm">{dict.ui.emptyCart}</p>
              ) : (
                <div className="space-y-3">
                  {cart.items.map((item, idx) => (
                    <div
                      key={`${item.menuItemId}-${idx}`}
                      className="p-3 rounded-xl bg-zinc-950/60 border border-zinc-800/80 space-y-2"
                    >
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-zinc-200">{item.name}</span>
                        <span className="font-semibold text-emerald-400">
                          {formatPrice(item.price * item.quantity)}
                        </span>
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <AllergenChip
                          status={item.allergenStatus}
                          matchedAllergens={item.matchedAllergens}
                          locale={lang}
                        />

                        {/* Quantity Controls */}
                        <div className="flex items-center gap-2 bg-zinc-800/80 rounded-lg p-1">
                          <button
                            onClick={() =>
                              handleUpdateQuantity(item.menuItemId, item.quantity - 1, item.notes)
                            }
                            className="w-6 h-6 flex items-center justify-center rounded bg-zinc-700 text-xs font-bold hover:bg-zinc-600"
                          >
                            -
                          </button>
                          <span className="text-xs font-semibold px-1">{item.quantity}</span>
                          <button
                            onClick={() =>
                              handleUpdateQuantity(item.menuItemId, item.quantity + 1, item.notes)
                            }
                            className="w-6 h-6 flex items-center justify-center rounded bg-zinc-700 text-xs font-bold hover:bg-zinc-600"
                          >
                            +
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Allergen Acknowledgment Checkbox if Risk Present */}
              {cart.items.length > 0 && requiresAck && (
                <div className="p-3.5 bg-rose-950/50 border border-rose-800/60 rounded-xl space-y-2">
                  <div className="flex items-start gap-2">
                    <span className="text-rose-400">⚠️</span>
                    <p className="text-xs text-rose-300 font-medium">
                      {dict.ui.allergenWarningDescription}
                    </p>
                  </div>
                  <label className="flex items-start gap-2 cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      checked={cart.acknowledged}
                      onChange={(e) => handleAckChange(e.target.checked)}
                      className="mt-0.5 rounded border-zinc-700 text-emerald-600 focus:ring-emerald-500 bg-zinc-950"
                    />
                    <span className="text-xs text-zinc-300 select-none">
                      {dict.ui.allergenAckCheckbox}
                    </span>
                  </label>
                </div>
              )}
            </div>

            {/* Footer / Total & Checkout */}
            {cart.items.length > 0 && (
              <div className="p-5 border-t border-zinc-800 bg-zinc-900/90 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-400 font-medium">{dict.ui.total}</span>
                  <span className="text-lg font-bold text-zinc-100">
                    {formatPrice(cartTotal)}
                  </span>
                </div>
                <button
                  onClick={handleCheckout}
                  disabled={submittingOrder || (requiresAck && !cart.acknowledged)}
                  className="w-full py-3.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-40 text-white font-semibold text-sm shadow-lg shadow-emerald-950 transition-all"
                >
                  {submittingOrder ? dict.ui.placingOrder : dict.ui.placeOrder}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Floating Chat Assistant */}
      <ChatPanel locale={lang} />
    </div>
  );
}
