import { describe, expect, it } from "vitest";
import { NEUTRAL_TOKENS, VENUE_BRANDS } from "ui";
import { brandStyle } from "./style";

describe("brandStyle", () => {
  it("sets every --brand-* variable from the tokens and fonts", () => {
    const b = VENUE_BRANDS["angeethi-house"];
    const s = brandStyle(b.tokens, b) as Record<string, string>;
    expect(s["--brand-surface"]).toBe("#f5ebdd");
    expect(s["--brand-accent"]).toBe("#7f011f");
    expect(s["--brand-on-accent"]).toBe("#f5ebdd");
    expect(s["--brand-button-radius"]).toBe("4px");
    expect(s["--brand-display"]).toBe(b.displayFont);
    expect(s["--brand-text"]).toBe(b.textFont);
  });
  it("falls back to system fonts without a venue", () => {
    const s = brandStyle(NEUTRAL_TOKENS) as Record<string, string>;
    expect(s["--brand-display"]).toMatch(/system-ui/);
    expect(s["--brand-text"]).toMatch(/system-ui/);
  });
  it("never sets ink or the allergen colours", () => {
    const keys = Object.keys(brandStyle(NEUTRAL_TOKENS));
    expect(keys.some((k) => /ink|danger|warn|safe/.test(k))).toBe(false);
  });
});
