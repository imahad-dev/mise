import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { formatPrice } from "ui";
import {
  PAYMENT_METHODS, SAMPLE_BILL_FOOTER, amountDueText, billNo, claimChip, claimSummary, claimWarning, previewFor, sampleBillPieces, sampleBillText,
  nextFormState, settlePayload, taxLabel, voidReason, warningKey, billFooter, ratePercent, serviceRateFraction, taxRuleText,
  collectedUndoLeft, counterColumn, isExpiredUnpaid, pickupText, settingsBody, settingsErrors, undoSecondsLeft,
} from "./bill";

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
  it("warns that a cancelled bill was claimed as paid", () => {
    const claim = { method: "raast", reference: "TX1", total: "2527.00", claimed_at: "2026-10-24T15:30:00Z" };
    expect(claimWarning(claim, "PKR")).toBe(
      `Guest said they paid by Raast QR (${formatPrice(2527, "PKR")}) — any refund happens outside Mise.`,
    );
  });
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
      const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8")
        .replace(SAMPLE_BILL_FOOTER, "")
        .replace(`"${billFooter("GB")}"`, "");
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
    // Settle confirms the server's preview for the method, never a total computed here.
    const methods = PAYMENT_METHODS.map((m) => ({
      method: m.value, label: m.label, payment_class: "standard" as const, tax_rate: "0", tax_amount: "0",
      total: m.value === v.method ? v.total : "-1",
    }));
    expect(previewFor({ methods }, v.method)?.total).toBe(v.total);
    expect(previewFor({ methods: methods.filter((m) => m.method !== v.method) }, v.method)).toBeNull();
  });
});

describe("confirm sheet helpers", () => {
  const claim = (method: string, reference: string | null = null) => ({ method, reference, total: "2527.00", claimed_at: "2026-10-27T10:00:00Z" });
  it("words the amount still due or overpaid", () => {
    // ICU puts a no-break space after "Rs"
    expect(amountDueText("60.00", "PKR")?.replace(/\s/g, " ")).toBe("Rs 60 still due");
    expect(amountDueText("-60.00", "PKR")).toBe(`${formatPrice(60, "PKR")} overpaid`);
    expect(amountDueText("0.00", "PKR")).toBeNull();
    expect(amountDueText(null, "PKR")).toBeNull();
  });
  it("shows the claim on the row", () => {
    expect(claimChip(claim("raast", "4471"))).toBe("Guest paying: Raast QR · ref 4471");
    expect(claimChip(claim("wallet", "TX1234567890"))).toBe("Guest paying: JazzCash / Easypaisa · ref TX123456…");
    expect(claimChip(claim("cash"))).toBe("Guest paying: cash");
    expect(claimChip(claim("card"))).toBe("Card machine requested");
    // The sheet shows the full reference and no chip prefix.
    expect(claimSummary(claim("wallet", "TX1234567890"))).toBe("JazzCash / Easypaisa · ref TX1234567890");
    expect(claimSummary(claim("cash"))).toBe("Cash");
  });
  it("builds settle from the selected method's preview, never from the claim", () => {
    const methods = [
      { method: "cash", label: "Cash", payment_class: "standard" as const, tax_rate: "0.16", tax_amount: "374.00", total: "2714.00" },
      { method: "raast", label: "Raast QR", payment_class: "digital" as const, tax_rate: "0.08", tax_amount: "187.00", total: "2527.00" },
    ];
    expect(settlePayload({ methods }, "cash", "TX1", false)).toEqual({
      payment_method: "cash", payment_reference: null, expected_total: "2714.00", expected_method: "cash", acknowledge_reused_reference: false, service_included: false,
    });
    expect(settlePayload({ methods }, "raast", "  TX1 ", true)).toEqual({
      payment_method: "raast", payment_reference: "TX1", expected_total: "2527.00", expected_method: "raast", acknowledge_reused_reference: true, service_included: false,
    });
    expect(settlePayload({ methods }, "card", "", false)).toBeNull();
  });
  it("keys the reused-reference warnings so an acknowledgement resets when they change", () => {
    const d = { reused_reference_bill_no: 1, reused_reference_open_bill_no: null, claim: claim("raast", "TX1") };
    expect(warningKey(d)).toBe(warningKey({ ...d }));
    expect(warningKey(d)).not.toBe(warningKey({ ...d, reused_reference_bill_no: 2 }));
    expect(warningKey(d)).not.toBe(warningKey({ ...d, reused_reference_open_bill_no: 3 }));
    expect(warningKey(d)).not.toBe(warningKey({ ...d, claim: claim("raast", "TX2") }));
    expect(warningKey(null)).toBe("");
  });
  it("follows a live claim unless staff edited the form", () => {
    const raast = claim("raast", "TX1");
    expect(nextFormState(raast, { ...raast, claimed_at: "later" }, false)).toEqual({ apply: null, notice: null });
    expect(nextFormState(null, null, false)).toEqual({ apply: null, notice: null });
    expect(nextFormState(raast, claim("cash"), false)).toEqual({ apply: { method: "cash", reference: "", serviceIncluded: false }, notice: null });
    expect(nextFormState(null, raast, false)).toEqual({ apply: { method: "raast", reference: "TX1", serviceIncluded: false }, notice: null });
    expect(nextFormState(raast, claim("raast", "TX9"), true)).toEqual({
      apply: null,
      notice: "The guest changed their payment to Raast QR · ref TX9 — check before confirming",
    });
  });
  it("builds the void reason", () => {
    expect(voidReason("Wrong table", "ignored")).toBe("Wrong table");
    expect(voidReason("Other", "  Spilled  ")).toBe("Spilled");
    expect(voidReason("Other", "  ")).toBeNull();
    expect(voidReason("Other", "x".repeat(201))).toBeNull();
  });
});

describe("counter helpers", () => {
  const row = (over: Record<string, unknown>) => ({
    status: "open", pickup_label: "K-042", order_status: "awaiting_payment", collected_at: null, pickup_yesterday: false, ...over,
  });
  it("puts each counter bill in its column", () => {
    expect(counterColumn(row({}))).toBe("awaiting");
    expect(counterColumn(row({ status: "settled", order_status: "placed" }))).toBe("preparing");
    expect(counterColumn(row({ status: "settled", order_status: "bumped" }))).toBe("ready");
    expect(counterColumn(row({ status: "settled", order_status: "collected", collected_at: "2026-10-28T10:00:00Z" }))).toBeNull();
    expect(counterColumn(row({ status: "cancelled", order_status: "cancelled" }))).toBeNull();
  });
  it("keeps table bills out of the counter queue", () => {
    expect(counterColumn(row({ pickup_label: null, order_status: null }))).toBeNull();
  });
  it("offers undo on a row collected less than 60 s ago", () => {
    const at = Date.parse("2026-10-28T10:00:00Z");
    const collected = { pickup_label: "K-042", collected_at: "2026-10-28T10:00:00Z" };
    expect(collectedUndoLeft(collected, at + 15_000)).toBe(45);
    expect(collectedUndoLeft(collected, at + 60_000)).toBe(0);
    expect(collectedUndoLeft({ ...collected, collected_at: null }, at)).toBe(0);
  });
  it("always sends every settings field; empty clears", () => {
    expect(settingsBody({ jazzcash: " 03001234567 ", account_title: "Kehwa", pickup_prefix: "", service_extra_label: "  " }, false)).toEqual({
      payment_details: { raast_id: null, jazzcash: "03001234567", easypaisa: null, iban: null, account_title: "Kehwa", sample: false },
      pickup_prefix: null,
      service_extra_label: null,
      sitting_code_required: false,
    });
    expect(settingsBody({ pickup_prefix: "P", service_extra_label: "Extra naan" }, true)).toMatchObject({
      payment_details: { sample: true },
      pickup_prefix: "P",
      service_extra_label: "Extra naan",
    });
  });
  it("sends the table-number choice from its checkbox", () => {
    expect(settingsBody({ sitting_code_required: "on" }, false).sitting_code_required).toBe(true);
    expect(settingsBody({ sitting_code_required: "" }, false).sitting_code_required).toBe(false);
  });
  it("tags yesterday's pickup numbers", () => {
    expect(pickupText(row({}))).toBe("K-042");
    expect(pickupText(row({ pickup_yesterday: true }))).toBe("K-042 · Yesterday");
  });
  it("offers a late payment only on a bill the expiry cancelled", () => {
    const expired = { status: "cancelled", cancel_reason: "Expired unpaid", pickup_label: "K-042" };
    expect(isExpiredUnpaid(expired)).toBe(true);
    expect(isExpiredUnpaid({ ...expired, cancelled_by_name: "Ali" })).toBe(false);
    expect(isExpiredUnpaid({ ...expired, cancel_reason: "Cancelled by staff" })).toBe(false);
    expect(isExpiredUnpaid({ ...expired, pickup_label: null })).toBe(false);
    expect(isExpiredUnpaid({ ...expired, status: "open" })).toBe(false);
  });
  it("counts the 60 s undo window down to zero", () => {
    expect(undoSecondsLeft(1_000, 1_000)).toBe(60);
    expect(undoSecondsLeft(1_000, 31_500)).toBe(30);
    expect(undoSecondsLeft(1_000, 61_000)).toBe(0);
    expect(undoSecondsLeft(1_000, 99_000)).toBe(0);
  });
  it("maps settings errors to their field", () => {
    expect(settingsErrors(422, { detail: { field: "iban", message: "Not a valid Pakistani IBAN" } })).toEqual({ iban: "Not a valid Pakistani IBAN" });
    expect(settingsErrors(409, { detail: "Finish open counter orders before changing the prefix" })).toEqual({
      pickup_prefix: "Finish open counter orders before changing the prefix",
    });
    expect(settingsErrors(422, { detail: [{ loc: ["body", "pickup_prefix"], msg: "String should match pattern" }] })).toEqual({
      pickup_prefix: "String should match pattern",
    });
    expect(settingsErrors(500, null)).toEqual({ form: "Request failed (500)" });
  });
});

describe("VAT-included bills and the optional service", () => {
  const ukBill = {
    methods: [{ method: "card", label: "Card", payment_class: "digital", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true }],
    service_charge_amount: "2.63",
  } as const;

  it("adds the service to the expected total only when included", () => {
    expect(settlePayload(ukBill as never, "card", "", false, true)?.expected_total).toBe("23.63");
    expect(settlePayload(ukBill as never, "card", "", false, true)?.service_included).toBe(true);
    expect(settlePayload(ukBill as never, "card", "", false, false)?.expected_total).toBe("21.00");
    expect(settlePayload(ukBill as never, "card", "", false, false)?.service_included).toBe(false);
  });
  it("never claims a service the bill does not have", () => {
    const none = { ...ukBill, service_charge_amount: "0.00" };
    expect(settlePayload(none as never, "card", "", false, true)).toMatchObject({ expected_total: "21.00", service_included: false });
  });
  it("says VAT is included where it is", () => {
    expect(taxLabel("0.20", "card", true)).toBe("VAT 20% included");
    expect(taxLabel("0.05", "cash", true)).toBe("VAT 5% included");
    expect(taxLabel("0.16", "cash", false)).toBe("Sales tax (illustrative) 16% — cash");
  });
  it("mentions Pakistani authorities only for Pakistani bills", () => {
    expect(billFooter("PB")).toContain("FBR");
    expect(billFooter("ICT")).toBe(SAMPLE_BILL_FOOTER);
    expect(billFooter("GB")).toBe("Sample bill — not a tax invoice.");
    expect(billFooter("AE-DU")).toBe("Sample bill — not a tax invoice.");
    // No jurisdiction: a bill from before venues outside Pakistan.
    expect(billFooter(null)).toBe(SAMPLE_BILL_FOOTER);
  });
  it("prints a settled UK bill with VAT included and the service on top", () => {
    const bill = {
      restaurant_name: "The Anchor", restaurant_city: "London", restaurant_timezone: "Europe/London", currency: "GBP", bill_no: 7,
      table_label: "4", settled_at: "2026-11-02T19:30:00Z", lines: [],
      subtotal: "21.00", tax_rate: "0.20", tax_amount: "3.50", total: "23.63", payment_method: "card",
      tax_jurisdiction: "GB", tax_pricing: "included", service_charge_amount: "2.63",
    };
    const p = sampleBillPieces(bill);
    expect(p.totals).toEqual([
      { label: "Subtotal", amount: formatPrice(21, "GBP") },
      { label: "VAT 20% included", amount: formatPrice(3.5, "GBP") },
      { label: "Optional service", amount: formatPrice(2.63, "GBP") },
      { label: "Total", amount: formatPrice(23.63, "GBP") },
    ]);
    expect(p.footer).toBe("Sample bill — not a tax invoice.");
    expect(sampleBillPieces({ ...bill, service_charge_amount: "0.00", total: "21.00" }).totals.map((r) => r.label)).toEqual([
      "Subtotal", "VAT 20% included", "Total",
    ]);
  });
  it("sends the service rate as a fraction only where the venue offers it", () => {
    expect(settingsBody({ service_charge_rate: "12.5" }, false, true).service_charge_rate).toBe("0.1250");
    expect(settingsBody({ service_charge_rate: "" }, false, true).service_charge_rate).toBe("0.0000");
    expect(settingsBody({ service_charge_rate: "12.5" }, false)).not.toHaveProperty("service_charge_rate");
  });
  it("accepts 0 to 20 per cent in 0.5 steps", () => {
    expect(serviceRateFraction("0")).toBe("0.0000");
    expect(serviceRateFraction("7.5")).toBe("0.0750");
    expect(serviceRateFraction("20")).toBe("0.2000");
    expect(serviceRateFraction("12.3")).toBeNull();
    expect(serviceRateFraction("20.5")).toBeNull();
    expect(serviceRateFraction("-1")).toBeNull();
    expect(serviceRateFraction("ten")).toBeNull();
  });
  it("shows a stored rate as a percentage", () => {
    expect(ratePercent("0.0750")).toBe(7.5);
    expect(ratePercent("0.1250")).toBe(12.5);
  });
  it("names the venue's tax rule", () => {
    expect(taxRuleText({ name: "United Kingdom", rate: "0.20", pricing: "included" })).toBe("Prices include VAT 20% (United Kingdom)");
    expect(taxRuleText({ name: "Punjab, Pakistan", rate: "0.16", pricing: "on_top" })).toBe("Sales tax added to bills (Punjab, Pakistan)");
    expect(taxRuleText(null)).toBeNull();
  });
});

describe("service-charge settings errors", () => {
  it("puts the API's service-charge refusal under its field", () => {
    expect(settingsErrors(422, { detail: "An optional service charge is not offered in Dubai, UAE" })).toEqual({
      service_charge_rate: "An optional service charge is not offered in Dubai, UAE",
    });
    expect(settingsErrors(422, { detail: [{ loc: ["body", "service_charge_rate"], msg: "Input should be less than or equal to 0.2" }] })).toEqual({
      service_charge_rate: "Input should be less than or equal to 0.2",
    });
  });
});

describe("the staff sheet follows the guest's service choice", () => {
  const card = (service_included: boolean) => ({ method: "card", reference: null, total: "21.00", claimed_at: "2026-11-02T19:00:00Z", service_included });
  it("follows a service-only change on an untouched form", () => {
    expect(nextFormState(card(true), card(false), false)).toEqual({ apply: { method: "card", reference: "", serviceIncluded: false }, notice: null });
    expect(nextFormState(card(false), card(true), false)).toEqual({ apply: { method: "card", reference: "", serviceIncluded: true }, notice: null });
  });
  it("warns about a service-only change once staff edited the form", () => {
    expect(nextFormState(card(true), card(false), true)).toEqual({
      apply: null,
      notice: "The guest changed their payment to Card — check before confirming",
    });
  });
  it("applies a claim that arrives later, service included", () => {
    expect(nextFormState(null, card(true), false)).toEqual({ apply: { method: "card", reference: "", serviceIncluded: true }, notice: null });
  });
  it("does nothing when the claim is unchanged", () => {
    expect(nextFormState(card(true), { ...card(true), claimed_at: "later" }, false)).toEqual({ apply: null, notice: null });
    expect(nextFormState(card(true), card(true), true)).toEqual({ apply: null, notice: null });
  });
});
