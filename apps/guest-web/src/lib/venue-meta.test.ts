import { describe, expect, it } from "vitest";
import { venueMetadata, venueViewport } from "./venue-meta";

describe("venueMetadata", () => {
  it("uses the venue's name, icon and manifest", () => {
    const m = venueMetadata({ slug: "angeethi-house", name: "Angeethi House" });
    expect(m.title).toBe("Angeethi House");
    expect(m.manifest).toBe("/venues/angeethi-house/manifest.webmanifest");
    expect(JSON.stringify(m.icons)).toContain("/venues/angeethi-house/mark.svg");
    expect(JSON.stringify(m)).not.toContain("Mise");
  });
  it("names an unbranded venue without inventing an icon or manifest", () => {
    const m = venueMetadata({ slug: "new-venue", name: "New Venue" });
    expect(m.title).toBe("New Venue");
    expect(m.manifest).toBeUndefined();
    expect(m.icons).toBeUndefined();
  });
  it("colours the browser bar with the venue's deep colour", () => {
    expect(venueViewport({ slug: "kehwa-and-crumb", name: "Kehwa & Crumb" }).themeColor).toBe("#064734");
    expect(venueViewport(null).themeColor).toBe("#ffffff");
  });
});
