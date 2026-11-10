// @vitest-environment jsdom
import React from "react";
import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./fonts", () => ({ display: { variable: "font-d" }, text: { variable: "font-t" } }));

import { brand } from "./index";

function reducedMotion(reduce: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: reduce ? q.includes("reduce") : q.includes("no-preference"),
    media: q,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("Kehwa & Crumb package", () => {
  // jsdom has no matchMedia; GSAP needs one even for the still loader.
  beforeEach(() => reducedMotion(false));
  it("exposes fonts and a decorative motif for both places", () => {
    expect(brand.fontClass).toBe("font-d font-t");
    for (const variant of ["masthead", "bar"] as const) {
      const { container } = render(<brand.Motif variant={variant} />);
      expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    }
  });
  it("loader announces its label", () => {
    const { getByRole } = render(<brand.Loader label="Loading menu" />);
    expect(getByRole("status").textContent).toContain("Loading menu");
  });
  it("welcome names the venue (ampersand as text) and finishes under reduced motion", async () => {
    vi.useFakeTimers();
    reducedMotion(true);
    const onDone = vi.fn();
    const { container } = render(<brand.Welcome name="Kehwa & Crumb" onDone={onDone} />);
    expect(container.textContent).toContain("Kehwa & Crumb");
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    expect(onDone).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
