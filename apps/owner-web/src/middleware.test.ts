import { beforeEach, describe, expect, it, vi } from "vitest";
import { middleware } from "./middleware";
import { NextResponse } from "next/server";

vi.mock("next/server", () => ({
  NextResponse: {
    redirect: vi.fn((url: URL) => ({
      type: "redirect",
      status: 307,
      url: url.toString(),
    })),
    next: vi.fn(() => ({ type: "next", status: 200 })),
  },
}));

function fakeRequest(
  pathname: string,
  cookies: Record<string, string> = {},
): any {
  return {
    nextUrl: { pathname },
    url: `http://localhost:3001${pathname}`,
    cookies: {
      get: (name: string) =>
        cookies[name] ? { name, value: cookies[name] } : undefined,
    },
  };
}

describe("owner-web middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("allows /login without auth cookie", () => {
    const result = middleware(fakeRequest("/login"));
    expect(NextResponse.next).toHaveBeenCalled();
    expect(result).toEqual({ type: "next", status: 200 });
  });

  it("allows /api/ paths without auth cookie", () => {
    const result = middleware(fakeRequest("/api/health"));
    expect(NextResponse.next).toHaveBeenCalled();
    expect(result).toEqual({ type: "next", status: 200 });
  });

  it("redirects to /login when mise_auth cookie is absent", () => {
    const result = middleware(fakeRequest("/dashboard"));
    expect(NextResponse.redirect).toHaveBeenCalled();
    expect(result).toEqual({
      type: "redirect",
      status: 307,
      url: "http://localhost:3001/login",
    });
  });

  it("passes through when mise_auth cookie is present", () => {
    const result = middleware(
      fakeRequest("/dashboard", { mise_auth: "owner:9999999999.sig" }),
    );
    expect(NextResponse.next).toHaveBeenCalled();
    expect(result).toEqual({ type: "next", status: 200 });
  });
});
