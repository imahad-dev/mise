import { describe, expect, it } from "vitest";
import { VISIT_ENDED } from "./pay";
import { TOO_MANY_TRIES, cartQuantity, orderOutcome, orderStage, tableMode, typeDigits } from "./ordering";

const status = (sitting_open: boolean) => ({ id: "s1", sitting_open, code_required: false });

describe("table mode", () => {
  it("lets an open table order", () => {
    expect(tableMode(status(true), false)).toBe("open");
    expect(tableMode(status(true), true)).toBe("open");
  });
  it("tells a new phone a waiter is coming and a phone that ordered thanks for visiting", () => {
    expect(tableMode(status(false), false)).toBe("waiting");
    expect(tableMode(status(false), true)).toBe("closed");
  });
});

describe("order outcome", () => {
  it("maps each refusal to a guest screen", () => {
    expect(orderOutcome(403, { detail: { error: "code_required" } })).toBe("code");
    expect(orderOutcome(429, { detail: TOO_MANY_TRIES })).toBe("locked");
    expect(orderOutcome(429, { detail: "You're ordering quickly! Please wait a moment and try again." })).toBe(
      "too_fast",
    );
    expect(orderOutcome(409, { detail: { error: "table_not_open" } })).toBe("not_open");
    expect(orderOutcome(409, { detail: { error: "allergen_ack_required", items: [] } })).toBe("allergen");
    expect(orderOutcome(409, { detail: { error: "unavailable_items", unavailable_items: [] } })).toBe(
      "unavailable",
    );
    expect(orderOutcome(409, { detail: VISIT_ENDED })).toBe("ended");
  });
  it("recognises the server's 30-item refusal", () => {
    const body = { detail: [{ type: "value_error", msg: "Value error, That's a big order! Please ask your waiter." }] };
    expect(orderOutcome(422, body)).toBe("too_big");
    expect(orderOutcome(422, { detail: [{ msg: "Field required" }] })).toBe("failed");
  });
  it("never passes a raw error through", () => {
    expect(orderOutcome(500, null)).toBe("failed");
    expect(orderOutcome(409, { detail: "Order conflict" })).toBe("failed");
    expect(orderOutcome(403, { detail: "Forbidden" })).toBe("failed");
  });
});

describe("table number boxes", () => {
  it("fills box by box", () => {
    expect(typeDigits("", 0, "4")).toBe("4");
    expect(typeDigits("4", 1, "7")).toBe("47");
  });
  it("takes a pasted or autofilled number into the boxes", () => {
    expect(typeDigits("", 0, "1234")).toBe("1234");
    expect(typeDigits("", 0, " 12-34 ")).toBe("1234");
    expect(typeDigits("", 0, "123456")).toBe("1234");
  });
  it("never leaves a gap and ignores letters", () => {
    expect(typeDigits("1", 3, "9")).toBe("19");
    expect(typeDigits("12", 2, "a")).toBe("12");
  });
  it("typing over a filled box keeps the new digit", () => {
    expect(typeDigits("12", 1, "25")).toBe("15");
  });
  it("clearing a box clears it and the ones after", () => {
    expect(typeDigits("123", 1, "")).toBe("1");
  });
});

describe("order stage", () => {
  it("follows the order from sent to cooking", () => {
    expect(orderStage("pending_approval")).toBe("confirming");
    expect(orderStage("placed")).toBe("cooking");
    expect(orderStage("bumped")).toBe("ready");
  });
  it("tells a declined order from a closed table", () => {
    expect(orderStage("cancelled", "declined")).toBe("declined");
    expect(orderStage("cancelled", "table_closed")).toBe("closed");
    expect(orderStage("cancelled", "voided")).toBe("cancelled");
    expect(orderStage("cancelled")).toBe("cancelled");
  });
});

it("counts portions across lines", () => {
  expect(cartQuantity([{ quantity: 20 }, { quantity: 11 }])).toBe(31);
});
