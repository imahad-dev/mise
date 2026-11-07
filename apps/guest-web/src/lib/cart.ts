import type { CartChoice } from "./choices";

export interface CartItem {
  menuItemId: string;
  name: string;
  price: number;
  quantity: number;
  optionId?: string;
  optionLabel?: string;
  choices?: CartChoice[];
  notes?: string;
  allergenStatus: "contains" | "unverified" | "no_declared_match";
  matchedAllergens: string[];
}

export interface CartState {
  idempotencyKey: string;
  items: CartItem[];
  acknowledged: boolean;
}

const STORAGE_KEY = "mise_cart";

export function generateUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function createEmptyCart(): CartState {
  return {
    idempotencyKey: generateUuid(),
    items: [],
    acknowledged: false,
  };
}

export function getCart(): CartState {
  if (typeof window === "undefined") {
    return createEmptyCart();
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const initial = createEmptyCart();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
      return initial;
    }
    const parsed = JSON.parse(raw);
    if (!parsed.idempotencyKey) {
      parsed.idempotencyKey = generateUuid();
    }
    return parsed;
  } catch {
    return createEmptyCart();
  }
}

export function saveCart(cart: CartState): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
  } catch (e) {
    console.error("Failed to save cart to localStorage", e);
  }
}

export function clearCart(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    console.error("Failed to clear cart", e);
  }
}

export interface CartOption {
  id: string;
  label: string;
  price: number;
}

const choiceKey = (ids?: string[]) => [...(ids ?? [])].sort().join(",");

/** A cart line is one dish in one size with one set of choices. */
export function lineKey(item: { menuItemId: string; optionId?: string; choices?: CartChoice[] }): string {
  return `${item.menuItemId}:${item.optionId ?? ""}:${choiceKey(item.choices?.map((c) => c.id))}`;
}

function sameLine(a: CartItem, menuItemId: string, optionId?: string, notes?: string, choiceIds?: string[]): boolean {
  return (
    a.menuItemId === menuItemId &&
    (a.optionId ?? "") === (optionId ?? "") &&
    choiceKey(a.choices?.map((c) => c.id)) === choiceKey(choiceIds) &&
    (a.notes || "") === (notes || "")
  );
}

export function addToCart(
  item: Omit<CartItem, "quantity" | "optionId" | "optionLabel" | "choices">,
  quantity = 1,
  option?: CartOption,
  choices: CartChoice[] = [],
): CartState {
  const cart = getCart();
  const ids = choices.map((c) => c.id);
  const existing = cart.items.find((i) => sameLine(i, item.menuItemId, option?.id, item.notes, ids));

  if (existing) {
    existing.quantity += quantity;
  } else {
    cart.items.push({
      ...item,
      ...(option && { optionId: option.id, optionLabel: option.label }),
      ...(choices.length > 0 && { choices }),
      price: choices.reduce((sum, c) => sum + c.priceDelta, option?.price ?? item.price),
      quantity,
    });
  }

  if (item.allergenStatus === "contains" || item.allergenStatus === "unverified") {
    cart.acknowledged = false;
  }

  saveCart(cart);
  return cart;
}

export function updateCartItemQuantity(
  menuItemId: string,
  quantity: number,
  notes?: string,
  optionId?: string,
  choiceIds?: string[],
): CartState {
  const cart = getCart();
  if (quantity <= 0) {
    cart.items = cart.items.filter((i) => !sameLine(i, menuItemId, optionId, notes, choiceIds));
  } else {
    const target = cart.items.find((i) => sameLine(i, menuItemId, optionId, notes, choiceIds));
    if (target) {
      target.quantity = quantity;
    }
  }

  saveCart(cart);
  return cart;
}

export function setAllergenAcknowledged(acknowledged: boolean): CartState {
  const cart = getCart();
  cart.acknowledged = acknowledged;
  saveCart(cart);
  return cart;
}

export function hasAllergenRisk(cart: CartState): boolean {
  return cart.items.some(
    (item) => item.allergenStatus === "contains" || item.allergenStatus === "unverified"
  );
}

export function calculateCartTotal(cart: CartState): number {
  return cart.items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}

/** Body for POST /api/orders. */
export function toOrderPayload(cart: CartState) {
  return {
    idempotency_key: cart.idempotencyKey,
    items: cart.items.map((i) => ({
      menu_item_id: i.menuItemId,
      option_id: i.optionId ?? null,
      choice_ids: (i.choices ?? []).map((c) => c.id),
      quantity: i.quantity,
      notes: i.notes || null,
    })),
    acknowledge_allergen_risk: cart.acknowledged,
  };
}
