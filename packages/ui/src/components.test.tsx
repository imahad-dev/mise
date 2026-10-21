import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Badge, Button, Card, PageHeader, StatTile, StatusChip } from "./components";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("Button", () => {
  it("maps variants to house classes and defaults to type=button", () => {
    expect(html(<Button>Go</Button>)).toBe('<button type="button" class="btn-primary">Go</button>');
    expect(html(<Button variant="outline">x</Button>)).toContain('class="btn-ghost"');
    expect(html(<Button variant="dark">x</Button>)).toContain('class="btn-dark"');
  });

  it("renders the round icon size with its label", () => {
    const out = html(<Button size="icon" aria-label="Add Carbonara">+</Button>);
    expect(out).toContain('class="btn-primary btn-icon"');
    expect(out).toContain('aria-label="Add Carbonara"');
  });
});

describe("StatusChip", () => {
  it("always pairs the colour with an icon and the text", () => {
    const out = html(<StatusChip tone="contains">Contains: Eggs</StatusChip>);
    expect(out).toContain("chip chip-contains");
    expect(out).toContain('<span aria-hidden="true">⚠</span>');
    expect(out).toContain("Contains: Eggs");
    expect(html(<StatusChip tone="unverified">x</StatusChip>)).toContain(">?</span>");
    expect(html(<StatusChip tone="safe">x</StatusChip>)).toContain(">✓</span>");
  });

  it("passes extra attributes through (used for test ids)", () => {
    expect(html(<StatusChip tone="safe" data-testid="t">x</StatusChip>)).toContain('data-testid="t"');
  });
});

describe("layout pieces", () => {
  it("Card, StatTile, PageHeader and Badge render their classes and content", () => {
    expect(html(<Card>hi</Card>)).toBe('<div class="mise-card">hi</div>');
    const tile = html(<StatTile label="Revenue" value="€1.00" sub="3 orders" />);
    expect(tile).toContain("stat-tile");
    expect(tile).toContain("Revenue");
    expect(tile).toContain("€1.00");
    expect(tile).toContain("3 orders");
    const header = html(<PageHeader title="Revenue brief" subtitle="28 days" />);
    expect(header).toContain("<h1");
    expect(header).toContain("Revenue brief");
    expect(html(<Badge>Vegan</Badge>)).toBe('<span class="chip chip-neutral">Vegan</span>');
  });
});
