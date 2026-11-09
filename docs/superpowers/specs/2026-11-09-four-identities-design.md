# Four identities

Date: 2026-11-09. Status: approved in conversation, awaiting written review.
Spec 3B of 3 (1: safer table ordering, 2: money goes global, 3A: dish choices, 3B: this).

## Why

Mise has to show that one system runs several very different restaurants. Today every guest sees
the same cream-and-maroon Mise app, "Welcome to Mise" and "Ask Mise Assistant", whichever venue
they are in. After 3B a visitor who opens the four venues should believe they are four separate
apps, each with its own brand and design system, while one tested ordering, allergen, bill and
payment system runs underneath.

Success test: four venues, each with its own logo, colours, fonts, shapes, welcome animation and
loader, and no trace of another venue or of Mise on any guest screen.

## Decisions

1. **One guest app, one brand package per venue.** Not brands as database rows (cannot carry a
   per-venue animation or motif) and not four separate apps (four builds, every ordering fix
   copied four times).
2. **Guest-facing only.** The guest app, welcome animation, loader, sample bill and QR table card
   take the venue's brand. The owner app, kitchen screen and bills screen stay Mise-branded and
   only name the selected venue. Kitchen screens and tickets stay monochrome and high-contrast.
3. **All four venues.** Angeethi House (Lahore) and Kehwa & Crumb (Islamabad) exist. Noor &
   Za'atar (Dubai) and Tikka Town (Manchester) are created here.
4. **Animations are live SVG driven by GSAP, never video.** Welcome once per visit, a short loader
   after that.
5. **Dish photos for featured dishes only**, 6 to 8 per venue, freely licensed, with a recorded
   source per photo.
6. **The five issues from the 2026-11-08 screenshot review are fixed first.**
7. **Out of scope:** owner, kitchen and bills screen branding; Arabic (project languages are `en`
   and `it`); owners editing their own brand; photos for non-featured dishes; photo upload; the
   showcase video (deferred, see the end).

## Phases

Each phase gets its own implementation plan and is built and reviewed on its own.

| Phase | Content | Depends on |
|---|---|---|
| 0 | Screenshot-review fixes | — |
| 1 | Brand system, Angeethi House and Kehwa & Crumb packages | 0 |
| 2 | Noor & Za'atar and Tikka Town: data, menus, demo history, packages | 1 |
| 3 | Featured dish photos | 2 |

## Phase 0 · Screenshot-review fixes

One commit each.

1. **Kitchen order count.** `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx` prints
   "1 ORDERS ACTIVE". Use singular for one ("1 ORDER ACTIVE"), plural otherwise. The existing
   check in `e2e/self-service.spec.ts` for "0 ORDERS ACTIVE" stays valid; add a check for the
   singular case. The "1 kg" line wrap on the same screen is fixed with a non-breaking space
   between quantity and unit.
2. **Brief summary numbers.** `services/api/src/services/brief.py` writes raw decimals and mixes
   the currency code with the symbol used elsewhere. Format every amount with the venue's
   currency formatting (grouped, two decimals at most, same symbol as the rest of the owner app)
   and round the margin percentage to one decimal. The model still never produces the numbers.
3. **Mock text in the Service report.** `services/inference/mock/src/canned.py` returns a generic
   "pasta specials" line that appears on Pakistani venues. Replace it with venue-neutral wording
   that names no dish.
4. **Raw order id shown to guests.** The guest order page shows the full order UUID. Show a short
   order reference instead (the first 6 characters, upper case, prefixed "#"). The full id stays in
   the URL and the API.
5. **Floating assistant covering a price.** The menu list leaves room at the bottom so the
   floating assistant button never covers the last dish's price. (Replacing "Mise" in the guest
   welcome and assistant titles is done in phase 1.)

## Phase 1 · The brand system

### Brand packages

Each venue has a folder `apps/guest-web/src/brands/<slug>/`:

| File | Holds |
|---|---|
| `tokens.ts` | Colour ramp (OKLCH), surface, ink, accent, button shape, corner radius |
| `fonts.ts` | One display font and one text font, free licence, loaded with `next/font` |
| `assets/` | Finished logo lockup and logo mark SVGs, built from the round-1 logos in `docs/brand/round-1/` |
| `Motif.tsx` | Header and order-bar motif (coals, crumbs, lantern, skewer) |
| `Welcome.tsx` | Arrival animation |
| `Loader.tsx` | Short loading animation |

`apps/guest-web/src/brands/index.ts` maps each slug to a lazy import of its package. A brand
folder imports only from its own folder, `gsap`, `@gsap/react` and the shared brand types; never
from another brand.

### How the shared screens take a brand

- The guest menu response gains `restaurant.slug`. The guest pages load that venue's package from
  the registry and set its tokens as CSS variables (`--brand-*`) on the page root.
- The shared screens (menu, dish sheet, cart bar, pay sheet, order status, chat panel) read only
  `--brand-*` variables and render the package's `Motif`. They contain no venue names, colours or
  per-venue conditions.
- **Fixed styles brands cannot change:** prices, allergen chips, the checkout total, payment
  method details and order status keep the styles in `packages/ui` and the 3A house classes. A
  brand may tint the surface around them, never their own colours or type.
- Page title, `themeColor` and icon come from the venue package. `welcomeTitle` and `chatTitle`
  in `apps/guest-web/src/i18n/{en,it}.ts` take the venue name as a parameter instead of "Mise".
- The sample bill and the QR table card use the venue's logo, colours and fonts. The sample bill
  keeps its disclaimer and never carries a fiscal number, QR code, authority logo or the words
  "invoice", "FBR integrated" or "compliant".

### Identities

Final colour values are chosen from the user's shared palette set and must pass the contrast test.
The table sets direction.

| Venue | Feel | Shapes | Welcome (about 2 s) | Loader |
|---|---|---|---|---|
| Angeethi House, Lahore | Coal grill; deep maroon, ember orange | Square buttons, heavy display type | Coals glow under the Urdu wordmark, then the name rises | Three embers pulse in turn |
| Kehwa & Crumb, Islamabad | Calm tea room; green tea, warm crumb | Pill buttons, light type | A cup fills with kehwa, crumbs settle into the logo | Crumbs fall and gather |
| Noor & Za'atar, Dubai | Evening light; deep indigo, saffron gold | Arches from the logo | A lantern pattern draws itself and lights up | A lantern flickers |
| Tikka Town, Manchester | Loud Northern sign-painting; brick red, mustard | Bold condensed type, ticket-stub edges | A skewer slides across and stamps the logo like a shop sign | A skewer turns |

Design rules: no cream + serif + terracotta default, no Fraunces, no hard sticker shadows; logos
are vectors built from real letterforms and from what only that venue has.

### Animations

- Built with SVG, `gsap` and `@gsap/react` (`useGSAP`, so timelines stop on unmount). These are the
  only new dependencies in 3B; GSAP and its plugins are free under GSAP's standard licence.
- GSAP loads only inside each package's `Welcome` and `Loader`, so it is absent from every page
  that is not a venue page.
- **Welcome:** plays once per visit, on the first guest page after a QR scan (tracked in
  `sessionStorage` per table sitting; when storage is unavailable it plays once per page load).
  Tap anywhere to skip. The menu loads underneath, so the welcome never delays ordering. Hard
  limit 3 seconds, then it always closes.
- **Loader:** shown while a page loads or an order is sent, at most once per wait.
- **Reduced motion:** with `prefers-reduced-motion: reduce`, both show the still logo
  (`gsap.matchMedia()`).

### Failures

- Brand package or font fails to load: the page renders with a neutral fallback brand (venue name
  in system fonts, neutral ramp). Ordering never depends on the brand.
- Unknown slug: the existing not-found page, with no venue brand.
- Welcome throws: it is skipped and the menu shows.

## Phase 2 · Noor & Za'atar and Tikka Town

### Data

| | Noor & Za'atar | Tikka Town |
|---|---|---|
| Seed file | `data/seed/noor_and_zaatar.json` | `data/seed/tikka_town.json` |
| Slug | `noor-and-zaatar` | `tikka-town` |
| City | Dubai | Manchester |
| Currency | AED | GBP |
| Tax jurisdiction | `AE-DU` (5% VAT, prices include tax) | `GB` (20% VAT, prices include tax) |
| Service charge | none | optional 10%, outside tax (`GB` already has `service_charge: optional_outside_tax`; the venue's `service_charge_rate` is 0.10) |
| Payment methods | those listed for `AE-DU` | those listed for `GB` |
| Tables | 10 | 12 |
| Dishes | about 24 | about 28 |

No new tax code: both jurisdictions already exist with sourced rates. Demo owners and staff for
both venues are added to `data/seed/demo_users.json`. Each venue gets 90 days of synthetic order
history in its own currency, so the dashboard, Brief and forecasts work from the start. The owner
app's venue picker lists all four venues.

### Menus

Every dish carries the 14-allergen data and dish choices (3A) where they make sense.

**Noor & Za'atar** (Emirati home cooking first, then the Levantine and Pakistani dishes Dubai
expects): chicken machboos, lamb machboos, harees, thareed, balaleet, luqaimat with date syrup,
karak chai, hummus, moutabal, za'atar manakish, cheese manakish, mixed grill, shish tawook, mutton
biryani, fresh lime-mint, plus further grills, mezze and drinks to about 24.

**Tikka Town** (Curry Mile classics plus British and Mancunian dishes): lamb chops, seekh kebab,
chicken tikka, karahi, balti, nihari, keema naan, samosa chaat, chicken tikka masala, masala fish
and chips, chicken tikka pie with minted peas, spiced Lancashire hotpot, chips and curry sauce,
cheesy chips masala, Bombay potatoes, Sunday roast with masala gravy and Yorkshire pudding,
Manchester tart, Eccles cake with Lancashire cheese, sticky toffee pudding, gulab jamun, mango
lassi, masala chai, plus breads and drinks to about 28.

### Brand packages

Noor & Za'atar and Tikka Town packages follow phase 1, from their round-1 logos.

## Phase 3 · Featured dish photos

- 6 to 8 signature dishes per venue (about 30 photos) are marked featured. A new boolean
  `menu_items.featured` (Alembic migration, default false) is set from the seed files and returned
  in the guest menu response.
- Featured dishes appear in a "House favourites" strip at the top of the menu and with their photo
  in the dish sheet (which already renders `image_url`). Other dishes stay text-only.
- Photos are stored in the repo as small WebP files under
  `apps/guest-web/public/venues/<slug>/dishes/`, loaded lazily, and referenced by `image_url`.
- **Every photo must show the dish it is attached to.** A dish without an accurate free photo is
  not featured; another signature dish is chosen.
- Free licences only (Unsplash, Pexels or similar). No AI-generated photos. Each photo's source
  URL, author and licence is recorded in `data/photo_credits.json`, keyed by file path; a test
  fails if a photo in `public/venues/` has no credit entry.

## Tests

- **Isolation:** no file in `brands/<a>/` imports from `brands/<b>/`; the rendered menu for each
  venue contains no other venue's name, logo file or font, and no "Mise".
- **Contrast:** every brand's text and background pairs pass WCAG 2 AA (4.5:1 body text, 3:1 large
  text and UI parts).
- **Fixed styles:** price, allergen chip and checkout total render with the same classes under all
  four brands.
- **Welcome:** plays once per visit, skips on tap, closes by 3 s, shows the still logo under
  reduced motion.
- **New venues:** API tests settle a bill in AED and in GBP; the Tikka Town bill shows the service
  charge on its own line outside tax; settling refuses a method the jurisdiction does not list.
- **Browser (e2e):** a full order at each new venue; one screenshot per venue of welcome, menu and
  sample bill.
- **Photos:** every featured dish has an `image_url` that exists and a credit entry.
- `make ci` and `make verify-f` pass on a fresh stack.

## Deferred

- **Showcase video** (Remotion, rendered locally): on hold until the next features are built,
  since new features are the main goal. Not part of 3B.
