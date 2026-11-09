import { describe, expect, it } from "vitest";
import { activeLabel, keepUnits } from "./kitchen";

const N = "\u00a0";

describe("activeLabel", () => {
  it("is singular only for exactly one", () => {
    expect(activeLabel(0)).toBe("0 ORDERS ACTIVE");
    expect(activeLabel(1)).toBe("1 ORDER ACTIVE");
    expect(activeLabel(2)).toBe("2 ORDERS ACTIVE");
    expect(activeLabel(100)).toBe("100 ORDERS ACTIVE");
  });
});

describe("keepUnits", () => {
  it("joins a number and its unit with a non-breaking space", () => {
    expect(keepUnits("Mutton karahi 1 kg")).toBe(`Mutton karahi 1${N}kg`);
    expect(keepUnits("Half 0.5 kg, 250 g, 330 ml")).toBe(`Half 0.5${N}kg, 250${N}g, 330${N}ml`);
    expect(keepUnits("1 KG")).toBe(`1${N}KG`);
    expect(keepUnits("1 kg + 2 kg")).toBe(`1${N}kg + 2${N}kg`);
  });

  it("leaves everything else alone", () => {
    expect(keepUnits("")).toBe("");
    expect(keepUnits("1kg")).toBe("1kg");
    for (const s of ["2 garlic naan", "10 lemons", "2 grams of saffron", "3 pcsx"]) {
      expect(keepUnits(s)).toBe(s);
    }
  });

  it("really inserts a non-ASCII space", () => {
    expect(keepUnits("1 kg")).not.toBe("1 kg");
  });

  it("is idempotent", () => {
    expect(keepUnits(keepUnits("1 kg"))).toBe(keepUnits("1 kg"));
  });
});
