// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PaySheet } from "./PaySheet";
import type { GuestBill } from "../lib/pay";

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
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ method: "card", reference: null, service_included: false });
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
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ method: "card", reference: null, service_included: false });
  });
});
