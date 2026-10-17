import { describe, it, expect, beforeEach } from "vitest";
import {
  getCart,
  addToCart,
  updateCartItemQuantity,
  clearCart,
  createEmptyCart,
  calculateCartTotal,
  hasAllergenRisk,
  saveCart,
} from "./cart";

const store = new Map<string, string>();
const mockLocalStorage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, val: string) => store.set(key, val),
  removeItem: (key: string) => store.delete(key),
  clear: () => store.clear(),
};

describe("Cart and idempotency-key management", () => {
  beforeEach(() => {
    (globalThis as unknown as { localStorage: typeof mockLocalStorage }).localStorage = mockLocalStorage;
    (globalThis as unknown as { window: unknown }).window = globalThis;
    mockLocalStorage.clear();
  });

  it("generates an idempotency key when the cart is built and reuses it on subsequent operations", () => {
    const initialCart = getCart();
    expect(initialCart.idempotencyKey).toBeDefined();
    expect(initialCart.idempotencyKey.length).toBeGreaterThan(10);
    const originalKey = initialCart.idempotencyKey;

    // Adding an item preserves the idempotency key
    const updatedCart = addToCart({
      menuItemId: "item-123",
      name: "Pizza Margherita",
      price: 12.5,
      allergenStatus: "no_declared_match",
      matchedAllergens: [],
    });

    expect(updatedCart.idempotencyKey).toBe(originalKey);
    expect(updatedCart.items).toHaveLength(1);
    expect(updatedCart.items[0].quantity).toBe(1);

    // Reading cart again returns the identical idempotency key
    const reloadedCart = getCart();
    expect(reloadedCart.idempotencyKey).toBe(originalKey);
  });

  it("reuses the same idempotency key across retries and quantity updates", () => {
    addToCart({
      menuItemId: "item-abc",
      name: "Spaghetti Carbonara",
      price: 14.0,
      allergenStatus: "contains",
      matchedAllergens: ["eggs", "milk"],
    });

    const keyBeforeRetry = getCart().idempotencyKey;

    // Simulate quantity update / checkout retry attempt
    updateCartItemQuantity("item-abc", 3);
    const cartAfterUpdate = getCart();
    expect(cartAfterUpdate.idempotencyKey).toBe(keyBeforeRetry);
    expect(cartAfterUpdate.items[0].quantity).toBe(3);

    // Calling getCart during retry preserves idempotency key
    const retryCart = getCart();
    expect(retryCart.idempotencyKey).toBe(keyBeforeRetry);
  });

  it("clears cart and generates a new idempotency key on new cart build", () => {
    const firstCart = addToCart({
      menuItemId: "item-1",
      name: "Tiramisu",
      price: 6.0,
      allergenStatus: "unverified",
      matchedAllergens: [],
    });
    const firstKey = firstCart.idempotencyKey;

    clearCart();

    const secondCart = getCart();
    expect(secondCart.items).toHaveLength(0);
    expect(secondCart.idempotencyKey).toBeDefined();
    expect(secondCart.idempotencyKey).not.toBe(firstKey);
  });

  it("correctly identifies allergen risks and calculates cart total", () => {
    const safeCart = createEmptyCart();
    safeCart.items.push({
      menuItemId: "safe-1",
      name: "Water",
      price: 2.5,
      quantity: 2,
      allergenStatus: "no_declared_match",
      matchedAllergens: [],
    });
    expect(hasAllergenRisk(safeCart)).toBe(false);
    expect(calculateCartTotal(safeCart)).toBe(5.0);

    const riskyCart = createEmptyCart();
    riskyCart.items.push({
      menuItemId: "risk-1",
      name: "Pesto Pasta",
      price: 15.0,
      quantity: 1,
      allergenStatus: "contains",
      matchedAllergens: ["nuts"],
    });
    expect(hasAllergenRisk(riskyCart)).toBe(true);
    expect(calculateCartTotal(riskyCart)).toBe(15.0);
  });

  it("resets cart.acknowledged when adding items with contains or unverified allergen status", () => {
    // Start with acknowledged safe cart
    const cart = getCart();
    cart.acknowledged = true;
    saveCart(cart);

    // Adding safe item keeps acknowledged true
    addToCart({
      menuItemId: "safe-1",
      name: "Water",
      price: 2.0,
      allergenStatus: "no_declared_match",
      matchedAllergens: [],
    });
    expect(getCart().acknowledged).toBe(true);

    // Adding item with 'contains' resets acknowledged to false
    addToCart({
      menuItemId: "allergen-1",
      name: "Peanut Cake",
      price: 5.0,
      allergenStatus: "contains",
      matchedAllergens: ["peanuts"],
    });
    expect(getCart().acknowledged).toBe(false);

    // Re-acknowledge
    const cart2 = getCart();
    cart2.acknowledged = true;
    saveCart(cart2);

    // Adding item with 'unverified' resets acknowledged to false
    addToCart({
      menuItemId: "unverified-1",
      name: "Chef Special",
      price: 18.0,
      allergenStatus: "unverified",
      matchedAllergens: [],
    });
    expect(getCart().acknowledged).toBe(false);
  });
});
