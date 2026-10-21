# Mise design system and redesign: design spec

Date: 2026-10-20. Status: approved in brainstorming, pending spec review.
Branch: `feat/design-system`, based on `fix/guest-flow-contract` (PR #2) for its Playwright tests.

## Goal

Replace the generic dark-navy look with one distinctive, consistent design across the guest
app, the owner dashboard and the kitchen display, built once in a shared package so the apps
cannot drift apart again. Visual change only: no API, data or behavior changes.

## Problems today

- Two copies of the same 196-line `globals.css`; 212 `className` uses with hard-coded hex
  colors (for example `text-[#8FA3B3]`); no shared components.
- Inconsistent branding: green "M" badge on the guest welcome, blue compass logo elsewhere.
- Owner navigation: nine links crammed into one top row.
- Guest menu: the price sits directly on top of the Add button; the small serif price reads
  as decoration.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Visual direction | A, "Trattoria editorial": warm paper, serif headings, terracotta accent |
| Owner layout | Left sidebar grouped by job; bottom tab bar on phones |
| Build approach | One shared package `packages/ui`; interactive parts on the native `<dialog>` element, no component library |
| Dish row | Price on the dish-name line (Inter, tabular figures); round "+" add button on the allergen line |

## Foundations

### Colour tokens

| Token | Value | Use | Contrast |
|---|---|---|---|
| `paper` | `#F6F0E6` | page background | — |
| `paper-2` | `#EFE6D7` | sidebar, sunken areas | — |
| `card` | `#FBF7F0` | surfaces | — |
| `ink` | `#2B2118` | text | 13.9:1 on paper |
| `ink-muted` | `#6B5A48` | secondary text | 5.8:1 on paper, 5.3:1 on paper-2 |
| `terracotta` | `#B5462B` | primary actions, accents | 4.8:1 on paper; cream `#FFF8EF` on it 5.1:1 |
| `olive` | `#4A5D3A` | positive, safe | — |
| `espresso` | `#17120D` | kitchen display background | cream text 16.4:1 |
| `kds-card` | `#221B14` | kitchen ticket | muted `#BBAA94` 7.5:1 |
| `kds-accent` | `#E2673F` | kitchen bump button | 5.5:1 on espresso |

Allergen status (always colour + icon + word, never colour alone):

| Status | Background | Text | Label | Contrast |
|---|---|---|---|---|
| contains | `#F7DCD6` | `#8A1C12` | "⚠ Contains {allergen}" | 7.2:1 |
| unverified | `#F5E6C4` | `#7A4E08` | "? Not yet verified" | 5.8:1 |
| no_declared_match | `#E3EAD5` | `#3B4D2C` | "✓ No declared match" | 7.4:1 |

Every text/background pair used meets WCAG AA (4.5:1).

### Type

- Fraunces (variable, self-hosted via `@fontsource-variable/fraunces`): headings, dish names,
  category labels (italic, terracotta), large KPI figures.
- Inter (variable, already self-hosted via `@fontsource-variable/inter`): all body text,
  forms, tables, buttons and **all prices**, with `font-variant-numeric: tabular-nums`.
- Rule: serif never below 15px; prices and table numbers are never serif.

### Components (`packages/ui`)

| Component | Purpose |
|---|---|
| `Button` | variants `primary` (terracotta), `outline`, `dark`; sizes `md`, `icon` (round "+", min 32×32 with an `aria-label`) |
| `Card` | surface with border and radius |
| `StatTile` | label, big serif figure, optional sub-line |
| `PageHeader` | title, subtitle, optional actions slot |
| `Badge` | neutral pill (dietary tags, "Template summary", etc.) |
| `AllergenChip` | moved from guest-web with its tests; uses the status table above |
| `AppShell` | owner sidebar grouped Service / Insights / Menu / Setup; bottom tab bar under 768px |
| `Sheet` | bottom sheet on native `<dialog>`: focus trapped, Esc closes, focus returns to the opener |
| `Dialog` | centred modal on native `<dialog>`, same behaviour |
| `formatPrice` | `Intl.NumberFormat` currency helper shared by both apps |

## Screens

- **Guest welcome (`/q/[token]`)**: compass logo replaces the green "M"; language, dietary and
  allergen pickers in Cards; the safety notice lives here.
- **Guest menu (`/[lang]/menu`)**: restaurant name in serif and table label; category tabs
  that stay pinned while scrolling; dish rows per the decision above; one terracotta bottom bar
  "View order · N · €total".
- **Order sheet**: `Sheet` with line items, the allergen check naming the exact dish and
  allergen, confirm blocked until acknowledged (the server rule is unchanged), safety notice.
- **Order status (`/[lang]/orders/[id]`)**: status steps (received, prepared) in the same
  language.
- **Guest landing (`/`)**: existing content restyled; compass logo panel stays.
- **Owner login**: centred Card on paper with the demo buttons.
- **Owner pages in `AppShell`**: Live orders, Revenue brief, What-if, Menu & allergens, Import
  from photo, Tables & QR. The brief uses StatTiles, a ranked-actions panel, the
  menu-engineering quadrant (SVG recoloured to tokens), the forecast table and backtest badge,
  and the simulated-data badge always visible in the header.
- **Kitchen display**: espresso theme, large type, solid red guest-allergy banner on the
  ticket, age colours unchanged (green under 10 min, amber from 10, red from 20).
- **Logo**: one compass mark recoloured to ink and terracotta; app icons and favicons updated.

## Architecture

- `packages/ui/package.json`: name `ui`, `exports` for `./theme.css` and the component entry,
  peer dependency on `react`.
- `packages/ui/src/theme.css`: Tailwind v4 `@theme` block with the tokens above, font-face
  imports, base styles (body background and colour, focus ring).
- Each app's `globals.css` becomes `@import "tailwindcss"; @import "ui/theme.css";` plus an
  `@source` line for `packages/ui/src` so Tailwind generates classes used in the package.
- Both `next.config.ts` files add `transpilePackages: ["ui"]`.
- Both Dockerfiles add `COPY packages/ui/package.json packages/ui/package.json` before
  `pnpm install` (they copy each manifest explicitly).
- Migration replaces hard-coded hex classes with token classes; the old custom classes
  (`glass-panel`, `gradient-text`, `mise-card`, `btn-*`, `chip-*`, `stat-tile`) are deleted
  once unused.

## Testing

- Playwright flows (`e2e/flows.spec.ts`) must pass after each screen group; selectors updated
  for changed labels (for example the add button is found by its "Add {dish}" label).
- The Playwright run also saves phone (375×812) and desktop screenshots of the guest menu,
  order sheet, owner brief and kitchen display under `test-results/` for review by eye. No
  pixel comparison.
- Vitest in `packages/ui`: `AllergenChip` (existing tests moved), `Sheet` and `Dialog` (open,
  Esc closes, focus returns), `formatPrice`.
- `make ci` and `make verify-f` must pass; `pnpm -r lint` includes the new package.

## Delivery

One PR, in three commit groups:
1. `packages/ui` with tokens, fonts, components, tests and the build and Docker wiring.
2. guest-web: welcome, menu, order sheet, order status, landing.
3. owner-web: AppShell, all owner pages, login, kitchen display; delete the old CSS.

## Out of scope

- Dark mode for guest and owner apps (only the kitchen display is dark).
- New features, API or copy changes beyond labels needed by the new layout.
- Dish photography (no images exist; dishes stay text-only).
- Replacing the removed cover images.
