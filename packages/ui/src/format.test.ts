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

  it("formats PKR as whole rupees", () => {
    expect(formatPrice(2100, "PKR").replace(/\s/g, " ")).toBe("Rs 2,100");
    expect(formatPrice(59.6, "PKR").replace(/\s/g, " ")).toBe("Rs 60");
  });

  it("keeps EUR unchanged", () => {
    expect(formatPrice(13, "EUR")).toBe("€13.00");
  });
});
