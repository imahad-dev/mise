import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ScanAgain } from "./ScanAgain";

const TEXT = "Scan the QR code on your table again.";

describe("ScanAgain", () => {
  it("asks to scan again and names no venue, no Mise and no link", () => {
    const html = renderToStaticMarkup(<ScanAgain lang="en" />);
    expect(html).toContain(TEXT);
    expect(html).not.toMatch(/Mise|Angeethi|Kehwa/);
    expect(html).not.toContain("<a");
    expect(html).not.toContain("<img");
  });
  it("falls back to English for an unknown language", () => {
    expect(renderToStaticMarkup(<ScanAgain lang="xx" />)).toContain(TEXT);
  });
  it("an Urdu not-found page is right-to-left", () => {
    const html = renderToStaticMarkup(<ScanAgain lang="ur" />);
    expect(html).toMatch(/<main[^>]* lang="ur"/);
    expect(html).toMatch(/<main[^>]* dir="rtl"/);
  });
});
