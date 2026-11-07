// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import MenuManagementPage from "./page";

// Stable objects: the page's loader depends on them, so fresh ones every render would loop.
const { venueValue, slugRef } = vi.hoisted(() => ({
  venueValue: { venue: { slug: "v", currency: "GBP" } },
  slugRef: { current: "v" },
}));
vi.mock("../../../lib/venue", () => ({
  useVenue: () => venueValue,
  useSlugRef: () => slugRef,
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const item = (id: string, name: string, pay: boolean) => ({
  id, restaurant_id: "r", category: "Drinks", price: "3.00", unit_cost: "1.00", ingredients: [],
  allergens: [], allergen_verified: true, dietary_verified: true, is_vegetarian: true, is_vegan: false,
  is_gluten_free: true, available: true, is_pay_forward: pay, choice_groups: [],
  translations: [{ language: "en", name }],
});

describe("Menu page", () => {
  it("hides the choices editor for the pay-it-forward dish", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([item("1", "Latte", false), item("2", "Chai for a stranger", true)]))),
    );
    render(<MenuManagementPage />);
    await waitFor(() => expect(screen.getByText("Latte")).toBeTruthy());
    expect(screen.getAllByText(/^Choices \(/)).toHaveLength(1);
  });
});
