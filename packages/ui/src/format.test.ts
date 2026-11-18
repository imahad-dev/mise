import { describe, expect, it } from "vitest";
import { formatPrice } from "./format";

const EASTERN_DIGITS = /[٠-٩۰-۹]/;

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

  it("formats pounds and dirhams with two decimals", () => {
    expect(formatPrice(23.63, "GBP", "en")).toBe("£23.63");
    expect(formatPrice(105, "AED", "en").replace(/\s/g, " ")).toBe("AED 105.00");
  });

  it("keeps Latin digits for Arabic and Urdu pages", () => {
    for (const locale of ["ar", "ur", "ar-AE", "ar-EG"]) {
      for (const [amount, currency] of [[105, "AED"], [23.63, "GBP"], [1250, "PKR"], [0, "AED"], [1234567.89, "AED"]] as const) {
        const text = formatPrice(amount, currency, locale);
        expect(text).not.toMatch(EASTERN_DIGITS);
        expect(text.replace(/[^\d.]/g, "")).toMatch(/^\d/);
      }
    }
  });

  it("PKR is the same in every language", () => {
    expect(formatPrice(1250, "PKR", "ur")).toBe(formatPrice(1250, "PKR", "en"));
    expect(formatPrice(1250, "PKR", "ur").replace(/\s/g, " ")).toBe("Rs 1,250");
  });
});
