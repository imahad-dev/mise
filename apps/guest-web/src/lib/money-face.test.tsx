// @vitest-environment jsdom
import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { choiceLine, formatPrice } from "ui";
import { getDictionary } from "../i18n";
import { choicesParts, figureSentence } from "./figure";
import { claimMessage, claimParts, paidParts, paidText, type GuestBill } from "./pay";

afterEach(cleanup);
const en = getDictionary("en");
const claim = (method: "cash" | "card") => ({ method, reference: null, total: "2714.00", claimed_at: "2026-10-27T10:00:00Z", service_included: false });
const rendered = (node: React.ReactNode) => {
  const { container } = render(<p>{node}</p>);
  return { text: container.textContent, figures: [...container.querySelectorAll("span.figure")].map((s) => s.textContent) };
};

describe("money in the fixed face", () => {
  it("claim sentence: amount in .figure, sentence text unchanged", () => {
    for (const counter of [false, true]) {
      const r = rendered(figureSentence(claimParts(claim("cash"), en, "en", "PKR", counter)));
      expect(r.figures).toEqual([formatPrice(2714, "PKR")]);
      expect(r.text).toBe(claimMessage(claim("cash"), en, "en", "PKR", counter));
    }
    expect(rendered(figureSentence(claimParts(claim("card"), en, "en", "PKR"))).figures).toEqual([]);
  });

  it("paid sentence: total in .figure, rate and method stay text", () => {
    const bill = { status: "settled", currency: "PKR", payment_method: "raast", tax_rate: "0.0800", total: "130.00" } as GuestBill;
    const r = rendered(figureSentence(paidParts(bill, en, "en")!));
    expect(r.figures).toEqual([formatPrice(130, "PKR")]);
    expect(r.text).toBe(paidText(bill, en, "en"));
    expect(paidParts({ ...bill, status: "open" }, en, "en")).toBeNull();
  });

  it("choices: only the +amount is a .figure, text equals choiceLine joined", () => {
    const choices = [
      { kind: "add" as const, label: "Extra cheese", price_delta: "50.00" },
      { kind: "pick" as const, label: "Oat milk", price_delta: "0" },
      { kind: "leave_out" as const, label: "Onions", price_delta: "0" },
      { kind: "add" as const, label: "Bacon", price_delta: 120 },
    ];
    const money = (n: number) => formatPrice(n, "PKR");
    const r = rendered(figureSentence(choicesParts(choices, money, en.dish.leaveOut)));
    expect(r.figures).toEqual([money(50), money(120)]);
    expect(r.text).toBe(choices.map((c) => choiceLine(c, money, en.dish.leaveOut)).join(", "));
  });
});
