import { afterEach, describe, expect, it, vi } from "vitest";
import { pickVenue, readStoredSlug, storeSlug } from "./venue";

const venues = [
  { slug: "angeethi-house", name: "Angeethi House", city: "Lahore", currency: "PKR", role: "owner" as const },
  { slug: "kehwa-and-crumb", name: "Kehwa & Crumb", city: "Islamabad", currency: "PKR", role: "owner" as const },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("venue selection", () => {
  it("uses the stored slug when it is one of my venues", () => {
    expect(pickVenue(venues, "kehwa-and-crumb")?.slug).toBe("kehwa-and-crumb");
  });
  it("falls back to the first venue for an unknown or missing slug", () => {
    expect(pickVenue(venues, "someone-else")?.slug).toBe("angeethi-house");
    expect(pickVenue(venues, null)?.slug).toBe("angeethi-house");
  });
  it("returns null when I have no venues", () => {
    expect(pickVenue([], "x")).toBeNull();
  });
  it("round-trips the slug through storage", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
      },
    });
    storeSlug("kehwa-and-crumb");
    expect(readStoredSlug()).toBe("kehwa-and-crumb");
  });
  it("survives storage that throws", () => {
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("window", { localStorage: { getItem: blocked, setItem: blocked } });
    expect(readStoredSlug()).toBeNull();
    expect(() => storeSlug("x")).not.toThrow();
  });
});
