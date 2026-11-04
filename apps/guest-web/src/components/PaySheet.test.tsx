// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PaySheet } from "./PaySheet";
import type { GuestBill, PaymentClaim } from "../lib/pay";

const ukBill: GuestBill = {
  bill_no: 1, status: "open", bill_requested_at: null,
  lines: [{ name: "Pie", option_label: null, quantity: 1, unit_price: "21.00", line_total: "21.00" }],
  subtotal: "21.00", currency: "GBP",
  methods: [
    { method: "cash", label: "Cash", payment_class: "standard", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true },
    { method: "card", label: "Card", payment_class: "digital", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true },
  ],
  payment_details: { raast_id: null, jazzcash: null, easypaisa: null, iban: null, account_title: null, sample: false },
  claim: null, voided: [], order_status: null, payment_method: null, tax_rate: null, total: null,
  service_charge_rate: "0.1250", service_charge_amount: "2.63",
};

// jsdom has no <dialog> modal API; Sheet calls it on open.
HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
  this.removeAttribute("open");
};

const sheet = (bill: GuestBill) =>
  render(<PaySheet lang="en" bill={bill} open onClose={() => {}} onUpdated={() => {}} onConflict={() => {}} />);

/** The order page's part: the server's answer replaces the bill. */
function Harness({ initial, open = true }: { initial: GuestBill; open?: boolean }) {
  const [bill, setBill] = React.useState(initial);
  return <PaySheet lang="en" bill={bill} open={open} onClose={() => {}} onUpdated={setBill} onConflict={() => {}} />;
}

const claimOf = (method: PaymentClaim["method"], total: string, service_included: boolean): PaymentClaim => ({
  method, reference: method === "cash" || method === "card" ? null : "TX1", total, claimed_at: "2026-11-04T10:00:00Z", service_included,
});
const bodies = (f: ReturnType<typeof vi.fn>) => f.mock.calls.map((c) => JSON.parse(c[1].body));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PaySheet in a VAT-inclusive venue", () => {
  it("shows one total with VAT included and the optional service switch", () => {
    sheet(ukBill);
    expect(screen.getByText("Includes VAT 20%: £3.50")).toBeTruthy();
    const sw = screen.getByRole("switch", { name: "Add optional service (12.5%): £2.63" });
    expect(sw.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByTestId("pay-total").textContent).toBe("£23.63");
    fireEvent.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByTestId("pay-total").textContent).toBe("£21.00");
    expect(screen.queryByText(/Raast|JazzCash/)).toBeNull();
    expect(screen.queryByText(/incl\. 20% tax/)).toBeNull(); // no per-method tax line
  });

  it("sends the service choice with the claim", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ukBill });
    vi.stubGlobal("fetch", fetchMock);
    sheet(ukBill);
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(screen.getByRole("button", { name: /Card/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodies(fetchMock)[0]).toEqual({ method: "card", reference: null, service_included: false });
  });

  it("sends the service by default", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ukBill });
    vi.stubGlobal("fetch", fetchMock);
    sheet(ukBill);
    fireEvent.click(screen.getByRole("button", { name: /Card/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodies(fetchMock)[0]).toEqual({ method: "card", reference: null, service_included: true });
  });

  it("starts from the table's claim when it left the service off", () => {
    sheet({ ...ukBill, claim: claimOf("card", "21.00", false) });
    expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("false");
    expect(screen.getByTestId("pay-total").textContent).toBe("£21.00");
  });

  it("resets the switch when the sheet opens again", async () => {
    const { rerender } = render(<Harness initial={ukBill} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("false");
    rerender(<Harness initial={ukBill} open={false} />);
    rerender(<Harness initial={ukBill} open />);
    await waitFor(() => expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true"));
  });

  it("updates a cash claim at once when the service is turned off", async () => {
    const claimed = { ...ukBill, claim: claimOf("cash", "23.63", true) };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...ukBill, claim: claimOf("cash", "21.00", false) }) });
    vi.stubGlobal("fetch", fetchMock);
    render(<Harness initial={claimed} />);
    expect(screen.getByText("A waiter is coming to collect £23.63.")).toBeTruthy();
    fireEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(screen.getByText("A waiter is coming to collect £21.00.")).toBeTruthy());
    expect(bodies(fetchMock)).toEqual([{ method: "cash", reference: null, service_included: false }]);
  });

  it("asks to send a transfer again after the service changes", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const bill: GuestBill = {
      ...ukBill,
      methods: [{ method: "bank_transfer", label: "Bank transfer", payment_class: "digital", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true }],
      claim: claimOf("bank_transfer", "23.63", true),
    };
    sheet(bill);
    expect(screen.getByText("Payment sent — waiting for staff to confirm.")).toBeTruthy();
    fireEvent.click(screen.getByRole("switch"));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("Payment sent — waiting for staff to confirm.")).toBeNull();
    expect(screen.getByText("You changed the service — tap “I've paid” again to update your payment.")).toBeTruthy();
    expect(screen.getByText("Send £21.00 to:")).toBeTruthy();
  });

  it("names the rate the Italian way", () => {
    render(<PaySheet lang="it" bill={ukBill} open onClose={() => {}} onUpdated={() => {}} onConflict={() => {}} />);
    expect(screen.getByRole("switch", { name: /\(12,5%\)/ })).toBeTruthy();
    expect(screen.getByText(/^IVA 20% inclusa:/)).toBeTruthy();
  });

  it("asks for the total with service on a transfer method", () => {
    const bill: GuestBill = {
      ...ukBill,
      methods: [{ method: "bank_transfer", label: "Bank transfer", payment_class: "digital", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true }],
      payment_details: { ...ukBill.payment_details, iban: "GB00", account_title: "Sample" },
    };
    sheet(bill);
    fireEvent.click(screen.getByRole("button", { name: /Bank transfer/ }));
    expect(screen.getByText("Send £23.63 to:")).toBeTruthy();
  });
});

describe("PaySheet in a venue without service charge", () => {
  const pkBill: GuestBill = {
    ...ukBill,
    currency: "PKR",
    subtotal: "1000.00",
    methods: [
      { method: "cash", label: "Cash", payment_class: "standard", tax_rate: "0.16", tax_amount: "160.00", total: "1160.00", tax_included: false },
      { method: "card", label: "Card", payment_class: "digital", tax_rate: "0.05", tax_amount: "50.00", total: "1050.00", tax_included: false },
    ],
    service_charge_rate: "0.0000", service_charge_amount: "0.00",
  };
  it("keeps per-method totals and shows no switch", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => pkBill });
    vi.stubGlobal("fetch", fetchMock);
    sheet(pkBill);
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByTestId("pay-total")).toBeNull();
    expect(screen.getByText("incl. 16% tax")).toBeTruthy();
    expect(screen.getByText("incl. 5% tax")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Card/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodies(fetchMock)[0]).toEqual({ method: "card", reference: null, service_included: false });
  });
});
