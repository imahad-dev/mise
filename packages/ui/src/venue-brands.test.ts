import { describe, expect, it } from "vitest";
import { NEUTRAL_TOKENS, VENUE_BRANDS, contrast, venueBrand } from "./venue-brands";

const INK = "#2b2118"; // theme --color-ink, never changed by a brand
const INK_MUTED = "#6b5a48"; // theme --color-ink-muted

describe("contrast", () => {
  it("matches the WCAG formula at the extremes", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 1);
    expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    expect(contrast("#fff", "#000")).toBeCloseTo(21, 1);
  });
  it("rejects a value that is not a hex colour", () => {
    expect(() => contrast("rgb(0 0 0)", "#fff")).toThrow();
  });
});

const all = [
  ...Object.values(VENUE_BRANDS).map((b) => [b.slug, b.tokens] as const),
  ["neutral", NEUTRAL_TOKENS] as const,
];

describe.each(all)("%s tokens", (_slug, t) => {
  it("text on the surfaces is readable (AA 4.5)", () => {
    for (const bg of [t.surface, t.surface2, t.card]) {
      expect(contrast(INK, bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(INK_MUTED, bg)).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("buttons and the masthead are readable (AA 4.5)", () => {
    expect(contrast(t.onAccent, t.accent)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.onAccent, t.accentStrong)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.onDeep, t.deep)).toBeGreaterThanOrEqual(4.5);
  });
  it("the accent stands out from the surface (3:1)", () => {
    expect(contrast(t.accent, t.surface)).toBeGreaterThanOrEqual(3);
  });
});

describe("heading weight", () => {
  it("is a CSS weight or null, and only Kehwa & Crumb sets one", () => {
    for (const [slug, t] of all) expect(t.headingWeight === null || /^[1-9]00$/.test(t.headingWeight), slug).toBe(true);
    expect(VENUE_BRANDS["kehwa-and-crumb"].tokens.headingWeight).toBe("300");
    expect(VENUE_BRANDS["angeethi-house"].tokens.headingWeight).toBeNull();
    expect(NEUTRAL_TOKENS.headingWeight).toBeNull();
  });
});

describe("venueBrand", () => {
  it("finds a known venue and refuses anything else", () => {
    expect(venueBrand("angeethi-house")?.name).toBe("Angeethi House");
    expect(venueBrand("kehwa-and-crumb")?.name).toBe("Kehwa & Crumb");
    for (const bad of [undefined, null, "", "ANGEETHI-HOUSE", "__proto__", "constructor", "../x"]) {
      expect(venueBrand(bad)).toBeNull();
    }
  });
  it("keys every brand by its own slug", () => {
    for (const [key, b] of Object.entries(VENUE_BRANDS)) expect(b.slug).toBe(key);
  });
  it("never uses Fraunces or the Mise terracotta", () => {
    const text = JSON.stringify(VENUE_BRANDS).toLowerCase();
    expect(text).not.toContain("fraunces");
    expect(text).not.toContain("#b5462b");
  });
});
