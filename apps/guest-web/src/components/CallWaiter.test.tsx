import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CallWaiter, callOutcome, formatElapsed } from "./CallWaiter";

describe("CallWaiter", () => {
  it("maps the API answers to what the guest sees", () => {
    expect(callOutcome(201, null)).toBe("called");
    expect(callOutcome(409, null)).toBe("already");
    expect(callOutcome(422, null)).toBe("unavailable");
    expect(callOutcome(429, "37")).toEqual({ wait: 37 });
    expect(callOutcome(429, null)).toEqual({ wait: 60 });
    expect(callOutcome(500, null)).toBe("failed");
  });
  it("formats the waiting time as m:ss", () => {
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(formatElapsed(-2_000)).toBe("0:00"); // phone clock behind the server
  });
  it("renders the button in the guest's language", () => {
    expect(renderToStaticMarkup(<CallWaiter lang="en" extraLabel={null} />)).toContain("Call waiter");
    expect(renderToStaticMarkup(<CallWaiter lang="it" extraLabel="More naan / roti" />)).toContain("More naan / roti");
  });
});
