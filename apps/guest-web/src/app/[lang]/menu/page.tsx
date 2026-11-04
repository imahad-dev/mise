"use client";

import React, { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AllergenChip } from "../../../components/allergen-chip";
import { CallWaiter } from "../../../components/CallWaiter";
import { CodeEntry } from "../../../components/CodeEntry";
import { ChatPanel } from "../../../components/chat-panel";
import { useTableStatus } from "../../../hooks/use-table-status";
import { getDictionary } from "../../../i18n";
import {
  MAX_ITEMS_PER_ORDER,
  cartQuantity,
  claimRestore,
  orderOutcome,
  orderStage,
  rememberNumber,
  rememberedNumber,
  sentOrderId,
  soldOutIds,
} from "../../../lib/ordering";
import { Badge, Button, Sheet, formatPrice as formatAmount } from "ui";
import { serviceLine } from "../../../lib/pay";
import {
  addToCart,
  calculateCartTotal,
  clearCart,
  getCart,
  hasAllergenRisk,
  lineKey,
  saveCart,
  setAllergenAcknowledged,
  toOrderPayload,
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
  options?: MenuOption[];
}

interface MenuOption {
  id: string;
  label: string;
  price: string;
}

interface MenuResponse {
  restaurant: {
    id: string;
    name: string;
    currency: string;
    /** The optional service on table bills; "0.0000" where none applies. */
    service_charge_rate: string;
  };
  table_id?: string | null;
  table_label?: string | null;
  table_kind?: "table" | "counter" | null;
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
  const [sizePickerItem, setSizePickerItem] = useState<MenuItem | null>(null);
  // Last picked dish, so the size sheet keeps its title and rows while it closes.
  const lastPickedItem = useRef<MenuItem | null>(null);
  if (sizePickerItem) lastPickedItem.current = sizePickerItem;
  const pickerItem = sizePickerItem ?? lastPickedItem.current;
  const [submittingOrder, setSubmittingOrder] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);
  const { status, reload: loadStatus } = useTableStatus();
  const [codeOpen, setCodeOpen] = useState(false);
  const [code, setCode] = useState("");
  const [codeMessage, setCodeMessage] = useState<string | null>(null);
  const [lockedUntil, setLockedUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [notice, setNotice] = useState<string | null>(null);
  // Unknown status reads as open: the server still refuses an order the table can't take.
  const mode = status?.table_state ?? "open";
  const closedText = { open: null, waiting: dict.order.waiting, closed: dict.order.thanks, ended: dict.pay.visitEnded }[
    mode
  ];
  const barText = closedText ?? notice;

  const lockedFor = Math.max(0, Math.ceil((lockedUntil - now) / 1000));
  useEffect(() => {
    if (lockedUntil <= Date.now()) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [lockedUntil]);

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

  // Back from a declined first order: its dishes go back in the cart, once.
  useEffect(() => {
    if (!menu) return;
    const orderId = new URLSearchParams(window.location.search).get("restore");
    if (!orderId) return;
    router.replace(`/${lang}/menu`);
    void (async () => {
      try {
        const res = await fetch(`/api/orders/${encodeURIComponent(orderId)}`);
        if (!res.ok) return;
        const order = (await res.json()) as {
          status: string;
          cancel_reason?: string | null;
          items: { menu_item_id: string; option_id?: string | null; quantity: number; notes?: string | null }[];
        };
        if (orderStage(order.status, order.cancel_reason) !== "declined") return;
        setNotice(dict.order.declined);
        if (!claimRestore(orderId)) return;
        let updated: CartState | null = null;
        for (const line of order.items) {
          const item = menu.items.find((i) => i.id === line.menu_item_id);
          const option = item?.options?.find((o) => o.id === line.option_id);
          if (!item || item.available === false || (line.option_id && !option)) continue;
          updated = addToCart(
            {
              menuItemId: item.id,
              name: item.name,
              price: Number(item.price),
              notes: line.notes ?? undefined,
              allergenStatus: item.allergen_status,
              matchedAllergens: item.matched_allergens || [],
            },
            line.quantity,
            option && { id: option.id, label: option.label, price: Number(option.price) },
          );
        }
        if (updated) setCart({ ...updated });
      } catch {
        // the guest can still add the dishes again by hand
      }
    })();
  }, [menu, lang, router, dict.order.declined]);

  const handleAddToCart = (item: MenuItem, option?: MenuOption) => {
    setNotice(null);
    const updated = addToCart(
      {
        menuItemId: item.id,
        name: item.name,
        price: Number(item.price),
        allergenStatus: item.allergen_status,
        matchedAllergens: item.matched_allergens || [],
      },
      1,
      option && { id: option.id, label: option.label, price: Number(option.price) },
    );
    setCart({ ...updated });
  };

  const handleUpdateQuantity = (
    menuItemId: string,
    qty: number,
    notes?: string,
    optionId?: string,
  ) => {
    const updated = updateCartItemQuantity(menuItemId, qty, notes, optionId);
    setCart({ ...updated });
  };

  const handleAckChange = (ack: boolean) => {
    const updated = setAllergenAcknowledged(ack);
    setCart({ ...updated });
  };

  const showCode = (message: string | null) => {
    setCode("");
    setCodeMessage(message);
    setCartOpen(false);
    setCodeOpen(true);
  };

  const showError = (message: string) => {
    setCodeOpen(false);
    setOrderError(message);
    setCartOpen(true);
  };

  const handleCheckout = async (typedNumber?: string) => {
    if (cart.items.length === 0) return;

    if (cartQuantity(cart.items) > MAX_ITEMS_PER_ORDER) {
      showError(dict.order.tooBig);
      return;
    }

    const risk = hasAllergenRisk(cart);
    if (risk && !cart.acknowledged) {
      showError(dict.ui.allergenAckCheckbox);
      return;
    }

    // Asked once per phone, on the first order only; a retry resends the number already typed.
    const number = typedNumber ?? rememberedNumber();
    if (status?.code_required && !number) {
      showCode(null);
      return;
    }

    setSubmittingOrder(true);
    setOrderError(null);

    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...toOrderPayload(cart), ...(number && { code: number }) }),
      });

      if (res.ok) {
        const orderData = await res.json();
        rememberNumber(null);
        setNotice(null);
        clearCart();
        router.push(`/${lang}/orders/${orderData.id}${orderData.over_first_order_cap ? "?big=1" : ""}`);
        return;
      }

      const body = await res.json().catch(() => null);
      const outcome = orderOutcome(res.status, body);
      if (outcome === "code") {
        rememberNumber(null);
        showCode(number ? dict.order.numberWrong : null);
      } else if (outcome === "locked") {
        rememberNumber(null);
        setLockedUntil(Date.now() + 60_000);
        setNow(Date.now());
        showCode(dict.order.tooManyTries);
      } else if (outcome === "not_open") {
        // The cart stays open; its footer shows the waiting, thanks or scan-again message once
        // the status is back.
        setCodeOpen(false);
        setCartOpen(true);
        loadStatus();
      } else if (outcome === "already_sent") {
        // This cart was already sent (a retry after a lost answer): show that order, never a second.
        clearCart();
        setCart(getCart());
        router.push(`/${lang}/orders/${sentOrderId(body)}`);
      } else if (outcome === "unavailable" && soldOutIds(body).length > 0) {
        const gone = new Set(soldOutIds(body));
        const names = [...new Set(cart.items.filter((i) => gone.has(i.menuItemId)).map((i) => i.name))];
        const next = { ...cart, items: cart.items.filter((i) => !gone.has(i.menuItemId)) };
        saveCart(next);
        setCart(next);
        setMenu((m) => m && { ...m, items: m.items.map((i) => (gone.has(i.id) ? { ...i, available: false } : i)) });
        showError(dict.order.soldOut.replace("{names}", names.join(", ")));
      } else if (outcome === "allergen") {
        showError(dict.ui.allergenWarningDescription);
        setCart((c) => {
          const next = { ...c, acknowledged: false };
          saveCart(next);
          return next;
        });
      } else {
        showError(
          {
            ended: dict.pay.visitEnded,
            ask_waiter: dict.order.askWaiter,
            too_fast: dict.order.tooFast,
            too_big: dict.order.tooBig,
            unavailable: dict.order.unavailable,
            failed: dict.order.failed,
          }[outcome],
        );
      }
    } catch {
      showError(dict.order.failed);
    } finally {
      setSubmittingOrder(false);
    }
  };

  const handleCodeChange = (next: string) => {
    setCode(next);
    setCodeMessage(null);
    if (next.length === 4) {
      rememberNumber(next);
      void handleCheckout(next);
    }
  };

  // Group items by category
  const categories = Array.from(new Set(menu?.items.map((i) => i.category) || []));
  const cartTotal = calculateCartTotal(cart);
  const cartCount = cartQuantity(cart.items);
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
            className="px-4 py-2 bg-paper-2 text-xs font-medium rounded-xl hover:bg-line"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const riskyNames = [...new Set(cart.items
    .filter((i) => i.allergenStatus !== "no_declared_match")
    .map((i) => i.name))];
  const catId = (cat: string) => `cat-${cat.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className={`min-h-screen bg-paper text-ink ${barText ? "pb-56" : "pb-28"}`}>
      {/* Always mounted, so a screen reader hears each new bar message. */}
      <p aria-live="polite" className="sr-only">
        {barText}
      </p>
      <header className="sticky top-0 z-30 border-b border-line bg-paper/95 px-4 pt-4 backdrop-blur sm:px-6">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-start justify-between gap-3">
            <div>
              {menu.table_label && (
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
                  {menu.table_kind === "counter" ? menu.table_label : `${dict.ui.table}: ${menu.table_label}`}
                </p>
              )}
              <h1 className="text-2xl text-ink">{menu.restaurant.name}</h1>
              {Number(menu.restaurant.service_charge_rate) > 0 && (
                <p className="text-xs text-ink-muted">{serviceLine(menu.restaurant.service_charge_rate, dict.menu.serviceNotice)}</p>
              )}
              {menu.table_kind === "counter" && (
                <p className="mt-0.5 text-sm font-semibold text-terracotta">{dict.counter.header}</p>
              )}
            </div>
            {mode !== "waiting" && <CallWaiter lang={lang} />}
          </div>
          <p className="mt-0.5 text-xs text-ink-muted">{dict.menu.taxNote}</p>
          <nav aria-label={dict.ui.menuTitle} className="-mx-1 mt-3 flex gap-2 overflow-x-auto pb-3">
            {categories.map((cat) => (
              <a
                key={cat}
                href={`#${catId(cat)}`}
                className="whitespace-nowrap rounded-full border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:bg-line"
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
                  const options = item.options ?? [];
                  return (
                    <li
                      key={item.id}
                      className={`border-b border-dotted border-line py-4 ${isAvailable ? "" : "opacity-50"}`}
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <h3 className="text-base font-semibold text-ink">{item.name}</h3>
                        <span className="whitespace-nowrap font-semibold tabular-nums text-ink">
                          {options.length > 0
                            ? `${dict.menu.from} ${formatPrice(Math.min(...options.map((o) => Number(o.price))))}`
                            : formatPrice(Number(item.price))}
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
                            onClick={() =>
                              options.length > 0 ? setSizePickerItem(item) : handleAddToCart(item)
                            }
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

      {(cartCount > 0 || barText) && (
        <div className="fixed inset-x-4 bottom-4 z-20 mx-auto max-w-md space-y-2">
          {barText && (
            <div className="space-y-3 rounded-2xl border border-line bg-card p-4 shadow-lg">
              <p className="text-base font-semibold text-ink">{barText}</p>
              {mode === "waiting" && (
                <div className="[&_button]:min-h-12 [&_button]:w-full [&_button]:text-base">
                  <CallWaiter lang={lang} />
                </div>
              )}
            </div>
          )}
          {cartCount > 0 && (
            <Button className="min-h-12 w-full justify-between py-3.5 text-base" onClick={() => setCartOpen(true)}>
              <span>
                {dict.ui.checkout} · {cartCount}
              </span>
              <span className="tabular-nums">{formatPrice(cartTotal)}</span>
            </Button>
          )}
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
              {mode === "open" ? (
                <Button
                  className="min-h-12 w-full text-base"
                  onClick={() => void handleCheckout()}
                  disabled={submittingOrder || (requiresAck && !cart.acknowledged)}
                >
                  {submittingOrder ? dict.ui.placingOrder : dict.ui.placeOrder}
                </Button>
              ) : (
                <p className="text-base font-semibold text-ink">{closedText}</p>
              )}
              <p className="text-[11px] leading-relaxed text-ink-muted">{dict.staffNotice}</p>
            </>
          )
        }
      >
        {orderError && (
          <div role="alert" className="rounded-xl bg-danger-bg p-3 text-base text-danger-fg">
            {orderError}
          </div>
        )}

        {cart.items.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-muted">{dict.ui.emptyCart}</p>
        ) : (
          <ul className="divide-y divide-line">
            {cart.items.map((item, idx) => (
              <li key={`${lineKey(item)}-${idx}`} className="space-y-2 py-3">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">
                    {item.optionLabel ? `${item.name} — ${item.optionLabel}` : item.name}
                  </span>
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
                      aria-label={`${dict.ui.decrease} ${item.name}${item.optionLabel ? ` ${item.optionLabel}` : ""}`}
                      onClick={() =>
                        handleUpdateQuantity(item.menuItemId, item.quantity - 1, item.notes, item.optionId)
                      }
                    >
                      −
                    </Button>
                    <span className="w-5 text-center text-sm font-semibold tabular-nums">
                      {item.quantity}
                    </span>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={`${dict.ui.increase} ${item.name}${item.optionLabel ? ` ${item.optionLabel}` : ""}`}
                      onClick={() =>
                        handleUpdateQuantity(item.menuItemId, item.quantity + 1, item.notes, item.optionId)
                      }
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

      <Sheet
        open={sizePickerItem !== null}
        onClose={() => setSizePickerItem(null)}
        title={pickerItem?.name ?? ""}
      >
        <p className="text-sm text-ink-muted">{dict.menu.chooseSize}</p>
        <ul className="space-y-2">
          {(pickerItem?.options ?? []).map((option) => (
            <li key={option.id}>
              <Button
                variant="outline"
                className="w-full justify-between"
                aria-label={`${dict.ui.addToCart} ${pickerItem?.name} ${option.label}`}
                onClick={() => {
                  if (sizePickerItem) handleAddToCart(sizePickerItem, option);
                  setSizePickerItem(null);
                }}
              >
                <span>{option.label}</span>
                <span className="tabular-nums">{formatPrice(Number(option.price))}</span>
              </Button>
            </li>
          ))}
        </ul>
      </Sheet>

      <Sheet open={codeOpen} onClose={() => setCodeOpen(false)} title={dict.order.numberTitle}>
        {codeOpen && (
          <CodeEntry
            lang={lang}
            code={code}
            onChange={handleCodeChange}
            message={codeMessage}
            lockedFor={lockedFor}
            busy={submittingOrder}
          />
        )}
      </Sheet>

      <ChatPanel locale={lang} raised={Boolean(barText)} />
    </div>
  );
}
