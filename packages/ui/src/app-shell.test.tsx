import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell, type NavGroup } from "./app-shell";

const groups: NavGroup[] = [
  { label: "Service", items: [{ href: "/", label: "Live orders" }] },
  {
    label: "Insights",
    items: [
      { href: "/brief", label: "Revenue brief" },
      { href: "/ai", label: "What-if" },
    ],
  },
  { label: "Menu", items: [{ href: "/menu", label: "Menu & allergens" }] },
];

describe("AppShell", () => {
  const out = renderToStaticMarkup(
    <AppShell brand={<span>Mise</span>} groups={groups} currentPath="/brief">
      <p>page</p>
    </AppShell>,
  );

  it("renders group labels, links and the page", () => {
    for (const text of ["Service", "Insights", "Menu", "Live orders", "What-if", "page"]) {
      expect(out).toContain(text);
    }
  });

  it("marks only the exact current page as current in each nav", () => {
    // sidebar + phone tab bar each mark /brief once
    expect(out.match(/aria-current="page"/g)).toHaveLength(2);
    expect(out).toMatch(/href="\/brief"[^>]*aria-current="page"/);
    expect(out).not.toMatch(/href="\/menu"[^>]*aria-current="page"/);
  });
});
