export interface CartItem {
  menuItemId: string;
  name: string;
  price: number;
  quantity: number;
  optionId?: string;
  optionLabel?: string;
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

/** A cart line is one dish in one size: Half and Full of the same dish are separate lines. */
export function lineKey(item: { menuItemId: string; optionId?: string }): string {
  return item.menuItemId + ":" + (item.optionId ?? "");
}

function sameLine(a: CartItem, menuItemId: string, optionId?: string, notes?: string): boolean {
  return lineKey(a) === lineKey({ menuItemId, optionId }) && (a.notes || "") === (notes || "");
}

export function addToCart(
  item: Omit<CartItem, "quantity" | "optionId" | "optionLabel">,
  quantity = 1,
  option?: CartOption,
): CartState {
  const cart = getCart();
  const existing = cart.items.find((i) => sameLine(i, item.menuItemId, option?.id, item.notes));

  if (existing) {
    existing.quantity += quantity;
  } else {
    cart.items.push({
      ...item,
      ...(option && { optionId: option.id, optionLabel: option.label, price: option.price }),
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
): CartState {
  const cart = getCart();
  if (quantity <= 0) {
    cart.items = cart.items.filter((i) => !sameLine(i, menuItemId, optionId, notes));
  } else {
    const target = cart.items.find((i) => sameLine(i, menuItemId, optionId, notes));
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
      quantity: i.quantity,
      notes: i.notes || null,
    })),
    acknowledge_allergen_risk: cart.acknowledged,
  };
}
