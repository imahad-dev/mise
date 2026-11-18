// @vitest-environment jsdom
import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../brands", () => ({ loadBrand: () => Promise.resolve(null) }));

import { BrandShell } from "./BrandShell";
import { Masthead } from "./Masthead";

afterEach(cleanup);

describe("Masthead", () => {
  it("shows the venue's lockup with the venue name as its text alternative", () => {
    const { getByRole } = render(
      <BrandShell venue={{ slug: "angeethi-house", name: "Angeethi House" }}>
        <Masthead />
      </BrandShell>,
    );
    expect(getByRole("img", { name: "Angeethi House" }).getAttribute("src")).toBe("/venues/angeethi-house/lockup.svg");
  });
  it("shows the name as text for a venue without a logo", () => {
    const { getByRole, container } = render(
      <BrandShell venue={{ slug: "new-venue", name: "New Venue" }}>
        <Masthead />
      </BrandShell>,
    );
    expect(getByRole("heading", { name: "New Venue" })).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
