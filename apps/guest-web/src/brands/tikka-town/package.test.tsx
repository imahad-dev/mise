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

describe("Tikka Town package", () => {
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
  it("loader shows the skewer normally and the venue's still mark under reduced motion", async () => {
    const skewer = render(<brand.Loader label="Loading menu" />);
    expect(skewer.container.querySelector("img")).toBeNull();
    expect(skewer.container.querySelector("svg")).not.toBeNull();
    skewer.unmount();
    reducedMotion(true);
    const { container } = render(<brand.Loader label="Loading menu" />);
    await act(async () => {});
    expect(container.querySelector("img")?.getAttribute("src")).toBe("/venues/tikka-town/mark.svg");
    expect(container.querySelector("svg")).toBeNull();
    expect(container.textContent).toContain("Loading menu");
  });
  it("welcome names the venue and finishes under reduced motion", async () => {
    vi.useFakeTimers();
    reducedMotion(true);
    const onDone = vi.fn();
    const { container } = render(<brand.Welcome name="Tikka Town" onDone={onDone} />);
    expect(container.textContent).toContain("Tikka Town");
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    expect(onDone).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
