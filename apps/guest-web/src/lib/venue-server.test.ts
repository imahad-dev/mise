import { afterEach, describe, expect, it, vi } from "vitest";
import { venueFromQr } from "./venue-server";

afterEach(() => vi.unstubAllGlobals());

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
    await expect(venueFromQr("prS10bEgcyuAA7Pc")).resolves.toEqual({ slug: "kehwa-and-crumb", name: "Kehwa & Crumb" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
