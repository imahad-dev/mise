import { afterEach, describe, expect, it, vi } from "vitest";
import { formatPrice } from "ui";
import { getDictionary } from "../i18n";
import { billState, claimMessage, counterState, paidText, payForwardThanks, referenceFor, copyText, detailsFor, isValidReference, needsReference, percent, type GuestBill } from "./pay";

const en = getDictionary("en");
const claim = (method: "cash" | "card" | "wallet" | "raast" | "bank_transfer") => ({
  method, reference: method === "cash" || method === "card" ? null : "TX123", total: "2714.00", claimed_at: "2026-10-27T10:00:00Z",
});

describe("pay helpers", () => {
  it("asks for a reference only for wallet, Raast and bank transfer", () => {
    expect(["raast", "wallet", "bank_transfer"].map(needsReference)).toEqual([true, true, true]);
    expect(["cash", "card"].map(needsReference)).toEqual([false, false]);
  });

  it("mirrors the server's reference rule", () => {
    expect(isValidReference("TX123")).toBe(true);
    expect(isValidReference("ab-12_./# 9")).toBe(true);
    expect(isValidReference("x".repeat(64))).toBe(true);
    expect(isValidReference("x".repeat(65))).toBe(false);
    expect(isValidReference("")).toBe(false);
    expect(isValidReference("TX\n1")).toBe(false);
    expect(isValidReference("<script>x</script>")).toBe(false);
    expect(isValidReference("١٢٣")).toBe(false); // Unicode digits are refused like on the server
  });

  it("says the right sentence for each method", () => {
    expect(claimMessage(claim("cash"), en, "en", "PKR")).toBe(`A waiter is coming to collect ${formatPrice(2714, "PKR")}.`);
    expect(claimMessage(claim("card"), en, "en", "PKR")).toBe("A waiter is bringing the card machine.");
    for (const m of ["wallet", "raast", "bank_transfer"] as const) {
      expect(claimMessage(claim(m), en, "en", "PKR")).toBe("Payment sent — waiting for staff to confirm.");
    }
    expect(claimMessage(claim("card"), getDictionary("it"), "it", "PKR")).toBe("Un cameriere porta il POS.");
  });

  it("lists the venue details for the chosen method", () => {
    const d = { raast_id: "0000 SAMPLE", jazzcash: "0000 SAMPLE", easypaisa: null, iban: "PK00", account_title: "Sample", sample: true };
    expect(detailsFor("wallet", d).map((x) => x.key)).toEqual(["jazzcash", "account_title"]);
    expect(detailsFor("raast", d).map((x) => x.key)).toEqual(["raast_id", "account_title"]);
    expect(detailsFor("bank_transfer", d).map((x) => x.key)).toEqual(["iban", "account_title"]);
    expect(detailsFor("cash", d)).toEqual([]);
  });

  it("clears the reference on a method switch, restoring the claim's own", () => {
    const raast = claim("raast");
    expect(referenceFor("wallet", raast)).toBe("");
    expect(referenceFor("raast", raast)).toBe("TX123");
    expect(referenceFor("raast", null)).toBe("");
  });

  it("formats tax rates as percentages", () => {
    expect(percent("0.16")).toBe("16");
    expect(percent("0.165")).toBe("16.5");
  });
});

describe("bill states", () => {
  const bill = (over: Partial<GuestBill>) => ({ status: "open", claim: null, ...over }) as GuestBill;
  it("covers every state the order page shows", () => {
    expect(billState(null, false)).toBe("none");
    expect(billState(bill({}), false)).toBe("open");
    expect(billState(bill({ claim: claim("raast") }), false)).toBe("claimed");
    expect(billState(bill({ status: "settled" }), false)).toBe("paid");
    expect(billState(bill({ status: "cancelled" }), false)).toBe("cancelled");
    expect(billState(bill({}), true)).toBe("ended");
    expect(billState(null, true)).toBe("ended");
    // the guest's own settled bill stays readable after the visit ends
    expect(billState(bill({ status: "settled" }), true)).toBe("paid");
  });
});

describe("paid text", () => {
  const settled = {
    status: "settled", currency: "PKR", payment_method: "raast", tax_rate: "0.0800", total: "130.00",
  } as GuestBill;
  it("says what was paid, with rate and method", () => {
    expect(paidText(settled, en, "en")).toBe(`Paid ${formatPrice(130, "PKR")} (incl. 8% sales tax) by Raast QR`);
    expect(paidText({ ...settled, payment_method: "bank_transfer" }, getDictionary("it"), "it")).toBe(
      `Pagato ${formatPrice(130, "PKR", "it")} (imposta 8% inclusa) con Bonifico`,
    );
  });
  it("is empty until the bill is settled", () => {
    expect(paidText({ ...settled, status: "open", total: null, tax_rate: null, payment_method: null }, en, "en")).toBeNull();
  });
});

describe("copyText", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("returns false without throwing when there is no clipboard", async () => {
    vi.stubGlobal("navigator", {});
    await expect(copyText("x")).resolves.toBe(false);
  });
  it("returns false when the browser refuses", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.reject(new Error("denied")) } });
    await expect(copyText("x")).resolves.toBe(false);
  });
  it("returns true once copied", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await expect(copyText("0000 SAMPLE")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("0000 SAMPLE");
  });
});

describe("counterState", () => {
  const counter = (over: Partial<GuestBill>) =>
    ({ status: "open", claim: null, pickup_label: "K-042", order_status: "awaiting_payment", ...over }) as GuestBill;
  it("is null for table bills and no bill", () => {
    expect(counterState(null)).toBeNull();
    expect(counterState(counter({ pickup_label: null }))).toBeNull();
  });
  it("follows the order from payment to collection", () => {
    expect(counterState(counter({}))).toBe("awaiting");
    expect(counterState(counter({ status: "settled", order_status: "placed" }))).toBe("preparing");
    expect(counterState(counter({ status: "settled", order_status: "bumped" }))).toBe("ready");
    expect(counterState(counter({ status: "settled", order_status: "collected" }))).toBe("collected");
  });
  it("says cancelled for an expired or cancelled order, and awaiting again once revived", () => {
    expect(counterState(counter({ status: "cancelled", order_status: "cancelled" }))).toBe("cancelled");
    expect(counterState(counter({ status: "open", order_status: "awaiting_payment" }))).toBe("awaiting");
  });
  it("tells counter guests to pay cash or card at the counter", () => {
    expect(claimMessage(claim("cash"), en, "en", "PKR", true)).toBe(`Pay ${formatPrice(2714, "PKR")} at the counter.`);
    expect(claimMessage(claim("card"), en, "en", "PKR", true)).toBe("Pay by card at the counter.");
    expect(claimMessage(claim("raast"), en, "en", "PKR", true)).toBe(en.pay.sent);
  });
});

describe("pay-it-forward thanks", () => {
  const bill = { status: "settled", pay_forward_count: 2 } as GuestBill;
  it("thanks the guest for chai bought for others, once settled", () => {
    expect(payForwardThanks(bill, en)).toBe("You bought 2 chai for someone who needs it. Shukriya.");
    expect(payForwardThanks({ ...bill, status: "open" }, en)).toBeNull();
    expect(payForwardThanks({ ...bill, pay_forward_count: 0 }, en)).toBeNull();
  });
});
