// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
let venue = { slug: "angeethi-house", name: "Angeethi House", branded: false, languages: ["en", "ur"], defaultLanguage: "en" };
vi.mock("./BrandShell", () => ({ useVenue: () => venue }));

import { ScanForm } from "./ScanForm";

beforeEach(() => {
  push.mockReset();
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 201 })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ScanForm languages", () => {
  it("offers only the venue's languages, each in its own name", () => {
    render(<ScanForm token="t" />);
    expect(screen.getByRole("button", { name: "English" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "اردو" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Italiano|العربية/ })).toBeNull();
  });

  it("shows no picker when the venue has one language", () => {
    venue = { ...venue, languages: ["en"] };
    render(<ScanForm token="t" />);
    expect(screen.queryByRole("button", { name: "English" })).toBeNull();
    expect(screen.queryByText("Language")).toBeNull();
    venue = { ...venue, languages: ["en", "ur"] };
  });

  it("choosing Urdu turns the form right-to-left and sends ur, then opens /ur/menu", async () => {
    const { container } = render(<ScanForm token="t" />);
    fireEvent.click(screen.getByRole("button", { name: "اردو" }));
    expect(container.querySelector('[dir="rtl"][lang="ur"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "مینو دیکھیں" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/ur/menu"));
    const body = JSON.parse((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.language).toBe("ur");
  });

  it("starts on the venue's default language", () => {
    venue = { ...venue, defaultLanguage: "ur" };
    const { container } = render(<ScanForm token="t" />);
    expect(container.querySelector('[dir="rtl"]')).not.toBeNull();
    venue = { ...venue, defaultLanguage: "en" };
  });

  it("the selected language is announced as pressed", () => {
    render(<ScanForm token="t" />);
    expect(screen.getByRole("button", { name: "English" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "اردو" }).getAttribute("aria-pressed")).toBe("false");
  });
});
