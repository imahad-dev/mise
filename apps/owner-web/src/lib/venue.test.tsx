import { afterEach, describe, expect, it, vi } from "vitest";
import { landingPath, pickVenue, readStoredSlug, storeSlug, venueError } from "./venue";

const venues = [
  { slug: "angeethi-house", name: "Angeethi House", city: "Lahore", currency: "PKR", role: "owner" as const },
  { slug: "kehwa-and-crumb", name: "Kehwa & Crumb", city: "Islamabad", currency: "PKR", role: "owner" as const },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("landing path after sign-in", () => {
  const staff = venues.map((v) => ({ ...v, role: "staff" as const }));
  it("sends staff-only accounts to the kitchen", () => {
    expect(landingPath(staff)).toBe("/kitchen");
  });
  it("sends anyone who owns a venue to the dashboard", () => {
    expect(landingPath([staff[0], venues[1]])).toBe("/");
    expect(landingPath(venues)).toBe("/");
  });
  it("sends accounts with no venues to the dashboard", () => {
    expect(landingPath([])).toBe("/");
  });
});

describe("venue error state", () => {
  it("is unauthorized on 401", () => {
    expect(venueError(401, [])).toBe("unauthorized");
  });
  it("is no_venues when signed in with an empty list", () => {
    expect(venueError(200, [])).toBe("no_venues");
  });
  it("is null with venues, on server errors, and on network failure", () => {
    expect(venueError(200, venues)).toBeNull();
    expect(venueError(500, [])).toBeNull();
    expect(venueError(null, [])).toBeNull();
  });
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
