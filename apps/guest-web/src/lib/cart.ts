export interface CartItem {
  menuItemId: string;
  name: string;
  price: number;
  quantity: number;
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

export function addToCart(
  item: Omit<CartItem, "quantity">,
  quantity = 1,
): CartState {
  const cart = getCart();
  const existingIndex = cart.items.findIndex(
    (i) => i.menuItemId === item.menuItemId && (i.notes || "") === (item.notes || "")
  );

  if (existingIndex >= 0) {
    cart.items[existingIndex].quantity += quantity;
  } else {
    cart.items.push({
      ...item,
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
): CartState {
  const cart = getCart();
  if (quantity <= 0) {
    cart.items = cart.items.filter(
      (i) => !(i.menuItemId === menuItemId && (i.notes || "") === (notes || ""))
    );
  } else {
    const target = cart.items.find(
      (i) => i.menuItemId === menuItemId && (i.notes || "") === (notes || "")
    );
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
