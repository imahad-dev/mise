import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { PAYMENT_METHODS, SAMPLE_BILL_FOOTER, billNo, sampleBillText, taxLabel } from "./bill";

describe("sample bill", () => {
  const bill = {
    restaurant_name: "Angeethi House", restaurant_city: "Lahore", restaurant_timezone: "Asia/Karachi", currency: "PKR", bill_no: 42,
    table_label: "T3", settled_at: "2026-10-24T15:30:00Z", status: "settled",
    lines: [{ name: "Chicken Karahi", option_label: "1 kg", quantity: 1, unit_price: "2100.00", line_total: "2100.00" }],
    subtotal: "2100.00", tax_rate: "0.08", tax_amount: "168.00", total: "2268.00", payment_method: "card",
  };
  it("always carries the not-a-tax-invoice footer", () => {
    expect(SAMPLE_BILL_FOOTER).toBe("Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority.");
    expect(sampleBillText(bill)).toContain(SAMPLE_BILL_FOOTER);
  });
  it("never says invoice outside the footer", () => {
    const withoutFooter = sampleBillText(bill).replace(SAMPLE_BILL_FOOTER, "");
    expect(withoutFooter.toLowerCase()).not.toContain("invoice");
    expect(withoutFooter).not.toMatch(/FBR|compliant|integrated/i);
  });
  it("labels tax as illustrative with rate and class", () => {
    expect(sampleBillText(bill)).toContain("Sales tax (illustrative) 8% — card, wallet or QR");
  });
  it("pads bill numbers", () => {
    expect(billNo(42)).toBe("Bill no. 0042");
  });
  it("offers the five payment methods", () => {
    expect(PAYMENT_METHODS.map((m) => m.value)).toEqual(["cash", "card", "wallet", "raast", "bank_transfer"]);
  });
});

describe("bill helpers", () => {
  it("names the tax class for cash and bank transfer", () => {
    expect(taxLabel("0.16", "cash")).toBe("Sales tax (illustrative) 16% — cash");
    expect(taxLabel("0.16", "bank_transfer")).toBe("Sales tax (illustrative) 16% — bank transfer");
  });
  it("keeps fractional rates", () => {
    expect(taxLabel("0.165", "wallet")).toBe("Sales tax (illustrative) 16.5% — card, wallet or QR");
  });
  it("shows a dash when a bill has no number", () => {
    expect(billNo(null)).toBe("Bill no. —");
  });
  it("keeps forbidden wording out of the Bills and print pages", () => {
    const files = ["../app/(dashboard)/bills/page.tsx", "../app/bills/[id]/print/page.tsx", "./bill.ts"];
    for (const file of files) {
      const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8").replace(SAMPLE_BILL_FOOTER, "");
      expect(source, file).not.toMatch(/invoice|FBR|compliant/i);
    }
  });
});
