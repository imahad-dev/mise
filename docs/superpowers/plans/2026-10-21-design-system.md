# Design System and Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the guest app, owner dashboard and kitchen display one distinctive "Trattoria editorial" design, built once in a shared `packages/ui`, with no API or behaviour changes.

**Architecture:** A new workspace package `ui` holds the Tailwind v4 theme (tokens, fonts, base styles and the house CSS classes) and a few thin React components that use those classes. Both Next.js apps import `ui/theme.css` and the components. A one-off script maps every hard-coded colour class to a token class; screens whose structure changes (guest menu, order sheet, owner shell, kitchen ticket) are rewritten by hand.

**Tech Stack:** Next.js 15, React 19, Tailwind CSS v4, TypeScript 5, Vitest 3, Playwright 1.49, pnpm 9 workspaces, `@fontsource-variable/fraunces` and `@fontsource-variable/inter`.

**Spec:** `docs/superpowers/specs/2026-10-20-design-system-design.md`

---

## Spec refinements (decided while planning)

1. **`AllergenChip` stays in guest-web.** It depends on guest-web's i18n dictionary. `packages/ui` provides a presentational `StatusChip` (tone, icon, label), and guest-web's `AllergenChip` keeps its logic and its 4 existing tests while rendering `StatusChip`.
2. **No separate `Dialog` yet.** The cart is the only modal in either app. `packages/ui` ships `Sheet` (bottom sheet on native `<dialog>`). Add a centred variant when a screen needs one.
3. **The house CSS classes stay, restyled.** Pages already use `btn-primary`, `btn-ghost`, `btn-danger`, `mise-card`, `chip`, `chip-*` and `stat-tile` (79 uses). They move into `ui/theme.css` with the new look, and the components render those same classes, so there is one source of truth. Only `glass-panel` and `gradient-text` are deleted (mapped to `mise-card` and `text-terracotta`).
4. **Sheet behaviour is tested in Playwright.** Vitest here runs in Node, and jsdom does not implement `HTMLDialogElement.showModal`. Unit tests cover markup; the browser test covers Esc-to-close and focus return.

## Conventions for every task

- Work on branch `feat/design-system`.
- The full stack must be running for browser tests: `LLM_PROVIDER=mock DEMO_MODE=true make up` (rebuild with `--build` after frontend changes: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web owner-web`).
- Never print `.env`. Never call a real LLM provider.
- Commit message footer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File structure

```
packages/ui/
  package.json            name "ui"; exports "." and "./theme.css"
  tsconfig.json
  vitest.config.ts
  src/
    theme.css             tokens (@theme), fonts, base, house classes, sheet styles, @source
    index.ts              re-exports
    format.ts             formatPrice
    format.test.ts
    components.tsx        Button, Card, StatTile, PageHeader, Badge, StatusChip
    components.test.tsx
    sheet.tsx             Sheet (native <dialog>)
    sheet.test.tsx
    app-shell.tsx         AppShell (sidebar + phone tab bar)
    app-shell.test.tsx
scripts/retheme_classes.py   one-off colour-class migration (deleted in the last task)
apps/guest-web/…            globals.css, layout, pages, allergen-chip, dictionaries, manifest, logo
apps/owner-web/…            globals.css, layouts, pages, lib/analytics.ts, logo
apps/*/next.config.ts       transpilePackages
apps/*/Dockerfile           COPY packages/ui/package.json
e2e/flows.spec.ts           selectors + sheet behaviour + screenshots
```

---

### Task 1: Create the `ui` package skeleton

**Files:**
- Create: `packages/ui/package.json`, `packages/ui/tsconfig.json`, `packages/ui/vitest.config.ts`, `packages/ui/src/index.ts`

- [ ] **Step 1: Write `packages/ui/package.json`**

```json
{
  "name": "ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": {
    ".": "./src/index.ts",
    "./theme.css": "./src/theme.css"
  },
  "scripts": {
    "lint": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@fontsource-variable/fraunces": "^5.1.0",
    "@fontsource-variable/inter": "^5.1.1"
  },
  "peerDependencies": {
    "react": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "typescript": "^5",
    "vitest": "^3"
  }
}
```

- [ ] **Step 2: Write `packages/ui/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "jsx": "react-jsx",
    "module": "esnext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "isolatedModules": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write `packages/ui/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { globals: true, environment: "node" },
});
```

- [ ] **Step 4: Write a placeholder `packages/ui/src/index.ts` so the package resolves**

```ts
export {};
```

- [ ] **Step 5: Install and confirm the workspace sees the package**

Run: `pnpm install`
Expected: ends with `Done`; `pnpm -r ls --depth -1` lists `ui`.

- [ ] **Step 6: Commit**

```bash
git add packages/ui pnpm-lock.yaml
git commit -m "feat(ui): add shared ui package skeleton"
```

---

### Task 2: `formatPrice` (TDD)

**Files:**
- Create: `packages/ui/src/format.ts`
- Test: `packages/ui/src/format.test.ts`
- Modify: `packages/ui/src/index.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { formatPrice } from "./format";

describe("formatPrice", () => {
  it("formats euros for English", () => {
    expect(formatPrice(13, "EUR", "en")).toBe("€13.00");
  });

  it("formats euros for Italian with comma decimals", () => {
    expect(formatPrice(1234.5, "EUR", "it")).toBe("1234,50 €");
  });

  it("falls back when the currency code is invalid", () => {
    expect(formatPrice(9.5, "NOT-A-CODE", "en")).toBe("NOT-A-CODE 9.50");
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pnpm --filter ui test`
Expected: FAIL, `Cannot find module './format'` or `formatPrice is not a function`.

- [ ] **Step 3: Implement**

`packages/ui/src/format.ts`:

```ts
/** Currency amount for display, e.g. €13.00 (en) or 13,00 € (it). */
export function formatPrice(amount: number, currency = "EUR", locale = "en"): string {
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}
```

`packages/ui/src/index.ts`:

```ts
export { formatPrice } from "./format";
```

- [ ] **Step 4: Run the tests**

Run: `pnpm --filter ui test`
Expected: 3 passed. If the Italian case prints `1.234,50 €`, Node's ICU groups thousands for `it`; change the expectation to the exact string Node prints and keep the ` ` (non-breaking space) before `€`.

- [ ] **Step 5: Commit**

```bash
git add packages/ui/src
git commit -m "feat(ui): add formatPrice"
```

---

### Task 3: Theme tokens, fonts and house classes

**Files:**
- Create: `packages/ui/src/theme.css`

- [ ] **Step 1: Write `packages/ui/src/theme.css`**

```css
/* Mise design system: tokens, fonts, base and house classes. Imported by both apps. */
@import "@fontsource-variable/inter";
@import "@fontsource-variable/fraunces";
@import "@fontsource-variable/fraunces/wght-italic.css";

/* Tailwind must scan the shared components for class names. */
@source "./";

@theme {
  --color-paper: #f6f0e6;
  --color-paper-2: #efe6d7;
  --color-card: #fbf7f0;
  --color-ink: #2b2118;
  --color-ink-muted: #6b5a48;
  --color-line: rgb(43 33 24 / 0.14);
  --color-terracotta: #b5462b;
  --color-terracotta-strong: #9a3518;
  --color-cream: #fff8ef;
  --color-olive: #4a5d3a;

  --color-danger-bg: #f7dcd6;
  --color-danger-fg: #8a1c12;
  --color-warn-bg: #f5e6c4;
  --color-warn-fg: #7a4e08;
  --color-safe-bg: #e3ead5;
  --color-safe-fg: #3b4d2c;

  /* Kitchen display (dark). Text on the accent colours must be espresso (contrast >= 4.9). */
  --color-espresso: #17120d;
  --color-kds-card: #221b14;
  --color-kds-muted: #bbaa94;
  --color-kds-accent: #e2673f;
  --color-kds-fresh: #8db46a;
  --color-kds-warn: #e0a33a;
  --color-kds-late: #e5533d;

  --font-sans: "Inter Variable", Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-serif: "Fraunces Variable", Georgia, "Times New Roman", serif;
}

@layer base {
  * {
    border-color: var(--color-line);
  }
  body {
    background-color: var(--color-paper);
    color: var(--color-ink);
    font-family: var(--font-sans);
    min-height: 100vh;
  }
  h1,
  h2,
  h3 {
    font-family: var(--font-serif);
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  :focus-visible {
    outline: 2px solid var(--color-terracotta);
    outline-offset: 2px;
  }
}

/* Buttons */
.btn-primary,
.btn-ghost,
.btn-dark,
.btn-danger {
  min-height: 44px;
  padding: 0.625rem 1.25rem;
  border-radius: 9999px;
  font-weight: 600;
  font-size: 0.875rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s;
}
.btn-primary {
  background: var(--color-terracotta);
  color: var(--color-cream);
}
.btn-primary:hover {
  background: var(--color-terracotta-strong);
}
.btn-ghost {
  background: transparent;
  color: var(--color-ink);
  border: 1px solid rgb(43 33 24 / 0.28);
}
.btn-ghost:hover {
  background: var(--color-paper-2);
}
.btn-dark {
  background: var(--color-ink);
  color: var(--color-paper);
}
.btn-danger {
  background: var(--color-danger-fg);
  color: var(--color-cream);
}
.btn-primary:disabled,
.btn-ghost:disabled,
.btn-dark:disabled,
.btn-danger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
/* Round icon button (e.g. "+" add). Needs an aria-label. 40px meets the 24px minimum target. */
.btn-icon {
  min-height: 40px;
  width: 40px;
  padding: 0;
  font-size: 1.25rem;
  line-height: 1;
}

/* Surfaces */
.mise-card {
  background: var(--color-card);
  border: 1px solid var(--color-line);
  border-radius: 16px;
  padding: 1.25rem;
}
.stat-tile {
  background: var(--color-card);
  border: 1px solid var(--color-line);
  border-radius: 14px;
  padding: 1rem 1.25rem;
}

/* Chips: colour + icon + word, never colour alone */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.65rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  min-height: 24px;
}
.chip-neutral {
  background: var(--color-paper-2);
  color: #5c4a36;
}
.chip-contains {
  background: var(--color-danger-bg);
  color: var(--color-danger-fg);
}
.chip-unverified {
  background: var(--color-warn-bg);
  color: var(--color-warn-fg);
}
.chip-safe {
  background: var(--color-safe-bg);
  color: var(--color-safe-fg);
}

/* Bottom sheet on native <dialog> */
.sheet {
  margin: auto auto 0;
  width: 100%;
  max-width: 32rem;
  max-height: 90vh;
  padding: 0;
  border: 0;
  border-radius: 22px 22px 0 0;
  background: var(--color-card);
  color: var(--color-ink);
  box-shadow: 0 -8px 24px rgb(43 33 24 / 0.18);
}
.sheet::backdrop {
  background: rgb(43 33 24 / 0.4);
}
@media (min-width: 640px) {
  .sheet {
    margin: auto;
    border-radius: 22px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  ::before,
  ::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 2: Check the font package paths exist**

Run: `ls packages/ui/node_modules/@fontsource-variable/fraunces/ && ls packages/ui/node_modules/@fontsource-variable/inter/`
Expected: `index.css` in both and `wght-italic.css` in fraunces. If `wght-italic.css` is missing, use the italic file name that is listed and update the third `@import`.

- [ ] **Step 3: Commit**

```bash
git add packages/ui/src/theme.css
git commit -m "feat(ui): add theme tokens, fonts and house classes"
```

---

### Task 4: Basic components (TDD)

**Files:**
- Create: `packages/ui/src/components.tsx`
- Test: `packages/ui/src/components.test.tsx`
- Modify: `packages/ui/src/index.ts`

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pnpm --filter ui test`
Expected: FAIL, `Cannot find module './components'`.

- [ ] **Step 3: Implement `packages/ui/src/components.tsx`**

```tsx
import React from "react";

const cx = (...parts: (string | false | undefined)[]) => parts.filter(Boolean).join(" ");

const BUTTON_CLASS = {
  primary: "btn-primary",
  outline: "btn-ghost",
  dark: "btn-dark",
  danger: "btn-danger",
} as const;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof BUTTON_CLASS;
  size?: "md" | "icon";
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(BUTTON_CLASS[variant], size === "icon" && "btn-icon", className)}
      {...rest}
    />
  );
}

export function Card({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("mise-card", className)} {...rest} />;
}

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}

export function StatTile({ label, value, sub }: StatTileProps) {
  return (
    <div className="stat-tile space-y-1">
      <span className="block text-xs font-semibold uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <div className="font-serif text-3xl font-bold text-ink">{value}</div>
      {sub && <div className="text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

export interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Badge({ className, ...rest }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cx("chip chip-neutral", className)} {...rest} />;
}

const STATUS_ICON = { contains: "⚠", unverified: "?", safe: "✓" } as const;

export interface StatusChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone: keyof typeof STATUS_ICON;
  [dataAttribute: `data-${string}`]: string | undefined;
}

export function StatusChip({ tone, className, children, ...rest }: StatusChipProps) {
  return (
    <span className={cx("chip", `chip-${tone}`, className)} {...rest}>
      <span aria-hidden="true">{STATUS_ICON[tone]}</span>
      {children}
    </span>
  );
}
```

`packages/ui/src/index.ts`:

```ts
export { formatPrice } from "./format";
export { Badge, Button, Card, PageHeader, StatTile, StatusChip } from "./components";
export type { ButtonProps, PageHeaderProps, StatTileProps, StatusChipProps } from "./components";
```

- [ ] **Step 4: Run tests and type check**

Run: `pnpm --filter ui test && pnpm --filter ui lint`
Expected: all tests pass; `tsc --noEmit` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add packages/ui/src
git commit -m "feat(ui): add Button, Card, StatTile, PageHeader, Badge and StatusChip"
```

---

### Task 5: `Sheet` on native `<dialog>` (TDD for markup)

**Files:**
- Create: `packages/ui/src/sheet.tsx`
- Test: `packages/ui/src/sheet.test.tsx`
- Modify: `packages/ui/src/index.ts`

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pnpm --filter ui test`
Expected: FAIL, `Cannot find module './sheet'`.

- [ ] **Step 3: Implement `packages/ui/src/sheet.tsx`**

```tsx
"use client";

import React, { useEffect, useId, useRef } from "react";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Bottom sheet (centred from 640px) on the native <dialog> element: the browser traps focus,
 * closes on Esc and returns focus to the element that opened it.
 */
export function Sheet({ open, onClose, title, children, footer }: SheetProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // click on the backdrop
      }}
    >
      <div className="flex max-h-[90vh] flex-col">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-xl text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="btn-ghost btn-icon text-base"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">{children}</div>
        {footer && <div className="space-y-3 border-t border-line p-5">{footer}</div>}
      </div>
    </dialog>
  );
}
```

Add to `packages/ui/src/index.ts`:

```ts
export { Sheet } from "./sheet";
export type { SheetProps } from "./sheet";
```

- [ ] **Step 4: Run tests and type check**

Run: `pnpm --filter ui test && pnpm --filter ui lint`
Expected: all pass, no type errors.

- [ ] **Step 5: Commit**

```bash
git add packages/ui/src
git commit -m "feat(ui): add Sheet on native dialog"
```

---

### Task 6: `AppShell` (TDD)

**Files:**
- Create: `packages/ui/src/app-shell.tsx`
- Test: `packages/ui/src/app-shell.test.tsx`
- Modify: `packages/ui/src/index.ts`

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pnpm --filter ui test`
Expected: FAIL, `Cannot find module './app-shell'`.

- [ ] **Step 3: Implement `packages/ui/src/app-shell.tsx`**

```tsx
import React from "react";

export interface NavItem {
  href: string;
  label: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export interface AppShellProps {
  brand: React.ReactNode;
  groups: NavGroup[];
  currentPath: string;
  /** Link component, e.g. next/link. Defaults to a plain anchor. */
  linkAs?: React.ElementType;
  banner?: React.ReactNode;
  sidebarFooter?: React.ReactNode;
  children: React.ReactNode;
}

/** Owner layout: grouped sidebar from 768px, horizontally scrolling tab bar below. */
export function AppShell({
  brand,
  groups,
  currentPath,
  linkAs: Link = "a",
  banner,
  sidebarFooter,
  children,
}: AppShellProps) {
  const link = (item: NavItem, className: string) => {
    const current = item.href === currentPath;
    return (
      <Link
        key={item.href}
        href={item.href}
        aria-current={current ? "page" : undefined}
        className={`${className} ${current ? "bg-ink text-paper" : "text-ink hover:bg-paper"}`}
      >
        {item.label}
      </Link>
    );
  };

  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      {banner}
      <div className="flex flex-1">
        <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-paper-2 px-4 py-5 md:flex">
          {brand}
          <nav aria-label="Main" className="mt-4 flex-1 space-y-4">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
                  {group.label}
                </p>
                <div className="space-y-0.5">
                  {group.items.map((item) =>
                    link(item, "block rounded-lg px-2 py-2 text-sm font-medium"),
                  )}
                </div>
              </div>
            ))}
          </nav>
          {sidebarFooter}
        </aside>
        <main className="min-w-0 flex-1 px-4 pb-24 pt-6 sm:px-8 md:pb-8">{children}</main>
      </div>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 flex gap-1 overflow-x-auto border-t border-line bg-paper-2 px-2 py-2 md:hidden"
      >
        {groups.flatMap((group) => group.items).map((item) =>
          link(item, "whitespace-nowrap rounded-full px-3 py-2 text-xs font-semibold"),
        )}
      </nav>
    </div>
  );
}
```

Add to `packages/ui/src/index.ts`:

```ts
export { AppShell } from "./app-shell";
export type { AppShellProps, NavGroup, NavItem } from "./app-shell";
```

- [ ] **Step 4: Run tests and type check**

Run: `pnpm --filter ui test && pnpm --filter ui lint`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/ui/src
git commit -m "feat(ui): add AppShell with grouped sidebar and phone tab bar"
```

---

### Task 7: Wire both apps to `ui` (build, Docker, fonts, logo)

**Files:**
- Modify: `apps/guest-web/package.json`, `apps/owner-web/package.json` (dependency)
- Modify: `apps/guest-web/next.config.ts`, `apps/owner-web/next.config.ts`
- Modify: `apps/guest-web/Dockerfile`, `apps/owner-web/Dockerfile`
- Replace: `apps/guest-web/src/app/globals.css`, `apps/owner-web/src/app/globals.css`
- Modify: `apps/guest-web/src/app/layout.tsx`, `apps/owner-web/src/app/layout.tsx`
- Replace: `apps/*/public/brand/logo-mark.svg`, `apps/*/src/app/icon.svg`
- Modify: `apps/guest-web/public/manifest.json`

- [ ] **Step 1: Add the dependency and remove the now-indirect Inter package**

Run: `pnpm --filter guest-web add ui@workspace:* && pnpm --filter owner-web add ui@workspace:* && pnpm --filter guest-web remove @fontsource-variable/inter && pnpm --filter owner-web remove @fontsource-variable/inter`
Expected: `Done`. (Skip a `remove` that reports the package is not a dependency.)

- [ ] **Step 2: Transpile the package in both Next configs**

In both `apps/guest-web/next.config.ts` and `apps/owner-web/next.config.ts`, add one line under `output: "standalone",`:

```ts
  transpilePackages: ["ui"],
```

- [ ] **Step 3: Copy the package manifest in both Dockerfiles**

In both `apps/guest-web/Dockerfile` and `apps/owner-web/Dockerfile`, after the line `COPY packages/api-client/package.json packages/api-client/package.json`, add:

```dockerfile
COPY packages/ui/package.json packages/ui/package.json
```

- [ ] **Step 4: Replace both `globals.css` files with the same two lines**

`apps/guest-web/src/app/globals.css` and `apps/owner-web/src/app/globals.css`:

```css
@import "tailwindcss";
@import "ui/theme.css";
```

- [ ] **Step 5: Update the root layouts**

`apps/owner-web/src/app/layout.tsx`, replace the `return (...)` of `RootLayout` with:

```tsx
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
```

`apps/guest-web/src/app/layout.tsx`: change `themeColor: "#070B10",` to `themeColor: "#F6F0E6",` and replace the `<html …>`/`<body …>` opening tags with:

```tsx
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
```

- [ ] **Step 6: Recolour the logo (one mark everywhere)**

Write this to `apps/guest-web/public/brand/logo-mark.svg`, `apps/owner-web/public/brand/logo-mark.svg`, `apps/guest-web/src/app/icon.svg` and `apps/owner-web/src/app/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="none">
  <circle cx="256" cy="256" r="210" stroke="#2B2118" stroke-width="22" stroke-dasharray="16 10" />
  <circle cx="256" cy="256" r="186" stroke="#2B2118" stroke-width="4" opacity="0.35" />
  <path d="M 256 22 L 256 50 M 256 462 L 256 490 M 22 256 L 50 256 M 462 256 L 490 256" stroke="#2B2118" stroke-width="10" stroke-linecap="round" />
  <rect x="156" y="280" width="36" height="84" rx="10" fill="#B5462B" opacity="0.55" />
  <rect x="238" y="230" width="36" height="134" rx="10" fill="#B5462B" opacity="0.8" />
  <rect x="320" y="180" width="36" height="184" rx="10" fill="#B5462B" />
  <path d="M 256 86 L 336 172 H 284 V 220 H 228 V 172 H 176 Z" fill="#B5462B" />
</svg>
```

Then delete the default Next.js favicons so browsers use the recoloured `icon.svg`:

Run: `git rm -q apps/guest-web/src/app/favicon.ico apps/owner-web/src/app/favicon.ico`

- [ ] **Step 7: Point the guest manifest at the logo and new colours**

`apps/guest-web/public/manifest.json`: set `"background_color": "#F6F0E6"`, `"theme_color": "#F6F0E6"`, and replace the `icons` array with:

```json
  "icons": [
    { "src": "/brand/logo-mark.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any" }
  ]
```

- [ ] **Step 8: Build both apps**

Run: `pnpm --filter guest-web build && pnpm --filter owner-web build`
Expected: both end with the route table and no errors. (Pages still use old colour classes; they render with the new base until Task 8.)

- [ ] **Step 9: Build the Docker images**

Run: `LLM_PROVIDER=mock DEMO_MODE=true docker compose build guest-web owner-web`
Expected: both images build.

- [ ] **Step 10: Commit**

```bash
git add apps/guest-web apps/owner-web pnpm-lock.yaml
git commit -m "feat(web): wire both apps to the shared ui theme, fonts and logo"
```

---

### Task 8: Migrate hard-coded colour classes to tokens

**Files:**
- Create (temporary): `scripts/retheme_classes.py`
- Modify: every `.tsx` under `apps/*/src` that the script reports

- [ ] **Step 1: Write `scripts/retheme_classes.py`**

```python
"""One-off: replace hard-coded colour classes with design-system tokens. Deleted after use."""

import re
import sys
from pathlib import Path

NN = r"(?:/\d+)?"  # optional opacity suffix

# Light theme (guest app, owner dashboard, login, landing). Order matters: specific first.
LIGHT = [
    (r"glass-panel", "mise-card"),
    (r"gradient-text", "text-terracotta"),
    (rf"text-\[#8FA3B3\]{NN}", "text-ink-muted"),
    (rf"text-\[#F3F8FC\]{NN}", "text-ink"),
    (rf"bg-\[#070B10\]{NN}", "bg-paper"),
    (r"via-\[#070B10\]", "via-paper"),
    (rf"bg-\[#0D141B\]{NN}", "bg-card"),
    (r"from-\[#0D141B\]", "from-card"),
    (r"to-\[#0D141B\]", "to-card"),
    (rf"bg-\[#38BDF8\]{NN}", "bg-paper-2"),
    (rf"(border|divide)-\[#38BDF8\]{NN}", r"\1-line"),
    (rf"text-\[#(?:22D3EE|2F7BFF)\]", "text-terracotta"),
    (rf"bg-\[#(?:22D3EE|2F7BFF)\]{NN}", "bg-terracotta/10"),
    (rf"(border|ring)-\[#(?:22D3EE|2F7BFF)\]{NN}", r"\1-terracotta"),
    (r"from-\[#2F7BFF\]", "from-terracotta"),
    (r"to-\[#22D3EE\]", "to-terracotta"),
    (r"text-\[#FF9F2E\]", "text-warn-fg"),
    (rf"bg-\[#FF9F2E\]{NN}", "bg-warn-bg"),
    (rf"border-\[#FF9F2E\]{NN}", "border-warn-fg/30"),
    (r"text-\[#EF4444\]", "text-danger-fg"),
    (r"bg-\[#EF4444\]/\d+", "bg-danger-bg"),
    (r"bg-\[#EF4444\]", "bg-danger-fg"),
    (rf"(border|ring)-\[#EF4444\]{NN}", r"\1-danger-fg"),
    (r"text-\[#34D399\]", "text-olive"),
    (r"bg-\[#34D399\]/\d+", "bg-safe-bg"),
    (r"bg-\[#34D399\]", "bg-olive"),
    (rf"border-\[#34D399\]{NN}", "border-olive"),
    (r"bg-\[#F59E0B\]", "bg-warn-fg"),
    (r"text-\[#070B10\]", "text-cream"),
    (r"bg-\[#F3F8FC\]", "bg-ink"),
    (r"text-zinc-(?:50|100|200)", "text-ink"),
    (r"text-zinc-(?:300|400|500|600|700)", "text-ink-muted"),
    (r"text-zinc-950", "text-cream"),
    (rf"bg-zinc-950{NN}", "bg-paper"),
    (rf"bg-zinc-900{NN}", "bg-card"),
    (rf"bg-zinc-(?:600|700|800){NN}", "bg-paper-2"),
    (rf"(border|divide)-zinc-\d+{NN}", r"\1-line"),
    (rf"bg-emerald-950{NN}", "bg-safe-bg"),
    (r"bg-emerald-400", "bg-olive"),
    (rf"bg-emerald-\d+{NN}", "bg-terracotta"),
    (r"text-emerald-\d+", "text-terracotta"),
    (rf"(border|ring)-emerald-\d+{NN}", r"\1-terracotta"),
    (rf"bg-(?:rose|red)-(?:900|950){NN}", "bg-danger-bg"),
    (rf"bg-(?:rose|red)-\d+{NN}", "bg-danger-fg"),
    (r"text-(?:rose|red)-\d+", "text-danger-fg"),
    (rf"border-(?:rose|red)-\d+{NN}", "border-danger-fg/40"),
    (rf"bg-amber-950{NN}", "bg-warn-bg"),
    (rf"bg-amber-\d+{NN}", "bg-warn-fg"),
    (r"text-amber-\d+", "text-warn-fg"),
    (rf"border-amber-\d+{NN}", "border-warn-fg/30"),
    (r"text-blue-\d+", "text-terracotta"),
    (rf"bg-blue-\d+{NN}", "bg-paper-2"),
    (r"border-blue-\d+", "border-terracotta"),
    (rf"shadow-(?:cyan|emerald|blue|sky)-\d+{NN}", "shadow-ink/10"),
    (rf"bg-black{NN}", "bg-ink/40"),
    (r"text-white", "text-cream"),
]

# Kitchen display (dark). Text on kds accents is espresso; fixed by hand in Task 12.
KDS = [
    (rf"bg-\[#070B10\]{NN}", "bg-espresso"),
    (rf"bg-\[#0D141B\]{NN}", "bg-kds-card"),
    (r"text-\[#F3F8FC\]", "text-cream"),
    (rf"text-\[#8FA3B3\]{NN}", "text-kds-muted"),
    (rf"(border|divide)-\[#38BDF8\]{NN}", r"\1-cream/10"),
    (r"text-\[#22D3EE\]", "text-kds-accent"),
    (r"text-\[#34D399\]", "text-kds-fresh"),
    (r"bg-\[#34D399\]/\d+", "bg-kds-fresh/20"),
    (rf"border(-l)?-\[#34D399\]{NN}", r"border\1-kds-fresh"),
    (r"text-\[#FF9F2E\]", "text-kds-warn"),
    (rf"bg-\[#FF9F2E\]{NN}", "bg-kds-warn/15"),
    (rf"border-\[#FF9F2E\]{NN}", "border-kds-warn"),
    (r"bg-\[#EF4444\]/\d+", "bg-kds-late/20"),
    (r"bg-\[#EF4444\]", "bg-kds-late"),
    (rf"(border(?:-l)?|ring)-\[#EF4444\]{NN}", r"\1-kds-late"),
    (r"bg-\[#F59E0B\]", "bg-kds-warn"),
    (r"border-l-\[#F59E0B\]", "border-l-kds-warn"),
    (r"text-\[#070B10\]", "text-espresso"),
    (rf"bg-black{NN}", "bg-espresso"),
    (r"text-white", "text-cream"),
    (r"text-black", "text-espresso"),
    (r"bg-white", "bg-cream"),
    (r"text-zinc-(?:100|200)", "text-cream"),
    (r"text-zinc-\d+", "text-kds-muted"),
    (rf"bg-zinc-\d+{NN}", "bg-kds-card"),
    (rf"border-zinc-\d+{NN}", "border-cream/10"),
    (rf"bg-emerald-950{NN}", "bg-kds-fresh/20"),
    (rf"bg-emerald-\d+{NN}", "bg-kds-fresh"),
    (r"text-emerald-\d+", "text-kds-fresh"),
    (rf"(border|ring)-emerald-\d+{NN}", r"\1-kds-fresh"),
    (rf"bg-(?:rose|red)-(?:900|950){NN}", "bg-kds-late/20"),
    (rf"bg-(?:rose|red)-\d+{NN}", "bg-kds-late"),
    (r"text-(?:rose|red)-\d+", "text-kds-late"),
    (rf"border-(?:rose|red)-\d+{NN}", "border-kds-late"),
    (rf"bg-amber-\d+{NN}", "bg-kds-warn"),
    (r"text-amber-\d+", "text-kds-warn"),
]

KITCHEN = {"apps/owner-web/src/app/(kitchen)/kitchen/page.tsx", "apps/owner-web/src/app/(kitchen)/layout.tsx"}
LEFTOVER = re.compile(
    r"\[#[0-9A-Fa-f]{6}\]|(?:zinc|emerald|rose|red|amber|blue|cyan|sky)-\d{2,3}"
    r"|glass-panel|gradient-text"
)


def apply(text: str, rules: list[tuple[str, str]]) -> str:
    for pattern, repl in rules:
        text = re.sub(rf"(?<![\w\[#-]){pattern}(?![\w\]-])", repl, text)
    return text


def main() -> int:
    leftovers = 0
    for path in sorted(Path("apps").glob("*/src/**/*.tsx")):
        rel = path.as_posix()
        old = path.read_text(encoding="utf-8")
        new = apply(old, KDS if rel in KITCHEN else LIGHT)
        if new != old:
            path.write_text(new, encoding="utf-8", newline="\n")
            print(f"updated {rel}")
        for n, line in enumerate(new.splitlines(), 1):
            for m in LEFTOVER.finditer(line):
                leftovers += 1
                print(f"LEFTOVER {rel}:{n}: {m.group(0)}")
    print(f"leftovers: {leftovers}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `python scripts/retheme_classes.py`
Expected: `updated …` lines for the 18 files listed in the spec's inventory, then `leftovers: N`.

- [ ] **Step 3: Resolve every leftover by hand**

For each `LEFTOVER path:line: match`, open the line and replace it with the nearest token from the tables in the script. Typical leftovers are gradient pairs (`from-… to-…`): replace the whole `bg-gradient-to-* from-* to-*` group with `bg-terracotta` (light) or `bg-kds-accent` (kitchen). Re-run the script until it prints `leftovers: 0`.

- [ ] **Step 4: Lint, unit tests and build**

Run: `pnpm -r lint && pnpm -r test && pnpm --filter guest-web build && pnpm --filter owner-web build`
Expected: all succeed.

- [ ] **Step 5: Rebuild the stack and run the browser tests**

Run: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web owner-web && make e2e`
Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add apps scripts/retheme_classes.py
git commit -m "refactor(web): replace hard-coded colours with design tokens"
```

---

### Task 9: Guest menu: dish row, category tabs, order bar and order sheet

**Files:**
- Modify: `apps/guest-web/src/components/allergen-chip.tsx`
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx` (imports, `formatPrice`, the `return (...)` from `// Top Bar` to the end)
- Modify: `apps/guest-web/src/i18n/en.ts`, `apps/guest-web/src/i18n/it.ts` (`checkout` label)
- Modify: `e2e/flows.spec.ts`

- [ ] **Step 1: Update the browser test first (it should fail)**

In `e2e/flows.spec.ts`, inside the guest test, replace the two lines

```ts
    await page.getByRole("button", { name: "Add" }).first().click();
    await page.getByRole("button", { name: /Review & Order/ }).click();
```

with

```ts
    await page.getByRole("button", { name: /^Add / }).first().click();
    const orderBar = page.getByRole("button", { name: /View order/ });
    await orderBar.click();

    // Order sheet is a native modal dialog: Esc closes it and focus returns to the bar.
    const sheet = page.getByRole("dialog", { name: "Your Order" });
    await expect(sheet).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(orderBar).toBeFocused();
    await orderBar.click();
```

Run: `make e2e`
Expected: the guest test FAILS (no button matching `/View order/`).

- [ ] **Step 2: Change the order-bar label**

`apps/guest-web/src/i18n/en.ts`: `checkout: "View order",`
`apps/guest-web/src/i18n/it.ts`: `checkout: "Vedi ordine",`

- [ ] **Step 3: Render `AllergenChip` through `StatusChip`**

Replace the body of `apps/guest-web/src/components/allergen-chip.tsx` with:

```tsx
"use client";

import React from "react";
import { StatusChip } from "ui";
import { getDictionary } from "../i18n";

export interface AllergenChipProps {
  status: "contains" | "unverified" | "no_declared_match" | string;
  matchedAllergens?: string[];
  locale?: string;
  className?: string;
}

export function AllergenChip({
  status,
  matchedAllergens = [],
  locale = "en",
  className = "",
}: AllergenChipProps) {
  const dict = getDictionary(locale);

  if (status === "contains") {
    const names = matchedAllergens.map((a) => (dict.allergens as Record<string, string>)[a] || a);
    const label = names.length
      ? `${dict.allergenStatus.contains}: ${names.join(", ")}`
      : dict.allergenStatus.contains;
    return (
      <StatusChip tone="contains" data-testid="allergen-chip-contains" className={className}>
        {label}
      </StatusChip>
    );
  }

  if (status === "unverified") {
    return (
      <StatusChip tone="unverified" data-testid="allergen-chip-unverified" className={className}>
        {dict.allergenStatus.unverified}
      </StatusChip>
    );
  }

  return (
    <StatusChip tone="safe" data-testid="allergen-chip-no-declared-match" className={className}>
      {dict.allergenStatus.no_declared_match}
    </StatusChip>
  );
}
```

Run: `pnpm --filter guest-web test`
Expected: the 4 existing `AllergenChip` tests still pass.

- [ ] **Step 4: Use the shared price formatter in the menu page**

In `apps/guest-web/src/app/[lang]/menu/page.tsx`:

Add to the imports:

```tsx
import { Badge, Button, Sheet, formatPrice as formatAmount } from "ui";
```

Change the React import to drop `useCallback` (it is no longer used):

```tsx
import React, { use, useEffect, useState } from "react";
```

Replace the whole `const formatPrice = useCallback(…);` block with:

```tsx
  const formatPrice = (amount: number) =>
    formatAmount(amount, menu?.restaurant?.currency || "EUR", lang);
```

- [ ] **Step 5: Replace the page's main `return (...)`**

Replace everything from `  return (\n    <div className="min-h-screen` (the final return, after the error branch) to the end of the component with:

```tsx
  const riskyNames = cart.items
    .filter((i) => i.allergenStatus !== "no_declared_match")
    .map((i) => i.name);
  const catId = (cat: string) => `cat-${cat.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="min-h-screen bg-paper pb-28 text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/95 px-4 pt-4 backdrop-blur sm:px-6">
        <div className="mx-auto max-w-3xl">
          {menu.table_label && (
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
              {dict.ui.table}: {menu.table_label}
            </p>
          )}
          <h1 className="text-2xl text-ink">{menu.restaurant.name}</h1>
          <nav aria-label={dict.ui.menuTitle} className="-mx-1 mt-3 flex gap-2 overflow-x-auto pb-3">
            {categories.map((cat) => (
              <a
                key={cat}
                href={`#${catId(cat)}`}
                className="whitespace-nowrap rounded-full border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:bg-paper-2"
              >
                {cat}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-8 px-4 py-4 sm:px-6">
        {categories.map((cat) => (
          <section key={cat} id={catId(cat)} className="scroll-mt-32">
            <h2 className="border-b border-line pb-1 text-lg font-semibold italic text-terracotta">
              {cat}
            </h2>
            <ul>
              {menu.items
                .filter((i) => i.category === cat)
                .map((item) => {
                  const isAvailable = item.available !== false;
                  return (
                    <li
                      key={item.id}
                      className={`border-b border-dotted border-line py-4 ${isAvailable ? "" : "opacity-50"}`}
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <h3 className="text-base font-semibold text-ink">{item.name}</h3>
                        <span className="whitespace-nowrap font-semibold tabular-nums text-ink">
                          {formatPrice(Number(item.price))}
                        </span>
                      </div>
                      {item.description && (
                        <p className="mt-0.5 text-sm text-ink-muted">{item.description}</p>
                      )}
                      <div className="mt-2 flex items-center justify-between gap-3">
                        <div className="flex flex-wrap gap-1.5">
                          <AllergenChip
                            status={item.allergen_status}
                            matchedAllergens={item.matched_allergens}
                            locale={lang}
                          />
                          {item.is_vegetarian && <Badge>{dict.dietary.vegetarian}</Badge>}
                          {item.is_vegan && <Badge>{dict.dietary.vegan}</Badge>}
                          {item.is_gluten_free && <Badge>{dict.dietary.gluten_free}</Badge>}
                        </div>
                        {isAvailable ? (
                          <Button
                            size="icon"
                            aria-label={`${dict.ui.addToCart} ${item.name}`}
                            onClick={() => handleAddToCart(item)}
                          >
                            +
                          </Button>
                        ) : (
                          <span className="text-xs italic text-ink-muted">{dict.ui.unavailable}</span>
                        )}
                      </div>
                    </li>
                  );
                })}
            </ul>
          </section>
        ))}
      </main>

      {cartCount > 0 && (
        <div className="fixed inset-x-4 bottom-4 z-20 mx-auto max-w-md">
          <Button className="w-full justify-between !py-3.5 text-base" onClick={() => setCartOpen(true)}>
            <span>
              {dict.ui.checkout} · {cartCount}
            </span>
            <span className="tabular-nums">{formatPrice(cartTotal)}</span>
          </Button>
        </div>
      )}

      <Sheet
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        title={dict.ui.cartTitle}
        footer={
          cart.items.length > 0 && (
            <>
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-ink-muted">{dict.ui.total}</span>
                <span className="text-lg font-semibold tabular-nums text-ink">
                  {formatPrice(cartTotal)}
                </span>
              </div>
              <Button
                className="w-full"
                onClick={handleCheckout}
                disabled={submittingOrder || (requiresAck && !cart.acknowledged)}
              >
                {submittingOrder ? dict.ui.placingOrder : dict.ui.placeOrder}
              </Button>
              <p className="text-[11px] leading-relaxed text-ink-muted">{dict.staffNotice}</p>
            </>
          )
        }
      >
        {orderError && (
          <div role="alert" className="rounded-xl bg-danger-bg p-3 text-xs text-danger-fg">
            {orderError}
          </div>
        )}

        {cart.items.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-muted">{dict.ui.emptyCart}</p>
        ) : (
          <ul className="divide-y divide-line">
            {cart.items.map((item, idx) => (
              <li key={`${item.menuItemId}-${idx}`} className="space-y-2 py-3">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">{item.name}</span>
                  <span className="font-semibold tabular-nums text-ink">
                    {formatPrice(item.price * item.quantity)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <AllergenChip
                    status={item.allergenStatus}
                    matchedAllergens={item.matchedAllergens}
                    locale={lang}
                  />
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={`− ${item.name}`}
                      onClick={() => handleUpdateQuantity(item.menuItemId, item.quantity - 1, item.notes)}
                    >
                      −
                    </Button>
                    <span className="w-5 text-center text-sm font-semibold tabular-nums">
                      {item.quantity}
                    </span>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={`+ ${item.name}`}
                      onClick={() => handleUpdateQuantity(item.menuItemId, item.quantity + 1, item.notes)}
                    >
                      +
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {cart.items.length > 0 && requiresAck && (
          <div className="space-y-2 rounded-xl bg-danger-bg p-3.5 text-danger-fg">
            <p className="text-sm font-semibold">⚠ {dict.ui.allergenWarningTitle}</p>
            <p className="text-xs">
              {dict.ui.allergenWarningDescription} <b>{riskyNames.join(", ")}</b>
            </p>
            <label className="flex cursor-pointer items-start gap-2 pt-1 text-xs text-ink">
              <input
                type="checkbox"
                checked={cart.acknowledged}
                onChange={(e) => handleAckChange(e.target.checked)}
                className="mt-0.5 accent-terracotta"
              />
              <span>{dict.ui.allergenAckCheckbox}</span>
            </label>
          </div>
        )}
      </Sheet>

      <ChatPanel locale={lang} />
    </div>
  );
}
```

- [ ] **Step 6: Lint, unit tests, build**

Run: `pnpm --filter guest-web lint && pnpm --filter guest-web test && pnpm --filter guest-web build`
Expected: no errors.

- [ ] **Step 7: Rebuild and run the browser tests**

Run: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web && make e2e`
Expected: `3 passed` (the guest test now covers Esc and focus return).

- [ ] **Step 8: Commit**

```bash
git add apps/guest-web e2e/flows.spec.ts
git commit -m "feat(guest): redesign menu with dish rows, category tabs and order sheet"
```

---

### Task 10: Guest welcome screen: one logo and a serif title

The order status, landing and login pages need no structural change: Task 8 moved them to tokens and the house classes carry the new look. Only the welcome screen still shows the old green "M" badge.

**Files:**
- Modify: `apps/guest-web/src/app/q/[token]/page.tsx` (imports; the badge and title around lines 94–98)

- [ ] **Step 1: Import `Image`**

Add to the imports at the top of `apps/guest-web/src/app/q/[token]/page.tsx`:

```tsx
import Image from "next/image";
```

- [ ] **Step 2: Replace the "M" badge and the title**

Replace the `<div …>` whose only content is the letter `M` (three lines, directly above the `<h1>` that renders `{dict.ui.welcomeTitle}`) and that `<h1 …>` opening tag with:

```tsx
          <Image src="/brand/logo-mark.svg" alt="Mise" width={56} height={56} priority />
          <h1 className="text-3xl text-ink">
```

(Keep `{dict.ui.welcomeTitle}` and the closing `</h1>` as they are.)

- [ ] **Step 3: Lint, build, browser tests**

Run: `pnpm --filter guest-web lint && pnpm --filter guest-web build && LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web && make e2e`
Expected: no errors; `3 passed`.

- [ ] **Step 4: Commit**

```bash
git add apps/guest-web
git commit -m "feat(guest): logo and serif title on the welcome screen"
```

---

### Task 11: Owner `AppShell` layout

**Files:**
- Replace: `apps/owner-web/src/app/(dashboard)/layout.tsx`

- [ ] **Step 1: Replace the dashboard layout**

`apps/owner-web/src/app/(dashboard)/layout.tsx`:

```tsx
"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AppShell, type NavGroup } from "ui";

const NAV: NavGroup[] = [
  {
    label: "Service",
    items: [
      { href: "/", label: "Live orders" },
      { href: "/kitchen", label: "Kitchen display ↗" },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/brief", label: "Revenue Brief" },
      { href: "/ai", label: "What-if" },
    ],
  },
  {
    label: "Menu",
    items: [
      { href: "/menu", label: "Menu & allergens" },
      { href: "/menu/ingest", label: "Import from photo" },
    ],
  },
  { label: "Setup", items: [{ href: "/tables", label: "Tables & QR" }] },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    fetch("/api/auth/config")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDemoMode(Boolean(d?.demo_mode)))
      .catch(() => setDemoMode(false));
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.push("/login");
    }
  };

  return (
    <AppShell
      groups={NAV}
      currentPath={pathname}
      linkAs={Link}
      banner={
        demoMode && (
          <div className="border-b border-warn-fg/30 bg-warn-bg px-4 py-1.5 text-center text-xs font-semibold text-warn-fg">
            Demo environment: synthetic data
          </div>
        )
      }
      brand={
        <Link href="/" className="flex items-center gap-3 px-2">
          <Image src="/brand/logo-mark.svg" alt="" width={32} height={32} priority />
          <span>
            <span className="block font-serif text-lg font-bold leading-tight">Mise</span>
            <span className="block text-xs text-ink-muted">Trattoria da Mario</span>
          </span>
        </Link>
      }
      sidebarFooter={
        <button onClick={handleLogout} className="btn-ghost mt-4 w-full">
          Sign out
        </button>
      }
    >
      {children}
    </AppShell>
  );
}
```


- [ ] **Step 2: Lint, build, browser tests**

Run: `pnpm --filter owner-web lint && pnpm --filter owner-web build && LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait owner-web && make e2e`
Expected: no errors; `3 passed`.

- [ ] **Step 3: Commit**

```bash
git add apps/owner-web
git commit -m "feat(owner): grouped sidebar layout"
```

---

### Task 12: Owner brief chart colours and kitchen display

**Files:**
- Modify: `apps/owner-web/src/lib/analytics.ts` (`CLASS_COLORS`)
- Modify: `apps/owner-web/src/app/(dashboard)/brief/page.tsx` (SVG colours)
- Modify: `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx`

- [ ] **Step 1: Quadrant colours from the palette**

`apps/owner-web/src/lib/analytics.ts`, replace `CLASS_COLORS` with:

```ts
export const CLASS_COLORS: Record<MenuClass, string> = {
  star: "#4A5D3A",
  plowhorse: "#8C7A64",
  puzzle: "#B5462B",
  dog: "#8A1C12",
};
```

In `apps/owner-web/src/app/(dashboard)/brief/page.tsx`, inside `Quadrant`: `fill="#070B10"` → `fill="#F6F0E6"`, and every `stroke="#8FA3B3"` / `fill="#8FA3B3"` → `"#6B5A48"`.

- [ ] **Step 2: Kitchen accents need espresso text**

In `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx` (already on kitchen tokens after Task 8), set these exact class strings:

The age badge block:

```tsx
            let ageBorder = "border-l-8 border-l-kds-fresh";
            let ageBadge = "bg-kds-fresh text-espresso";
            if (elapsedMinutes >= 20) {
              ageBorder = "border-l-8 border-l-kds-late ring-1 ring-kds-late/40";
              ageBadge = "bg-kds-late text-espresso font-black animate-pulse";
            } else if (elapsedMinutes >= 10) {
              ageBorder = "border-l-8 border-l-kds-warn";
              ageBadge = "bg-kds-warn text-espresso font-black";
            }
```

The ticket container: `className={`rounded-2xl bg-kds-card border border-cream/10 p-5 flex flex-col justify-between space-y-4 shadow-2xl transition-all ${ageBorder}`}`.

Both allergy banners (the guest-allergies banner and the per-item "ALLERGY WARNING" banner): background `bg-kds-late`, text `text-espresso` (replace `text-cream` in those two elements).

The bump button:

```tsx
                  <button
                    onClick={() => handleBump(order.id)}
                    className="w-full min-h-[48px] rounded-xl bg-kds-accent py-3.5 text-lg font-black uppercase tracking-wider text-espresso shadow-xl transition-all hover:opacity-90 active:scale-95"
                  >
                    BUMP
                  </button>
```

The recall button: `bg-kds-warn text-espresso` (drop any `hover:bg-*`). The header title "KITCHEN": `font-serif text-kds-fresh`.

- [ ] **Step 3: Lint, build, browser tests**

Run: `pnpm --filter owner-web lint && pnpm --filter owner-web test && pnpm --filter owner-web build && LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait owner-web && make e2e`
Expected: no errors; owner-web tests pass; `3 passed`.

- [ ] **Step 4: Commit**

```bash
git add apps/owner-web
git commit -m "feat(owner): palette for the brief chart and espresso kitchen display"
```

---

### Task 13: Screenshots for review, clean-up and full verification

**Files:**
- Modify: `e2e/flows.spec.ts`
- Delete: `scripts/retheme_classes.py`

- [ ] **Step 1: Save review screenshots in the browser tests**

In `e2e/flows.spec.ts`:

In the guest test, right after `await expect(page.getByText(`Table: ${info.table_label}`)).toBeVisible();` add:

```ts
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({ path: "test-results/screens/guest-menu-phone.png", fullPage: true });
```

and right after the second `await orderBar.click();` add:

```ts
    await page.screenshot({ path: "test-results/screens/order-sheet-phone.png" });
```

In the kitchen test, before `await bump.click();` add:

```ts
    await page.screenshot({ path: "test-results/screens/kitchen-desktop.png", fullPage: true });
```

In the owner test, after the `7-day demand forecast` assertion add:

```ts
    await page.screenshot({ path: "test-results/screens/owner-brief-desktop.png", fullPage: true });
```

- [ ] **Step 2: Delete the one-off script and confirm no old colours remain**

Run: `git rm -q scripts/retheme_classes.py && grep -rnE "\[#[0-9A-Fa-f]{6}\]|(zinc|emerald|rose|amber)-[0-9]{2,3}|glass-panel|gradient-text" apps/*/src --include=*.tsx`
Expected: no output (grep exit code 1).

- [ ] **Step 3: Run the browser tests and look at the screenshots**

Run: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web owner-web && make e2e`
Expected: `3 passed`; four PNGs in `test-results/screens/`. Open each and compare against the approved mockups in `.superpowers/brainstorm/*/content/screens.html` and `price-row.html`. Fix any visual mismatch before continuing.

- [ ] **Step 4: Full verification**

Run: `LLM_PROVIDER=mock DEMO_MODE=true make verify-f`
Expected: every step `PASS`, ending with `PASS verify-f: all steps`.

- [ ] **Step 5: Update the README screenshots note**

In `README.md`, under `## Screenshots`, replace the HTML comment `<!-- Add your application screenshots here -->` with:

```markdown
Screenshots are produced by `make e2e` in `test-results/screens/` (guest menu and order sheet on a phone, owner brief and kitchen display on desktop).
```

- [ ] **Step 6: Commit**

```bash
git add e2e/flows.spec.ts README.md
git commit -m "test(e2e): save review screenshots; remove the one-off retheme script"
```
