import { describe, expect, it } from "vitest";
import { formatPrice } from "./format";

describe("formatPrice", () => {
  it("formats euros for English", () => {
    expect(formatPrice(13, "EUR", "en")).toBe("€13.00");
  });

  it("formats euros for Italian with comma decimals", () => {
    expect(formatPrice(1234.5, "EUR", "it")).toBe("1234,50 €");
  });

  it("falls back when the currency code is invalid", () => {
    expect(formatPrice(9.5, "NOT-A-CODE", "en")).toBe("NOT-A-CODE 9.50");
  });
});
