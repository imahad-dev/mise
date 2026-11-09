import { describe, expect, it } from "vitest";
import { choiceLine } from "./choices";

const money = (n: number) => `£${n.toFixed(2)}`;

describe("choiceLine", () => {
  it("shows a paid extra with its price", () => {
    expect(choiceLine({ kind: "add", label: "Extra milk", price_delta: "0.50" }, money)).toBe("Extra milk +£0.50");
  });
  it("shows a free choice as its label", () => {
    expect(choiceLine({ kind: "pick", label: "Mild", price_delta: "0.00" }, money)).toBe("Mild");
  });
  it("says No for a leave-out", () => {
    expect(choiceLine({ kind: "leave_out", label: "Onions", price_delta: "0" }, money)).toBe("No onions");
  });
  it("keeps an acronym leave-out as written", () => {
    expect(choiceLine({ kind: "leave_out", label: "BBQ sauce", price_delta: "0" }, money)).toBe("No BBQ sauce");
  });
  it("uses a translated leave-out template when given", () => {
    expect(choiceLine({ kind: "leave_out", label: "Onions", price_delta: "0" }, money, "Senza {label}")).toBe("Senza onions");
  });
});
