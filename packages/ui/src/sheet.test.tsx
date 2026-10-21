import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Sheet } from "./sheet";

describe("Sheet", () => {
  it("renders a labelled dialog with title, body and footer", () => {
    const out = renderToStaticMarkup(
      <Sheet open={false} onClose={() => {}} title="Your Order" footer={<p>Total</p>}>
        <p>Carbonara</p>
      </Sheet>,
    );
    expect(out).toMatch(/^<dialog class="sheet" aria-labelledby="([^"]+)">/);
    const id = out.match(/aria-labelledby="([^"]+)"/)?.[1];
    expect(out).toContain(`id="${id}"`);
    expect(out).toContain("Your Order");
    expect(out).toContain("Carbonara");
    expect(out).toContain("Total");
    expect(out).toContain('aria-label="Close"');
  });
});
