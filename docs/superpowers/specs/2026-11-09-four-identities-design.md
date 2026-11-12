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
7. **Out of scope:** owner, kitchen and bills screen branding and translation; owners editing their
   own brand; photos for non-featured dishes; photo upload; the showcase video (deferred, see the
   end).
8. **Local languages (decided 2026-11-12):** Italian is removed. Each venue offers English plus
   its local language: Urdu for the Pakistani venues, Arabic for Dubai, English only for
   Manchester. See phase 1b.

## Phases

Each phase gets its own implementation plan and is built and reviewed on its own.

| Phase | Content | Depends on |
|---|---|---|
| 0 | Screenshot-review fixes | — |
| 1 | Brand system, Angeethi House and Kehwa & Crumb packages | 0 |
| 1b | Local languages: Urdu, right-to-left layout, Italian removed | 1 |
| 2 | Noor & Za'atar and Tikka Town: data, menus, demo history, packages, Arabic menu | 1b |
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

### One venue per guest

A guest sees only the venue whose QR code they scanned, from the scan to the end of the visit:
no other venue's name, logo, menu or link, no venue list or picker, and no "Mise" name or logo.

- **Scan page** (`/q/[token]`): today it shows the Mise logo. It shows a neutral, nameless
  loading state until the token resolves, then the venue's brand. A bad or expired token shows a
  neutral "Scan the QR code on your table again" message with no venue or Mise name.
- **Expired guest session:** the menu page now redirects to `/` on a 401. `/` is the demo
  landing page and lists all four venues. It redirects to the same neutral "scan again" message
  instead. No guest page links to `/`.
- **Installed-app details:** `public/manifest.json` ("Mise - Guest Dining") is replaced by a
  manifest per venue (name, colours, icon), served for venue pages only. The page title,
  `themeColor` and icon are the venue's.
- **Not-found page:** neutral, with no venue or Mise name.
- **Assistant:** it already answers from the session's own venue (`guest_chat` scopes by
  `session.restaurant_id`); its title is the venue's name.
- **API:** every guest endpoint already scopes by the session's venue. A test confirms a guest
  session at one venue gets 404 or nothing for another venue's menu, bill and service calls.
- **Demo landing (`/`)** stays as the Mise-branded presenter page that lists the demo venues. No
  QR code or guest flow leads to it.

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

## Phase 1b · Local languages

Research: `docs/research/2026-10-22-pakistan-notes/urdu_ui.md` (fonts, digits, right-to-left,
translation quality). This phase adds Urdu and the right-to-left layout; Arabic arrives with the
Dubai venue in phase 2 and reuses all of it.

### Languages per venue

| Venue | `restaurant.languages` | Default |
|---|---|---|
| Angeethi House | `en`, `ur` | `en` |
| Kehwa & Crumb | `en`, `ur` | `en` |
| Noor & Za'atar (phase 2) | `en`, `ar` | `en` |
| Tikka Town (phase 2) | `en` | `en` |

- **Italian is removed everywhere:** the guest dictionary, the `it` route, the API's allowed
  languages and the owner app's menu-import language list. No venue offers it.
- **A venue offers only its own languages.** The guest venue response (QR lookup and session)
  carries the venue's `languages`. The scan page shows a button per language, in that language's
  own name ("English", "اردو", "العربية"); with one language it shows no picker.
- **The API refuses a language the venue does not offer** when a guest session is created or
  changed (422, a short reason). Allowed codes: `en`, `ur`, `ar`.
- **Guest routes** are `/en/…`, `/ur/…` and `/ar/…`. Any other language segment is the neutral
  not-found page. A guest on a language their venue doesn't offer is sent to the venue's default.

### Right-to-left

- For `ur` and `ar` the guest page root has `lang` and `dir="rtl"`, set on the server in
  `[lang]/layout.tsx`, so the first paint is already in the right direction. Native sheets
  (`<dialog>`) are inside the root and follow it.
- Guest screens use direction-neutral layout (`ms-`/`me-`/`ps-`/`pe-`/`start-`/`end-`,
  `text-start`/`text-end`) instead of left/right, so one set of classes works both ways. Arrows and
  chevrons mirror; the plus, minus, check, allergen and clock icons do not.
- **Money and numbers stay left-to-right in Latin digits** (`Rs 1,250`, table and order numbers,
  quantities), each isolated (`<bdi>`, or `dir="ltr"` with isolation on `.figure`) so they never
  jump inside Urdu text. Prices use the same formatter as English.
- The bottom stack (assistant, order bar, View order) and the sheets keep working at 320 px in both
  directions.

### Fonts

- Urdu and Arabic text use **Noto Naskh Arabic** (free, OFL), weights 400 and 700, loaded with
  `next/font` only on `ur` and `ar` pages. Naskh, not Nastaliq: it is about a third of the size and
  avoids the clipping and spacing problems the research found. Line height about 1.7 for Urdu and
  Arabic text.
- The venue's own fonts stay for Latin text (logo band, prices, English words). The venue logo is
  the same in every language.

### Words

- **Guest screens:** a complete Urdu dictionary (`ur.ts`) replaces `it.ts`; every key present,
  checked by a test. Polite register (آپ). Common loanwords stay as customers say them (آرڈر,
  مینو, بل, ٹیبل).
- **Menus:** every dish, size and choice in both Pakistani venues gets an Urdu name and
  description in the seed data. Dish names are written as customers say them (چکن کڑاہی, not a
  word-for-word translation). The 14 allergen names and the diet labels are in the dictionary.
- **Allergen and safety text** (the notice, the warnings, "contains", the order acknowledgement)
  is marked as a draft translation in the dictionary and in the README until a native speaker
  has checked it. It is written by hand, never machine-generated, and the allergen status itself
  stays server code in every language.
- **Ingredient tags** stay as the menu data writes them (English) in this phase; translating
  ingredient names is a later data task.
- **The assistant** keeps answering in English; its title, placeholder and buttons are translated.
- The owner app, kitchen screen, tickets and bills screen stay English. The printed QR card and
  sample bill stay English except for the venue's logo.

### Tests

- Unit: the Urdu dictionary has every English key, no empty values and no "Mise"; the scan page
  shows only the venue's languages and hides the picker for one language; the API refuses `it`
  and refuses `ur` at a venue without it; money stays Latin-digit and isolated in an Urdu sentence.
- End-to-end: at Angeethi House, choosing اردو gives an Urdu, right-to-left menu (`dir="rtl"`, an
  Urdu dish name, `Rs` prices in Latin digits), an order can be placed and paid in Urdu, and at
  320 px the assistant never covers a dish. The one-venue test also walks the Urdu pages. A
  language a venue doesn't offer (`/ar/menu` at Angeethi) falls back to its default.

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

Every dish carries the 14-allergen data and dish choices (3A) where they make sense. Noor &
Za'atar's menu is written in English and Arabic from the start, and an Arabic guest dictionary
(`ar.ts`) is added on the phase 1b pattern (same draft-translation rule for safety text).

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
- **One venue per guest (e2e):** scan venue A and walk every guest page (scan, welcome, menu,
  dish sheet, chat, order status, pay, sample bill, expired session, not found); the page text,
  title, manifest and image sources never contain another venue's name or "Mise". Run for all
  four venues.
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
