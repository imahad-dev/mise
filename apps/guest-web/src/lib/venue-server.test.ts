import { afterEach, describe, expect, it, vi } from "vitest";
import { venueFromQr, venueFromSession } from "./venue-server";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "signed" }) }) }));
vi.mock("react", async (orig) => ({ ...(await orig<typeof import("react")>()), cache: (f: unknown) => f }));

afterEach(() => vi.unstubAllGlobals());

const session = {
  id: "visit-1",
  language: "ur",
  venue: { slug: "angeethi-house", name: "Angeethi House", languages: ["en", "ur"], default_language: "en" },
};

describe("venueFromSession", () => {
  it("carries the venue's languages and the visit's language", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(session))));
    expect(await venueFromSession()).toEqual({
      slug: "angeethi-house",
      name: "Angeethi House",
      visitId: "visit-1",
      languages: ["en", "ur"],
      defaultLanguage: "en",
      language: "ur",
    });
  });

  it("an old API answer without languages means English only", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...session, venue: { slug: "x", name: "X" } }))));
    expect(await venueFromSession()).toMatchObject({ languages: ["en"], defaultLanguage: "en" });
  });
});

describe("venueFromQr", () => {
  it("never calls the API for a token with unexpected characters", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const bad of ["", "a/b", "../x", "a b", "a?b=1", "x".repeat(129), "tok\u0000en"]) {
      await expect(venueFromQr(bad)).resolves.toBeNull();
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("looks up a token_urlsafe token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ slug: "kehwa-and-crumb", name: "Kehwa & Crumb" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(venueFromQr("prS10bEgcyuAA7Pc")).resolves.toEqual({
      slug: "kehwa-and-crumb",
      name: "Kehwa & Crumb",
      languages: ["en"],
      defaultLanguage: "en",
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
