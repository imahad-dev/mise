import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { formatPrice } from "ui";
import { PAYMENT_METHODS, SAMPLE_BILL_FOOTER, billNo, previewFor, sampleBillPieces, sampleBillText, taxLabel } from "./bill";

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

// Shared with services/api/tests/test_money_agreement.py (scripts/gen_tax_vectors.py writes it).
const vectorsUrl = new URL("../../../../data/test-vectors/tax_vectors.json", import.meta.url);
const { vectors } = JSON.parse(readFileSync(fileURLToPath(vectorsUrl), "utf8")) as {
  vectors: { method: string; payment_class: string; subtotal: string; tax_rate: string; tax_amount: string; total: string; currency: string }[];
};

describe("the UI shows the API's tax numbers verbatim", () => {
  it("has the 50 shared vectors", () => {
    expect(vectors).toHaveLength(50);
  });
  it.each(vectors)("$method $subtotal at $tax_rate", (v) => {
    const pieces = sampleBillPieces({
      restaurant_name: "Venue", restaurant_city: null, restaurant_timezone: "Asia/Karachi", currency: v.currency,
      bill_no: 1, table_label: null, settled_at: null, lines: [],
      subtotal: v.subtotal, tax_rate: v.tax_rate, tax_amount: v.tax_amount, total: v.total, payment_method: v.method,
    });
    expect(pieces.totals).toEqual([
      { label: "Subtotal", amount: formatPrice(Number(v.subtotal), v.currency) },
      { label: taxLabel(v.tax_rate, v.method), amount: formatPrice(Number(v.tax_amount), v.currency) },
      { label: "Total", amount: formatPrice(Number(v.total), v.currency) },
    ]);
    // Settle confirms the preview of the method's class, never a total computed here.
    const preview = { payment_class: v.payment_class, tax_rate: v.tax_rate, tax_amount: v.tax_amount, total: v.total } as const;
    const other = { ...preview, total: "-1" };
    const bill = v.payment_class === "digital"
      ? { preview_digital: preview, preview_standard: other }
      : { preview_standard: preview, preview_digital: other };
    expect(previewFor(bill as Parameters<typeof previewFor>[0], v.method)?.total).toBe(v.total);
  });
});
