# Venue brands, guest UX and table-order security

Research date: 2026-10-30. Sources are linked inline. "Uncertain" marks claims that rest on a
single secondary source, on vendor marketing, or that I could not confirm on an official page.
Nothing here describes Mise features; it is input for decisions.

---

## 1. Stopping fake or remote QR table orders

### The problem

A static table QR code is just a URL. Anyone who photographs it, or guesses the pattern, can
order to that table from anywhere. Location checks do not fix this: browser geolocation can be
overridden in standard developer tools ([Chrome DevTools: override geolocation](https://developer.chrome.com/docs/devtools/settings/locations)),
and Wi-Fi checks fail for guests on mobile data and are easy to get round by sharing the
password.

### What established products do

| Product | Documented approach | Source |
|---|---|---|
| Toast Mobile Order & Pay | Two modes: "pay-as-you-go" (guest pays each time they order) or tabs, with an option to require a pre-authorised card before a tab opens. Staff seat guests and help them load the menu from the table's own QR. | [Toast setup guide](https://support.toasttab.com/en/article/Setting-Up-Toast-Mobile-Order-and-Pay) |
| me&u (merged with Mr Yum) | Group tabs: "pay at end" places a pre-authorisation hold for the tab limit; "pay as you go" charges each order. | [me&u group tabs](https://help.meandu.com/hc/en-us/articles/6539880778511-Group-tabs-explained) |
| Square Online QR ordering | Guest selects items and pays on the phone; owner can switch off "Accept QR code orders" per location. | [Square help](https://squareup.com/help/us/en/article/7142-set-up-self-serve-ordering-and-qr-codes-with-square-online) |
| Lightspeed Order Anywhere | Table orders can be paid online by card; venue chooses automatic or manual acceptance. With manual acceptance, staff open the table and press Send before a ticket prints. | [Lightspeed: processing orders](https://resto-support.lightspeedhq.com/hc/en-us/articles/4411448915483-Processing-Order-Anywhere-orders) |
| Petpooja Scan & Order (India, UAE) | "Your captain validates the order with an OTP, and the KOT fires in your kitchen." Every order is staff-validated before the kitchen sees it. | [Petpooja Scan & Order](https://www.petpooja.com/poss/scan-and-order) |
| Gingersoft (Hong Kong) | Random per-sitting QR codes with a time limit and order verification, explicitly "to prevent malicious scanning and ordering". | [Gingersoft](https://www.gingersoft.com.hk/en/) |
| Bopple | Guest checkout can be reduced to first name and table number; payment taken at checkout. | [Bopple guest checkout](https://help.bopple.com/how-do-i-setup-guest-checkout) |
| Foodics | Online orders arrive on a cashier device set to receive them. I could not confirm on the help page whether accept/reject is manual (uncertain). | [Foodics help](https://help.foodics.com/hc/en-us/articles/8225883704860-Receiving-Online-Orders-in-the-Branch) |
| Sunday, Qlub | Mainly pay-at-table: the QR retrieves an existing POS bill, so a remote scanner can only pay, not create food orders. Qlub also offers NFC devices at tables. | [Sunday](https://sundayapp.com/), [Qlub pay-at-table](https://qlub.io/us/en/pay-at-table), [Stripe partner listing for Qlub](https://stripe.partners/directory/qlub) |

Pattern: Western products mostly rely on **payment first** (card or pre-auth hold), which makes
prank orders cost the prankster. Products built for cash-heavy markets (Petpooja, Gingersoft)
rely on **staff validation** or **per-sitting codes**, because pay-first does not fit.

### Options compared

| Layer | Stops remote orders? | Guest friction | Staff work | Hardware cost |
|---|---|---|---|---|
| Staff "open table" / seat activation (table accepts orders only after staff open it) | Yes, outside open sittings | None | One tap per seating | None |
| Short table code per sitting (shown by staff or on the bill folder, entered once) | Yes, strong | One 3–4 digit entry | Read code to guest | None |
| Approve first order only (later rounds auto-accepted for that sitting) | Yes, if staff check the table is occupied | Short wait on first order | One tap per table | None |
| Approve every order (Petpooja-style OTP) | Yes, strongest | Wait every round | High at peak | None |
| Pay first / card pre-auth | Prankster must pay | Card needed; poor fit for cash | Low | PSP fees |
| Order caps and rate limits (max items, max value, orders per minute per session) | Limits damage only | None for normal guests | None | None |
| Session expiry (guest session ends when bill settles or after idle time) | Stops reuse of old sessions | Rescan after leaving | None | None |
| Rotating QR on e-ink/LED table display | Yes | None | None | Per-table device, batteries, Wi-Fi (vendor claims; uncertain cost) |
| NFC tag | No (tag URL is as copyable as a QR) | Low; not all phones read NFC by default | None | Tag per table |

Rotating-code displays are described mainly in vendor posts (for example
[ITTA POS on dynamic QR](https://www.facebook.com/ITTAPOS/posts/not-all-qr-ordering-works-the-same-did-you-know-there-are-2-types-of-qr-ordering/1705826054880334/));
I found no independent evidence on reliability or cost, so treat them as uncertain.

### Recommendation for Mise

Default for a Pakistani sit-down restaurant, all software-only and cheap: (1) **staff opens the
table** from the Floor view when guests sit, and the table rejects orders when closed; (2) the
**first order of each sitting needs one-tap staff approval**, later rounds go straight to the
kitchen; (3) **session expiry** when the bill is settled or after a set idle time; (4) **caps and
rate limits** per session (item count, order value, orders per minute). Offer an optional
**per-sitting 4-digit table code** for venues with walk-through traffic or past abuse. Leave pay-first
as an option for card-heavy overseas venues only. Skip GPS, Wi-Fi checks, NFC and e-ink displays:
they add cost or friction without stopping a determined remote user.

---

## 2. Guest UX standards for QR menus

### Evidence and guidance

| Topic | Finding | Source |
|---|---|---|
| Dish photos | Uber Eats: menus with photos are "3x more likely to be ordered from". | [Uber Eats merchant academy](https://merchants.ubereats.com/us/en/academy/storefront/) |
| | DoorDash internal data: reaching 50% photo coverage raised sales about 13% on average (2023–2025). | [DoorDash merchants](https://merchants.doordash.com/en-us/blog/online-food-delivery-services-market-growth) |
| | Grubhub claims "up to 30 percent" per item; the widely repeated 25–30% range could not be traced to a primary study by one reviewer (treat as uncertain). | [Grubhub](https://get.grubhub.com/blog/improve-online-ordering-experience/), [Opnclo review](https://opnclo.com/blog/digital-menu-sales-statistics) |
| Tap targets | WCAG 2.2 AA: targets at least 24×24 CSS px, or spaced so a 24 px circle does not overlap neighbours. AAA (2.5.5) is 44×44. | [W3C SC 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [W3C SC 2.5.5](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html) |
| QR usage | NN/g: QR codes need clear, brief context and must lead straight to a relevant mobile page. | [NN/g QR guidelines](https://www.nngroup.com/articles/qr-code-guidelines/) |
| Devices in Pakistan | Android ~90% of mobile OS share (Sept 2026). | [StatCounter Pakistan](https://gs.statcounter.com/os-market-share/mobile/pakistan) |
| Connectivity | Local vendors stress that the menu is a web page using the guest's own mobile data, no app. | [Restozay guide](https://restozay.com/guides/qr-code-menu-pakistan) |

Practical standards derived from the above (my synthesis, not a single source):

- **Steps to order:** scan → category → add item → review → place order. No account, no app,
  no OTP for the guest in the default flow. Keep checkout on one screen.
- **Category navigation:** sticky horizontal category bar that scrolls to sections; search only
  when the menu is long.
- **Type and targets:** body text 16 px minimum; primary buttons 44–48 px tall (above the 24 px
  AA floor, matching common platform guidance); price and "Add" on the same row as the dish name.
- **Low-end Android and weak data:** compressed WebP/AVIF thumbnails with lazy loading, text menu
  usable before images arrive, no heavy web fonts on the critical path.
- **Older guests and low digital literacy:** large plain-language labels ("Add", "Send to
  kitchen"), icons always with text, a printed menu and a staff fallback. Never force a guest to
  use the phone.
- **Status after ordering:** a clear confirmation screen showing what was sent and a simple
  status (Received → Preparing → Served), plus "what next" (for example "Pay at the counter").
- **Calling staff:** a visible "Call waiter" and "Ask for bill" button, rate-limited, shown on
  the staff Floor view.

### Language: Urdu and Arabic

- Urdu is the national language under Article 251 of the Constitution, with English used
  officially ([National Assembly text](https://na.gov.pk/uploads/documents/1393408219_781.pdf)).
- Literacy is 60.7% in the 2023 census ([summary](https://en.wikipedia.org/wiki/2023_Pakistani_census);
  PBS headline [63%](https://www.pbs.gov.pk/)), and 84% in Islamabad and 66% in Punjab
  ([State of Children summary](https://stateofchildren.com/insights-from-the-2023-census-report/)).
  This is literacy in any language, not English literacy.
- **foodpanda Pakistan's website has no language switcher and no Urdu text**
  ([foodpanda.pk](https://www.foodpanda.pk/), checked 2026-10-30); its Play Store listing does not
  mention languages ([Play Store](https://play.google.com/store/apps/details?id=com.global.foodpanda.android&hl=en_US)).
  YouTube tutorials claim the app can switch to Urdu ([example](https://www.youtube.com/watch?v=SAdvTqPcLpU));
  unverified. foodpanda's own marketing uses Roman Urdu and Urdu video
  ([TikTok](https://www.tiktok.com/@foodpandapk/video/7602259082740813074)).
- Local QR-menu vendors I found market in English or Roman Urdu and do not advertise Urdu-script
  menus ([Restozay](https://restozay.com/guides/qr-code-menu-pakistan),
  [Conect.pk](https://www.facebook.com/Conect.Pk/videos/-smart-caf%C3%A9s-ka-smart-digital-menu-qr-code-se-digital-menu-no-waiting-pakistan-k/2257864515069164/)).
  No study measured demand for Urdu-script menus (gap).
- Technical cost of Urdu: RTL layout plus Nastaliq, which W3C documents as having specific web
  layout gaps ([Urdu Layout Requirements](https://www.w3.org/TR/arab-ur-lreq/),
  [Urdu Gap Analysis](https://www.w3.org/TR/arab-ur-gap/)). Noto Nastaliq Urdu is free on Google
  Fonts ([specimen](https://fonts.google.com/noto/specimen/Noto+Nastaliq+Urdu)) but Nastaliq needs
  much taller line height than Latin text; plan for it.

### Recommendation for Mise

Ship the UX standards above as defaults (photos encouraged with per-dish fallback, 44–48 px
buttons, 16 px text, three-state order status, call-waiter button). On language: English already
covers the current Lahore and Islamabad venues' printed menus and the main local apps, so **Urdu is
worth considering but not urgent**. If a family restaurant asks for it, add `ur` as a full RTL
locale with Noto Nastaliq Urdu loaded only for that locale, and keep dish names editable per
language. Note the project rule today allows only `en` and `it`; adding `ur` or `ar` needs that
rule changed first. **Arabic is needed** if an overseas venue is in Dubai, Riyadh or Doha: Arabic
is the official language there and guests and inspectors expect it (my own assessment; uncertain whether
any rule makes Arabic mandatory on a digital menu).

---

## 3. Per-restaurant brand kits

### What platforms let restaurants set

| Platform | Brand controls | Source |
|---|---|---|
| Toast Online Ordering | One brand accent colour (buttons, menu group, cart outline), logo, banner, favicon. Pro adds background, menu text, secondary text and card colours, heading and body fonts, custom font upload (.otf/.ttf/.woff). Colours are global across the page. | [Toast basic](https://support.toasttab.com/en/article/Customizing-Your-Toast-Online-Ordering-Page), [Toast Pro](https://support.toasttab.com/en/article/Getting-Started-with-Toast-Online-Ordering-Pro), [Pro menu customisation](https://support.toasttab.com/en/article/Toast-Online-Ordering-Pro-Menu-Customization) |
| me&u | One main theme colour; the app derives "tonal variations" and auto-selects black or white text "for optimal contrast". Logo and venue imagery set separately. | [me&u revamp](https://help.meandu.com/hc/en-us/articles/13065055225359-Explore-The-Revamped-Order-Pay-Experience), [me&u logo](https://help.meandu.com/hc/en-us/articles/6539880730255-How-to-update-your-venue-s-logo-and-imagery) |
| Square Online | Preset styles, then colours, fonts and button shapes. Checkout keeps the default font "for legibility". | [Square styles](https://squareup.com/help/us/en/article/7820-choose-themes-for-your-square-online-site) |
| ChowNow | Branded app: logo, loading screen image, name, colour scheme. Logo minimum 60×60 px. | [ChowNow app design](https://get.chownow.com/restaurant-support/design-updates-on-restaurant-mobile-apps/), [logo rules](https://get.chownow.com/restaurant-support/what-are-our-logo-requirements-and-guidelines/) |
| Owner.com | Guidance: 3 brand words for tone; 1 primary, 1 secondary, 1 neutral colour; headline and body fonts; logo in full, stacked and icon forms, light and dark. | [Owner.com branding guide](https://www.owner.com/blog/restaurant-branding-more-direct-orders) |
| Sunday | Customises the payment flow to brand identity and voice (marketing page, few details). | [Sunday branding](https://sundayapp.com/branding/) |
| UpMenu | Templates plus custom colours, style and domain (marketing page, few details). | [UpMenu](https://www.upmenu.com/restaurant-website-builder/) |

Common shape: **few inputs** (one accent colour, logo, banner, optional fonts), with the platform
deriving the rest and protecting legibility in checkout. me&u and Square both explicitly limit
brand control where readability matters.

### Proposed brand kit contents

| Item | Contents |
|---|---|
| Logo | Full, stacked/square, icon; light-on-dark and dark-on-light; SVG plus PNG; one-colour version for thermal print |
| Colour | Primary (required), secondary (optional), neutral surface/background chosen from a short safe list |
| Typography | Display font for headings (optional); body font fixed to a legible system or Noto stack; script support per locale |
| Imagery | Photo style notes (light, angle, background), banner image, dish photo aspect ratio |
| Tone of voice | Three brand words; greeting and confirmation copy within length limits |
| Printed assets | QR table card (logo, table number, short URL, call-to-action), bill header (name, address, "Demo bill, not a tax invoice" in demo), kitchen ticket (venue name only, monochrome, no colour dependence) |

### Deriving an accessible token set

- WCAG 2.2 AA requires 4.5:1 contrast for normal text, 3:1 for large text, and 3:1 for UI
  components and focus indicators ([W3C SC 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
  [SC 1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)).
- OKLCH is defined in CSS Color 4 ([W3C](https://www.w3.org/TR/css-color-4/)); its L channel is
  perceptual, so equal lightness steps look equal, unlike HSL
  ([12 Days of Web](https://12daysofweb.dev/2022/css-color-spaces-relative-color-syntax/),
  [Evil Martians](https://evilmartians.com/chronicles/oklch-in-css-why-quit-rgb-hsl)).

Method: convert the brand colour to OKLCH; generate a tint/shade ramp by stepping L at fixed
hue (lower chroma near the ends to stay in sRGB gamut); for each token pair (text on brand, brand
on surface, link on surface) compute the **WCAG 2 contrast ratio in sRGB** and choose white or
near-black text, or move to the nearest ramp step that passes. Do this server-side or at build
time and store the result, so every surface (web, print preview) uses the same checked tokens. OKLCH
lightness is a good guide but not a guarantee: the pass/fail check must use the WCAG formula.

### Pitfalls

- Mid-lightness brand colours (orange, bright red, yellow) fail 4.5:1 with both white and black
  text; use a darker shade for buttons and keep the true brand colour for accents.
- Gamut clipping: high-chroma OKLCH steps fall outside sRGB and shift hue when clipped.
- Brand colour used for error or success states confuses guests; keep status colours fixed.
- Custom display fonts without Urdu or Arabic glyphs fall back badly; set fonts per script.
- Thermal kitchen and bill printers are monochrome; nothing may depend on colour.
- Logos on photos need a scrim or solid backing to keep 3:1.
- Dark mode needs its own checked pairs; inverting the light set is not enough.

### Recommendation for Mise

Adopt a **small brand kit**: logo set, one primary colour, optional secondary, a surface choice
from a safe list, optional display font, banner image and three tone words. Derive all other
tokens in code with an OKLCH ramp plus a WCAG 2 contrast check, auto-pick text colour as me&u
does, and refuse or adjust any pair below AA. Keep checkout, prices, allergen status and order
status in fixed, tested styles that brands cannot override. Print assets use a monochrome logo.

---

## 4. Two overseas showcase venues

### Shortlist

| Market | Pakistani community | Fit for a Pakistan-based studio | Notes |
|---|---|---|---|
| UAE (Dubai) | ~1.6 m Pakistanis in UAE (2020 estimate, Ministry figure via [Wikipedia](https://en.wikipedia.org/wiki/Pakistani_diaspora); uncertain) | High: short flights, same time zone band, many Pakistani-owned restaurants, English widely used | Petpooja and Qlub already sell there ([Petpooja UAE](https://www.petpooja.com/ae/poss/scan-and-order), [Qlub](https://qlub.io/)): proven demand, real competition |
| UK (Manchester or London) | 1.59 m Pakistani ethnic group in England and Wales, 2.7% ([Census 2021](https://www.ethnicity-facts-figures.service.gov.uk/uk-population-by-ethnicity/national-and-regional-populations/population-of-england-and-wales/latest/)) | High: English, family links, large desi food scene, credible "global" signal | Strict consumer pricing rules; mature competitors |
| Saudi Arabia (Riyadh) | 1.81 m (2022 census, via [Wikipedia](https://en.wikipedia.org/wiki/Pakistani_diaspora)) | Medium: large market but Arabic-first and ZATCA e-invoicing integration expected | Highest compliance burden |
| Qatar (Doha) | Smaller | Medium-low: small market | No VAT in force (uncertain; not verified on an official page) |
| Canada (Toronto) | Significant (no official figure gathered) | Medium: far time zones | Ontario HST 13% ([CRA](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate.html)) |
| USA | Significant but spread out | Low: sales tax varies by city, tipping UX complex | Not researched further |

### Detail for the top two

| | UAE (Dubai) | UK |
|---|---|---|
| Currency | UAE dirham, AED, 2 decimal places (ISO 4217). Menus usually show "AED 45" or "45" with no decimals; the new dirham symbol exists but menus mostly still write AED (uncertain). | Pound sterling, GBP, symbol £, 2 decimals. Menus usually show "£12.50" or "12.5". |
| Tax on restaurant food | VAT 5% ([FTA](https://tax.gov.ae/en/taxes/Vat.aspx)) | VAT standard rate (20%) on eat-in catering and hot takeaway ([HMRC Notice 709/1](https://www.gov.uk/guidance/catering-takeaway-food-and-vat-notice-7091)). A temporary reduced rate for certain children's meals applied 25 June to 1 September 2026 only (same source). |
| Menu prices include tax? | Yes: displayed prices must include VAT (Art. 38, Federal Decree-Law 8 of 2017, per [Legal 500](https://www.legal500.com/intelligence/united-arab-emirates/tax/vat-inclusive-displayed-prices-rule-exceptions-and-implications); [law PDF](https://tax.gov.ae/DataFolder/Files/Pdf/VAT-Decree-Law-No-8-of-2017.pdf)) | Yes: prices to consumers should include VAT and all non-optional charges ([Code of Practice for Traders on Price Indications](https://www.legislation.gov.uk/uksi/2005/2705/made), [Business Companion](https://www.businesscompanion.info/en/guidance-for-traders-on-pricing-practices)) |
| Municipality / extra fees | 7% Dubai Municipality fee and 10% service charge apply to hotel and licensed venues, not standalone restaurants ([Menuthere, citing official sources](https://menuthere.com/en/guides/uae/dubai-restaurant-fees-and-vat); [Business Dubai](https://www.businessdubai.ae/blogs/restaurant-business-setup-dubai); secondary). A May 2026 Dubai package exempts DET-registered establishments from collecting "sales fees on hotel rooms and restaurants" (Dubai Media Office press release, 21 May 2026); scope and end date unclear (uncertain). | None |
| Service charge and tips | Service charge mainly in hotels (above); tipping customary but optional (uncertain, no official source) | Discretionary service charge common in sit-down venues (often 12.5%, uncertain). Tips and service charges must be passed fully to workers under the Employment (Allocation of Tips) Act 2023 ([statutory code](https://www.gov.uk/government/publications/distributing-tips-fairly-statutory-code-of-practice/code-of-practice-on-fair-and-transparent-distribution-of-tips-html-version)). |
| Payments | Cards, Apple Pay and Google Pay dominate in venues using Qlub ([Qlub](https://qlub.io/us/en/pay-at-table)); cash still used (uncertain share) | Debit card most used; about 4 in 10 payments contactless; half of adults use mobile wallets ([UK Finance 2025](https://www.ukfinance.org.uk/system/files/2025-10/Payment%20Markets%20Report%20Summary.pdf)) |
| E-invoicing / fiscal | Mandatory e-invoicing phases in: businesses with AED 50 m+ revenue from 1 Jan 2027, others from 1 Jul 2027 ([Hawksford](https://www.hawksford.com/insights-and-guides/uae-e-invoicing); secondary, official MoF page not retrieved). Whether B2C restaurant bills are in scope is uncertain. | No mandatory e-invoicing or fiscal receipt for restaurants. |
| Language | Arabic official; English widely used | English |

Saudi note, if chosen later: VAT 15% ([ZATCA](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Amendments-to-the-Implementing-Regulation-of-%28VAT%29.PDF));
simplified tax invoices must carry a ZATCA-specified QR code
([ZATCA e-invoicing guideline](https://zatca.gov.sa/en/e-invoicing/introduction/guidelines/documents/e-invoicing_detailed__guideline.pdf)).
A demo bill there must never carry a QR code, VAT registration number or the words "tax invoice".

### Recommendation for Mise

Pick **Dubai and the UK (Manchester first, London as an alternative)**. Dubai is the most
reachable overseas market for a Pakistani studio, has a very large Pakistani community and a
simple 5% tax-inclusive model; it also forces Arabic support, which proves the "works anywhere"
claim. The UK has the largest settled Pakistani diaspora in the West, English-only menus, and a
different rule set (20% VAT, discretionary service charge, tips law), so together the two venues
show currency, tax and language range without the ZATCA integration Saudi Arabia would demand.
For both demo venues: tax-inclusive menu prices, an optional service charge line shown separately,
bills labelled as demo bills with no QR code, no tax registration number and no "invoice" wording,
consistent with the project's demo-bill rule. Revisit UAE e-invoicing scope before any paid UAE
deployment in 2027.
