"use client";

import React, { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AllergenChip } from "../../../components/allergen-chip";
import { ChatPanel } from "../../../components/chat-panel";
import { getDictionary } from "../../../i18n";
import { Badge, Button, Sheet, formatPrice as formatAmount } from "ui";
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

  const formatPrice = (amount: number) =>
    formatAmount(amount, menu?.restaurant?.currency || "EUR", lang);

  if (loading) {
    return (
      <div className="min-h-screen bg-paper text-ink flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-terracotta border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-ink-muted">Loading menu...</p>
        </div>
      </div>
    );
  }

  if (error || !menu) {
    return (
      <div className="min-h-screen bg-paper text-ink flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-card border border-line rounded-2xl p-6 text-center space-y-4">
          <p className="text-sm text-danger-fg">{error || "Unable to display menu."}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-paper-2 text-xs font-medium rounded-xl hover:bg-paper-2"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const riskyNames = cart.items
    .filter((i) => i.allergenStatus !== "no_declared_match")
    .map((i) => i.name);
  const catId = (cat: string) => `cat-${cat.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="min-h-screen bg-paper pb-28 text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/95 px-4 pt-4 backdrop-blur sm:px-6">
        <div className="mx-auto max-w-3xl">
          {menu.table_label && (
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
              {dict.ui.table}: {menu.table_label}
            </p>
          )}
          <h1 className="text-2xl text-ink">{menu.restaurant.name}</h1>
          <nav aria-label={dict.ui.menuTitle} className="-mx-1 mt-3 flex gap-2 overflow-x-auto pb-3">
            {categories.map((cat) => (
              <a
                key={cat}
                href={`#${catId(cat)}`}
                className="whitespace-nowrap rounded-full border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:bg-paper-2"
              >
                {cat}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-8 px-4 py-4 sm:px-6">
        {categories.map((cat) => (
          <section key={cat} id={catId(cat)} className="scroll-mt-32">
            <h2 className="border-b border-line pb-1 text-lg font-semibold italic text-terracotta">
              {cat}
            </h2>
            <ul>
              {menu.items
                .filter((i) => i.category === cat)
                .map((item) => {
                  const isAvailable = item.available !== false;
                  return (
                    <li
                      key={item.id}
                      className={`border-b border-dotted border-line py-4 ${isAvailable ? "" : "opacity-50"}`}
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <h3 className="text-base font-semibold text-ink">{item.name}</h3>
                        <span className="whitespace-nowrap font-semibold tabular-nums text-ink">
                          {formatPrice(Number(item.price))}
                        </span>
                      </div>
                      {item.description && (
                        <p className="mt-0.5 text-sm text-ink-muted">{item.description}</p>
                      )}
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <div className="flex flex-wrap gap-1.5">
                          <AllergenChip
                            status={item.allergen_status}
                            matchedAllergens={item.matched_allergens}
                            locale={lang}
                          />
                          {item.is_vegetarian && <Badge>{dict.dietary.vegetarian}</Badge>}
                          {item.is_vegan && <Badge>{dict.dietary.vegan}</Badge>}
                          {item.is_gluten_free && <Badge>{dict.dietary.gluten_free}</Badge>}
                        </div>
                        {isAvailable ? (
                          <Button
                            size="icon"
                            aria-label={`${dict.ui.addToCart} ${item.name}`}
                            onClick={() => handleAddToCart(item)}
                          >
                            +
                          </Button>
                        ) : (
                          <span className="text-xs italic text-ink-muted">{dict.ui.unavailable}</span>
                        )}
                      </div>
                    </li>
                  );
                })}
            </ul>
          </section>
        ))}
      </main>

      {cartCount > 0 && (
        <div className="fixed inset-x-4 bottom-4 z-20 mx-auto max-w-md">
          <Button className="w-full justify-between !py-3.5 text-base" onClick={() => setCartOpen(true)}>
            <span>
              {dict.ui.checkout} · {cartCount}
            </span>
            <span className="tabular-nums">{formatPrice(cartTotal)}</span>
          </Button>
        </div>
      )}

      <Sheet
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        title={dict.ui.cartTitle}
        footer={
          cart.items.length > 0 && (
            <>
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-ink-muted">{dict.ui.total}</span>
                <span className="text-lg font-semibold tabular-nums text-ink">
                  {formatPrice(cartTotal)}
                </span>
              </div>
              <Button
                className="w-full"
                onClick={handleCheckout}
                disabled={submittingOrder || (requiresAck && !cart.acknowledged)}
              >
                {submittingOrder ? dict.ui.placingOrder : dict.ui.placeOrder}
              </Button>
              <p className="text-[11px] leading-relaxed text-ink-muted">{dict.staffNotice}</p>
            </>
          )
        }
      >
        {orderError && (
          <div role="alert" className="rounded-xl bg-danger-bg p-3 text-xs text-danger-fg">
            {orderError}
          </div>
        )}

        {cart.items.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-muted">{dict.ui.emptyCart}</p>
        ) : (
          <ul className="divide-y divide-line">
            {cart.items.map((item, idx) => (
              <li key={`${item.menuItemId}-${idx}`} className="space-y-2 py-3">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">{item.name}</span>
                  <span className="font-semibold tabular-nums text-ink">
                    {formatPrice(item.price * item.quantity)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <AllergenChip
                    status={item.allergenStatus}
                    matchedAllergens={item.matchedAllergens}
                    locale={lang}
                  />
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={`− ${item.name}`}
                      onClick={() => handleUpdateQuantity(item.menuItemId, item.quantity - 1, item.notes)}
                    >
                      −
                    </Button>
                    <span className="w-5 text-center text-sm font-semibold tabular-nums">
                      {item.quantity}
                    </span>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={`+ ${item.name}`}
                      onClick={() => handleUpdateQuantity(item.menuItemId, item.quantity + 1, item.notes)}
                    >
                      +
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {cart.items.length > 0 && requiresAck && (
          <div className="space-y-2 rounded-xl bg-danger-bg p-3.5 text-danger-fg">
            <p className="text-sm font-semibold">⚠ {dict.ui.allergenWarningTitle}</p>
            <p className="text-xs">
              {dict.ui.allergenWarningDescription} <b>{riskyNames.join(", ")}</b>
            </p>
            <label className="flex cursor-pointer items-start gap-2 pt-1 text-xs text-ink">
              <input
                type="checkbox"
                checked={cart.acknowledged}
                onChange={(e) => handleAckChange(e.target.checked)}
                className="mt-0.5 accent-terracotta"
              />
              <span>{dict.ui.allergenAckCheckbox}</span>
            </label>
          </div>
        )}
      </Sheet>

      <ChatPanel locale={lang} />
    </div>
  );
}
