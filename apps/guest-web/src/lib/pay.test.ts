import { afterEach, describe, expect, it, vi } from "vitest";
import { formatPrice } from "ui";
import { getDictionary } from "../i18n";
import { billState, claimMessage, copyText, detailsFor, isValidReference, needsReference, percent, type GuestBill } from "./pay";

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
