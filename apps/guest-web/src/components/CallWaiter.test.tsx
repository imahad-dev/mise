import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CallWaiterView, callOutcome, formatElapsed, type CallWaiterViewProps } from "./CallWaiter";

const view = (p: Partial<CallWaiterViewProps>) =>
  renderToStaticMarkup(
    <CallWaiterView
      lang="en" extraLabel={null} waitingMs={null} resolved={false} open={false} busy={false} message={null}
      onOpen={() => {}} onClose={() => {}} onSend={() => {}} {...p}
    />,
  );

describe("CallWaiter", () => {
  it("maps the API answers to what the guest sees", () => {
    expect(callOutcome(201, null)).toBe("called");
    expect(callOutcome(409, null)).toBe("already");
    expect(callOutcome(409, null, "Your visit has ended — scan the table QR again")).toBe("ended");
    expect(callOutcome(422, null)).toBe("unavailable");
    expect(callOutcome(429, "37")).toEqual({ wait: 37 });
    expect(callOutcome(429, null)).toEqual({ wait: 60 });
    expect(callOutcome(500, null)).toBe("failed");
  });
  it("formats the waiting time as m:ss", () => {
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(formatElapsed(-2_000)).toBe("0:00");
  });
  it("renders the button and reasons in the guest's language", () => {
    expect(view({})).toContain("Call waiter");
    expect(view({})).toContain("Something else");
    const it_ = view({ lang: "it", extraLabel: "More naan / roti" });
    expect(it_).toContain("Chiama il cameriere");
    expect(it_).toContain("More naan / roti");
  });
  it("announces the call once and keeps the ticking timer out of the live region", () => {
    const html = view({ waitingMs: 65_000 });
    expect(html).toContain('<span role="status">Waiter called</span>');
    expect(html).toContain('<span aria-hidden="true"> · 1:05</span>');
  });
  it("says the call was seen after staff resolve it", () => {
    expect(view({ resolved: true })).toContain("A waiter has seen your call");
  });
});
