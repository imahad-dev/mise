// @vitest-environment jsdom
import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { figureParts } from "./figure";

afterEach(cleanup);
const html = (t: string, v: Record<string, string>) => {
  const { container } = render(<p>{figureParts(t, v)}</p>);
  return container;
};
const spans = (c: HTMLElement) => [...c.querySelectorAll("span.figure")].map((s) => s.textContent);

describe("figureParts", () => {
  it("handles a placeholder at the start, middle and end", () => {
    expect(spans(html("{a} to pay", { a: "£1" }))).toEqual(["£1"]);
    expect(spans(html("Send {a} to:", { a: "£1" }))).toEqual(["£1"]);
    expect(html("Total {a}", { a: "£1" }).textContent).toBe("Total £1");
    expect(spans(html("Total {a}", { a: "£1" }))).toEqual(["£1"]);
  });
  it("wraps a repeated placeholder each time", () => {
    expect(spans(html("{a} and {a}", { a: "£1" }))).toEqual(["£1", "£1"]);
  });
  it("leaves a missing value's token visible without crashing", () => {
    const c = html("Pay {nope} now", {});
    expect(c.textContent).toBe("Pay {nope} now");
    expect(spans(c)).toEqual([]);
  });
  it("treats values containing $& or {x} as plain text", () => {
    const c = html("Pay {a}", { a: "$& {x}" });
    expect(c.textContent).toBe("Pay $& {x}");
    expect(spans(c)).toEqual(["$& {x}"]);
  });
  it("keeps sentence words outside the span", () => {
    const c = html("Send {a} to:", { a: "£1" });
    expect(c.querySelector("span.figure")!.textContent).toBe("£1");
    expect(c.textContent).toBe("Send £1 to:");
  });
});
