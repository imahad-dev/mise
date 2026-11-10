// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../brands", () => ({
  loadBrand: (slug: string) => (slug === "broken" ? Promise.reject(new Error("chunk failed")) : Promise.resolve(null)),
}));

import { BrandShell, useVenue } from "./BrandShell";

afterEach(cleanup);

function Name() {
  return <p>{useVenue().name}</p>;
}

describe("BrandShell", () => {
  it("gives its children the venue name and the brand's variables", () => {
    const { container } = render(
      <BrandShell venue={{ slug: "angeethi-house", name: "Angeethi House" }}>
        <Name />
      </BrandShell>,
    );
    expect(screen.getByText("Angeethi House")).toBeTruthy();
    const root = container.querySelector("[data-brand]") as HTMLElement;
    expect(root.dataset.brand).toBe("angeethi-house");
    expect(root.style.getPropertyValue("--brand-accent")).toBe("#7f011f");
  });
  it("renders neutrally for a venue without a brand, still naming it", () => {
    const { container } = render(
      <BrandShell venue={{ slug: "new-venue", name: "New Venue" }}>
        <Name />
      </BrandShell>,
    );
    expect(screen.getByText("New Venue")).toBeTruthy();
    expect((container.querySelector("[data-brand]") as HTMLElement).dataset.brand).toBe("neutral");
  });
  it("keeps the page and skips the welcome when the brand package fails to load", async () => {
    render(
      <BrandShell venue={{ slug: "broken", name: "Broken Venue" }} welcomeFor="visit-1">
        <Name />
      </BrandShell>,
    );
    await waitFor(() => expect(document.querySelector('[data-welcome="done"]')).toBeTruthy());
    expect(screen.getByText("Broken Venue")).toBeTruthy();
    expect(screen.queryByTestId("welcome")).toBeNull();
  });
});
