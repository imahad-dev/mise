import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AllergenChip } from "./allergen-chip";

describe("AllergenChip component", () => {
  it("renders 'contains' status with matched allergens badge", () => {
    const html = renderToStaticMarkup(
      <AllergenChip
        status="contains"
        matchedAllergens={["gluten", "crustaceans"]}
        locale="en"
      />
    );

    expect(html).toContain("allergen-chip-contains");
    expect(html).toContain("Contains");
    expect(html).toContain("Gluten");
    expect(html).toContain("Crustaceans");
  });

  it("renders 'unverified' status chip", () => {
    const html = renderToStaticMarkup(<AllergenChip status="unverified" locale="en" />);

    expect(html).toContain("allergen-chip-unverified");
    expect(html).toContain("Unverified");
  });

  it("renders 'no_declared_match' status chip", () => {
    const html = renderToStaticMarkup(<AllergenChip status="no_declared_match" locale="en" />);

    expect(html).toContain("allergen-chip-no-declared-match");
    expect(html).toContain("No declared match");
  });

  it("renders localized text for Italian locale", () => {
    const html = renderToStaticMarkup(
      <AllergenChip
        status="contains"
        matchedAllergens={["gluten"]}
        locale="it"
      />
    );

    expect(html).toContain("allergen-chip-contains");
    expect(html).toContain("Contiene");
    expect(html).toContain("Glutine");
  });
});
