import { describe, expect, it } from "vitest";
import { ALERT_LABELS, STAGE_LABELS, formatDuration, hourSpan } from "./service-report";

describe("service report helpers", () => {
  it("formats durations in whole minutes", () => {
    expect(formatDuration(null)).toBe("–");
    expect(formatDuration(0)).toBe("under a minute");
    expect(formatDuration(59)).toBe("under a minute");
    expect(formatDuration(60)).toBe("1 minute");
    expect(formatDuration(89)).toBe("1 minute");
    expect(formatDuration(90)).toBe("2 minutes");
    expect(formatDuration(3_600)).toBe("60 minutes");
  });
  it("shows an hour as its span, wrapping at midnight", () => {
    expect(hourSpan(9)).toBe("09:00–10:00");
    expect(hourSpan(23)).toBe("23:00–00:00");
  });
  it("names steps and alerts in everyday words", () => {
    expect(STAGE_LABELS.approval).toBe("Waiter confirming the first order");
    expect(ALERT_LABELS.order_no_bump).toBe("Order waiting for the kitchen");
    expect(ALERT_LABELS.bill_not_settled).toBe("Bill waiting to be paid");
  });
});
