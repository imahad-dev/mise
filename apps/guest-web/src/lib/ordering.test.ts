import { describe, expect, it } from "vitest";
import { VISIT_ENDED } from "./pay";
import {
  ASK_WAITER,
  TOO_MANY_TRIES,
  cartQuantity,
  claimRestore,
  nextStatusCheck,
  orderOutcome,
  orderStage,
  sentOrderId,
  soldOutIds,
  typeDigits,
} from "./ordering";

describe("checking whether the table is open", () => {
  it("checks every 5 s while the guest waits for the waiter", () => {
    expect(nextStatusCheck({ state: "waiting", failures: 0 })).toBe(5000);
  });
  it("keeps trying when the status is not known yet", () => {
    expect(nextStatusCheck({ failures: 0 })).toBe(5000);
  });
  it("backs off on errors: 5, 10, 20, then every 30 s", () => {
    expect([1, 2, 3, 4, 9].map((failures) => nextStatusCheck({ failures }))).toEqual([
      10_000, 20_000, 30_000, 30_000, 30_000,
    ]);
  });
  it("stops once the table is open, closed or the visit ended, and when signed out", () => {
    for (const state of ["open", "closed", "ended"] as const) {
      expect(nextStatusCheck({ state, failures: 0 })).toBeNull();
    }
    expect(nextStatusCheck({ failures: 1, signedOut: true })).toBeNull();
  });
});

describe("restoring a declined order", () => {
  it("restores each order once, even an older one after a newer", () => {
    expect(claimRestore("o1")).toBe(true);
    expect(claimRestore("o2")).toBe(true);
    expect(claimRestore("o1")).toBe(false);
    expect(claimRestore("o2")).toBe(false);
  });
});

describe("order outcome", () => {
  it("maps each refusal to a guest screen", () => {
    expect(orderOutcome(403, { detail: { error: "code_required" } })).toBe("code");
    expect(orderOutcome(429, { detail: TOO_MANY_TRIES })).toBe("locked");
    expect(orderOutcome(429, { detail: ASK_WAITER })).toBe("ask_waiter");
    expect(orderOutcome(429, { detail: "You're ordering quickly! Please wait a moment and try again." })).toBe(
      "too_fast",
    );
    expect(orderOutcome(409, { detail: { error: "table_not_open" } })).toBe("not_open");
    expect(orderOutcome(409, { detail: { error: "allergen_ack_required", items: [] } })).toBe("allergen");
    expect(orderOutcome(409, { detail: { error: "unavailable_items", unavailable_items: [] } })).toBe(
      "unavailable",
    );
    expect(orderOutcome(409, { detail: VISIT_ENDED })).toBe("ended");
    expect(orderOutcome(409, { detail: { error: "already_sent", order_id: "o1" } })).toBe("already_sent");
  });
  it("reads the order this phone already sent", () => {
    expect(sentOrderId({ detail: { error: "already_sent", order_id: "o1" } })).toBe("o1");
    expect(sentOrderId({ detail: "Order conflict" })).toBeNull();
    expect(sentOrderId(null)).toBeNull();
  });
  it("reads which dishes sold out", () => {
    const body = { detail: { error: "unavailable_items", unavailable_items: [{ menu_item_id: "m1", category: "mains" }] } };
    expect(soldOutIds(body)).toEqual(["m1"]);
    expect(soldOutIds({ detail: "x" })).toEqual([]);
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
