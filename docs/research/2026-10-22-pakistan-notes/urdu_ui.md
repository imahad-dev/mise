# Urdu UI best practice (Next.js / Tailwind v4 guest app + kitchen tickets)

Researched 2026-10-22. "Measured" means checked directly in this session: Node 24.7 (ICU 77.1, CLDR 47) for Intl output, `curl` of live site HTML/CSS for fonts and price formats, and `curl` of the Google Fonts CSS API and gstatic for font subset sizes.

## RTL implementation (dir/lang, logical properties, Tailwind v4 rtl:/ltr:, icon mirroring, bidi isolation, prices/phones)

### Takeaway
Set `<html lang="ur" dir="rtl">` per request locale and lay the page out with logical utilities (`ms-/me-/ps-/pe-/start-/end-`, `text-start`), so one class set works in both directions. Keep `rtl:`/`ltr:` for the few exceptions, such as transforms and icon flips. Wrap every LTR fragment inside Urdu text (prices, phone numbers, English dish names, order numbers) in `<bdi>` or in an element with `dir="ltr"`/`dir="auto"`. Mirror directional icons only.

### Cited Findings
- Tailwind docs: "Use the `rtl` and `ltr` variants to conditionally add styles in right-to-left and left-to-right modes." The `rtl` variant compiles to `&:where(:dir(rtl), [dir="rtl"], [dir="rtl"] *)`. Tailwind says these variants are only needed when one site supports both directions. — [Tailwind: hover, focus and other states](https://tailwindcss.com/docs/hover-focus-and-other-states)
- W3C: "tightly wrap every opposite-direction phrase in markup that sets its base direction". Use `dir="auto"` when the direction is unknown until run time. "If there is no markup, wrap … with a `bdi` element" (`bdi` defaults to `dir=auto`). Prefer markup over invisible control characters. Use RLI/LRI/FSI/PDI only where markup is impossible (e.g. `<title>`, attribute values). Use LRM/RLM only as a legacy fallback, because they "only address the isolation problem". Don't use `bdo` for normal content. — [W3C: Inline markup and bidirectional text in HTML](https://www.w3.org/International/articles/inline-bidi-markup/)
- W3C Urdu layout requirements: "Numbers, even Arabic numbers, are written from left to right", and layout is right to left when Arabic script is the main script. Arabic-script ascenders and descenders "extend much further than those of the Latin script", so mixed-script baselines need care. (This doc is now retired in favour of the shared Arabic-script resources.) — [W3C Urdu Layout Requirements (retired)](https://w3c.github.io/alreq/arab-ur/index.html)
- Material bidirectionality guidance: mirror icons that show direction (back/forward arrows, "next" chevrons, a volume slider). Do NOT mirror icons that don't show direction (camera), numbers (clocks, phone numbers), charts, or media playback controls (they show tape direction). — [Material Design 2: Bidirectionality](https://m2.material.io/go/design-bidirectionality); [Material 1](https://m1.material.io/usability/bidirectionality.html); GNOME discussion of media icons: [GTK issue 2469](https://gitlab.gnome.org/GNOME/gtk/-/issues/2469)
- Android Compose ships `Icons.AutoMirrored`, a subset of icons that mirror automatically in RTL, which is a useful list of the icons that should flip. — [Android Icons.AutoMirrored](https://developer.android.com/reference/kotlin/androidx/compose/material/icons/Icons.AutoMirrored?authuser=5)
- Wikimedia Codex has a maintained bidirectionality style guide (a design-system example). — [Codex bidirectionality](https://doc.wikimedia.org/codex/main/style-guide/bidirectionality.html)
- Measured: `new Intl.NumberFormat('ur-PK',{style:'currency',currency:'PKR'}).format(1250)` returns `Rs 1,250.00`, with code points `52 73 A0 31 2C …`. It uses a no-break space and includes **no** LRM/RLM or isolate marks. In an RTL paragraph it is therefore a neutral/LTR run that still needs isolation. (Node 24.7 / ICU 77.1.)

### Inferences
- Use a route-segment locale such as `app/[locale]/layout.tsx` and set `<html lang={locale} dir={locale === 'ur' ? 'rtl' : 'ltr'}>` on the server. That way the first paint is in the right direction and there's no layout flip. The project's current rule is "Languages: `en` and `it` only" (CLAUDE.md), so adding `ur` is a policy change.
- Tailwind v4 already ships the logical utilities `ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `text-start/end`, `border-s/e`, `rounded-s/e`. Grep and replace `ml-/mr-/pl-/pr-/left-/right-/text-left/text-right` rather than adding `rtl:` pairs everywhere. (The fetched Tailwind page didn't list these utilities, so check them against the Tailwind spacing docs.)
- `rtl:-scale-x-100` on chevron/arrow icons is the minimal way to mirror. Leave the cart, allergen, clock, checkmark and plus/minus icons alone.
- Price component: `<bdi>{formatPrice(n)}</bdi>` (or `<span dir="ltr">`). Phone number: `<a href="tel:…" dir="ltr">`. Order/table number: `<bdi>`. English dish names inside Urdu sentences: `<bdi lang="en">`. Number inputs (`<input type="tel|number">`) should get `dir="ltr"`.
- Strings built by interpolation in i18n messages (e.g. "{count} items") are safe if the placeholder is rendered as a React node wrapped in `<bdi>`. They are not safe if string concatenation puts raw numbers next to Urdu punctuation.
- Avoid inline styling *inside* an Urdu word (see Fonts gaps: it breaks cursive joining).

### Gaps
- I didn't fetch Tailwind's logical-property docs page directly, so the utility names come from my own knowledge of Tailwind v4.
- I didn't verify the current M3 page wording (only M1/M2 copies).

## Fonts (Nastaliq vs Naskh; Noto Nastaliq Urdu, Noto Naskh Arabic, Gulzar, Mehr, Jameel Noori; what Pakistani sites use; sizes; licensing)

### Takeaway
For UI (buttons, chips, prices, menus) use a **Naskh** face, Noto Naskh Arabic (OFL, about 51 KB woff2 for the Arabic subset). That's what the major Pakistani Urdu news sites do for body/UI text. Nastaliq is culturally preferred for reading, but it is about 3x heavier, needs much taller line-height, and has documented clipping, spacing and fallback problems. If Nastaliq is wanted, use it for headings/dish names with Noto Nastaliq Urdu (OFL). Do not use Jameel Noori Nastaleeq (not freely licensed). Mehr Nastaliq is CC BY-SA, not OFL.

### Cited Findings
- **What Pakistani sites actually ship (measured from their live HTML/CSS):**
  - BBC Urdu: its own proprietary `BBC Reith Qalam` (`BBCReithQalam_W_Rg/Bd`). — [bbc.com/urdu](https://www.bbc.com/urdu)
  - Geo Urdu: `Nafees-Web-Naskh` / `NafeesWeb` and `new-naskh`. — [urdu.geo.tv](https://urdu.geo.tv/)
  - Daily Jang: `NotoNaskhArabic-Regular` plus `Nafees` and a `mehran` face. — [jang.com.pk](https://jang.com.pk/)
  - Express: `Nafees-Web-Naskh !important`. — [express.pk](https://www.express.pk/)
  - Daraz.pk: Latin `NotoSans-*` only; I found no Urdu UI on the homepage. — [daraz.pk](https://www.daraz.pk/)
- Google's 2014 launch post for Noto Nastaliq Urdu warned that the font "can be challenging to the current generation of browsers and font renderers". — [Google Developers Blog](https://developers.googleblog.com/en/i-can-get-another-if-i-break-it-announcing-noto-nastaliq-urdu)
- A Chrome 138 user (2025) reported Noto Nastaliq rendering much larger than other Urdu fonts, with some words mis-shaped. This is a single user report. — [Discourse meta](https://meta.discourse.org/t/discourse-font-rendering/378897)
- Android: a developer found Noto Nastaliq takes far more vertical space than its text needs. Removing font padding only partly helped, so they wrote a custom layout modifier. (I could only read this through the search summary; the article returned 403.) — [ProAndroidDev: Taming Noto Nastaliq](https://proandroiddev.com/taming-noto-nastaliq-fixing-urdu-font-rendering-issues-in-android-c65e83b40b34)
- A design-system guide recommends line-height of at least 1.8 for Nastaliq and says 1.5 clips diacritics. This is opinion, not measurement. — [open-design.ai design system urdu](https://open-design.ai/plugins/design-system-urdu/)
- W3C gap analysis: browsers cannot fall back to a Nastaliq font specifically (High priority). CSS Fonts 4 `generic(nastaliq)` is unsupported in Gecko, Blink and WebKit. Inline styling inside a word breaks cursive joins: WebKit fails for any styling, and Firefox fails on weight, style or size changes. Gecko and Blink draw dark patches where glyphs overlap when text has opacity. Text-stroke breaks joins. — [W3C Urdu Gap Analysis (retired, see alreq-gap)](https://www.w3.org/TR/arab-ur-gap)
- **Sizes (measured, Google Fonts woff2, Arabic subset, weight 400):** Noto Nastaliq Urdu 159,368 B (about 156 KB). Noto Naskh Arabic 52,668 B (about 51 KB). Gulzar 208,800 B (about 204 KB). Google Fonts already splits each font into `arabic`, `latin`, `latin-ext` subsets via `unicode-range`. The Arabic subset covers U+0600–06FF, U+0750–077F, U+FB50–FDFF, U+FE70–FEFC and U+200C–200E (ZWNJ/ZWJ/LRM). Noto Nastaliq Urdu offers weights 400–700. — [Google Fonts CSS API](https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400..700)
- **@fontsource (measured via npm, 2026-10):** `@fontsource/noto-nastaliq-urdu` 5.3.0 OFL-1.1 (also `@fontsource-variable/noto-nastaliq-urdu`), `@fontsource/noto-naskh-arabic` 5.3.0 OFL-1.1 (also variable), `@fontsource/gulzar` 5.3.0 OFL-1.1 (no variable package). Fontsource page: [fontsource.org noto-nastaliq-urdu](https://fontsource.org/fonts/noto-nastaliq-urdu/about). `next/font/google` can self-host the same Google families.
- **Licensing:**
  - Noto Nastaliq Urdu: SIL OFL 1.1 — [fontsource](https://fontsource.org/fonts/noto-nastaliq-urdu/about)
  - Noto Naskh Arabic and Gulzar: OFL-1.1 (npm license field, measured)
  - SIL Awami Nastaliq: OFL — [Wikipedia: Awami Nastaliq](https://en.wikipedia.org/wiki/Awami_Nastaliq)
  - Mehr Nastaliq Web: **CC BY-SA 4.0** for the font (wrapper code MIT) — [mehr README on jsDelivr](https://cdn.jsdelivr.net/npm/mehr@2.0.1/README.md), [GitHub mehr](https://github.com/ansarinaeemakhtar/mehr), [NeoNetwork 2017](https://en.neonetwork.pk/09-Feb-2017/pakistani-researchers-developed-calligraphic-urdu-font-for-internet)
  - **Jameel Noori Nastaleeq: not free.** Wikimedia refused to install it because it is not free. Its own notice reportedly says only "free of charge for Urdu lovers", and commercial use is unclear. — [Wikimedia Phabricator T62685](https://phabricator.wikimedia.org/T62685); [ubuntu-pk mailing list](https://lists.launchpad.net/ubuntu-pk/msg00007.html)
  - Nafees Nastaleeq (CRULP): permissive permission notice with renaming conditions; listed as MIT/X11 on Font Library. — [Font Library](https://fontlibrary.org/en/font/nafees-nastaleeq)
- Browser extensions that restyle BBC Urdu, Jang and similar sites in Nastaliq (Mehr, Awami, Gulzar, Noto) exist. This shows reader demand for Nastaliq, but it's not what the sites ship. — [WebUrdu (GitHub)](https://github.com/ishaqx/WebUrdu)

### Inferences
- Recommended stack: `font-family: "Noto Naskh Arabic", "Noto Sans Arabic", system-ui, sans-serif` under `:lang(ur)`, keeping the existing Latin font for Latin runs. Start at a 16–17px base (about 1.1× the Latin size) with `line-height: 1.6–1.7` for Naskh. If Nastaliq is used for display text, use `line-height ≥ 1.8–2.2` and give its containers no fixed height and no `overflow:hidden`, so the deep descenders don't clip.
- Load the Urdu font only on the `ur` route (`next/font` in the `[locale]` layout or a conditional `@fontsource` import) so English users pay nothing. `unicode-range` subsetting is already done by Google Fonts and Fontsource, so further subsetting isn't worth the effort.
- Never apply bold/colour spans to part of an Urdu word (e.g. search-match highlighting), because it breaks joins. Avoid `opacity` on Urdu text (it causes overlap artifacts in Blink); use a lighter colour instead.
- Faux bold: Noto Naskh Arabic has real weights 400–700. Load 400 and 600/700 only.

### Gaps
- I didn't verify the line-height recommendations on real devices. They need testing on low-end Android Chrome.
- I couldn't confirm which fonts foodpanda Pakistan or banking apps use for Urdu. Their sites appear English-first, and native apps can't be inspected by curl.
- The license of BBC Reith Qalam isn't public. It is BBC-proprietary and unavailable.
- I couldn't read Jameel Noori's original license text, so treat the font as non-free.

## Numerals (Western 0-9 vs Urdu ۰-۹; Intl ur-PK behaviour)

### Takeaway
Use Western digits (0–9). CLDR/ICU `ur-PK` defaults to `latn`, and Pakistani commercial UIs use Latin digits. Only `ur-IN` or an explicit `-u-nu-arabext` produces ۰–۹, and browsers render those glyphs inconsistently.

### Cited Findings
- Measured (Node 24.7, ICU 77.1, CLDR 47):

  | locale | currency PKR | plain | numberingSystem |
  |---|---|---|---|
  | `ur-PK` | `Rs 1,250.00` | `1,250` | `latn` |
  | `ur` | `Rs 1,250.00` | `1,250` | `latn` |
  | `ur-PK-u-nu-arabext` | `Rs ۱٬۲۵۰٫۰۰` | `۱٬۲۵۰` | `arabext` |
  | `ur-IN` | `PKR ۱٬۲۵۰٫۰۰` | `۱٬۲۵۰` | `arabext` |
  | `en-PK` | `Rs 1,250.00` | `1,250` | `latn` |

  `ur-PK` groups in thousands (`1,250,000`), not lakhs. `currencyDisplay:'name'` gives `1,250.00 پاکستانی روپیہ`.
- ICU locale data for ur_PK lists the currency symbol "Rs", the international symbol PKR, the grouping separator ",", and zero digit "0". — [LocalePlanet ICU ur_PK](https://www.localeplanet.com/icu/ur_PK/index.html)
- W3C gap: Urdu uses the extended Arabic-Indic digits (U+06F0–06F9), but Blink shows Persian glyph shapes for them (e.g. ۴ ۵ ۶ differ from Urdu forms). WebKit shows the Urdu shapes. Gecko uses Persian shapes. — [W3C Urdu Gap Analysis](https://www.w3.org/TR/arab-ur-gap)
- foodpanda.pk shows prices as `Rs.599`, `Rs.1299`, `Rs. 1,300` (Latin digits; measured from live HTML). — [foodpanda.pk](https://www.foodpanda.pk/)

### Inferences
- Format with `Intl.NumberFormat('ur-PK', …)` (or a single shared formatter for both locales). Do not use `ur-IN` by accident. Server-side (Python) price strings should match the client's.
- Pass `maximumFractionDigits: 0`, because PKR menu prices are whole rupees.
- Latin digits mean prices, totals and quantities look the same in English and Urdu UIs. That also keeps them readable to kitchen staff and consistent with receipts.

### Gaps
- I found no survey data on the share of Pakistani apps using Latin vs Urdu digits. The recommendation rests on CLDR defaults and the observed sites.
- I didn't test browser Intl output (Chrome/Safari bundle their own ICU), but it uses the same CLDR data, so it should match.

## Currency display (Rs / Rs. / PKR / روپے)

### Takeaway
Show `Rs 1,250` (or `Rs. 1,250`) in both the English and Urdu UIs, wrapped in `<bdi>`. "Rs" is the CLDR symbol for ur-PK and en-PK and what foodpanda uses. "روپے" is natural only in prose (e.g. "کل 1,250 روپے"). Keep "PKR" for invoices and exports.

### Cited Findings
- CLDR symbol "Rs" for ur_PK and en_PK; ISO code PKR. — [LocalePlanet ICU ur_PK](https://www.localeplanet.com/icu/ur_PK/index.html); measured Intl output above.
- foodpanda.pk mixes `Rs.599` (no space, with period) and `Rs. 1,300`. — [foodpanda.pk](https://www.foodpanda.pk/) (measured)
- Intl `currencyDisplay:'name'` gives `پاکستانی روپیہ` (singular). (Measured.)

### Inferences
- Because Intl inserts a no-break space, `Rs 1,250` won't wrap. Inside RTL text the whole thing stays one LTR island when wrapped in `<bdi>`, with "Rs" to the left of the number as on English receipts.
- Writing "روپے" after the number in Urdu sentences is fine for copy, but don't hand-roll it in price components.

### Gaps
- I didn't check the Cheezious and KFC Pakistan sites: they render client-side and returned no price strings. Banking apps weren't inspected.

## Kitchen tickets in Urdu (thermal printers, KDS)

### Takeaway
ESC/POS printers generally can't shape Urdu from their built-in code pages. The standard approach is to render the ticket to a 1-bit bitmap (with a browser/canvas or a server text renderer that does HarfBuzz shaping) and send it as a raster image (`GS v 0`). Screen KDS can show the dish name in English with Urdu beneath it, since browsers shape Urdu natively.

### Cited Findings
- The `unified_esc_pos_printer` package does "multilingual text rasterization", rendering text through Flutter TextStyle so "any font, script, or style" can print. It sends the result as column (ESC *) or raster (GS v 0 / GS ( L) images with auto-resize. — [pub.dev unified_esc_pos_printer](https://pub.dev/documentation/unified_esc_pos_printer/3.4.0/)
- The Rust `escpos` crate supports raster bit images behind a `graphics` feature. — [docs.rs escpos](https://docs.rs/crate/escpos/latest)
- Raster support varies by model: `esc_pos_printer` reports graphics don't work on an Xprinter XP-N160I but do on a MUNBYN model. — [esc_pos_printer 3.1.2](https://pub-web.flutter-io.cn/packages/esc_pos_printer/versions/3.1.2)

### Inferences
- A cheap path in this stack is to render the ticket as HTML and print through the browser/OS driver at 58 or 80 mm. The browser does the Urdu shaping, and the vendor driver rasterizes. Raw ESC/POS from the server needs a shaping renderer (e.g. Pillow with libraqm, or a headless browser screenshot) and then a GS v 0 dither to 1-bit (384 dots wide for 58 mm, 576 for 80 mm at 203 dpi).
- Use Naskh, not Nastaliq, at 24px or larger on thermal paper. Thin Nastaliq strokes and stacked glyphs degrade at 203 dpi. Print quantity and table number in large Latin digits.
- KDS: show the Urdu name as a secondary line under the canonical English/house name, so the kitchen always shares one identifier. Allergen flags should stay icon plus fixed text from server code (CLAUDE.md: allergen status is deterministic server code).

### Gaps
- I found no source documenting Urdu-specific ESC/POS code pages or any Pakistani kitchen's practice (Urdu vs English tickets). Field validation with real staff and real printers is needed.
- I didn't measure how readable Urdu is at thermal resolution.

## Translation quality (dish naming, Roman Urdu, glossary, MT pitfalls)

### Takeaway
There is no national standard for Urdu app-UI terminology, so a small, human-reviewed glossary is required. Many Pakistani dishes are already Urdu words (biryani, karahi, nihari), so names should be transliterated from what customers say, not translated. Use the polite "آپ" register. Have a native reviewer check every string. The CRULP/NLA localization glossary is the only public term base found.

### Cited Findings
- The CRULP Urdu Localization Terminology Glossary is based on the National Language Authority's 2005 English-Urdu computing dictionary and is available as a UTF-8 TSV. — [CLE OSS glossary](https://cle.org.pk/software/localization/OSS/ossGlossary.html)
- A LibreOffice localizer says app-UI jargon is "essentially 'untouched' territory", that every project uses its own discretion, and that "Find/Search" has three valid renderings of differing formality. This is an anecdotal forum post. — [LibreOffice l10n list 2021](https://listarchives.libreoffice.org/global/l10n/2021/msg00265.html)
- The CLE localization paper says GUI strings are the bulk of the work. Teams should balance technical and language experts (they used 3 + 3). — [CLE ICOSST 2010 paper](https://www.cle.org.pk/Publication/papers/2010/icosst2010.pdf)
- ProZ (2026): register matters. The informal "tum" register can seem "flippant or disrespectful" to older users, while archaic vocabulary makes apps feel stiff. Nastaliq's sloping baseline clashes with UI grids. (Search summary only; the page returned 403.) — [ProZ: Urdu Localization: Balancing Script Tradition and Digital Demand](https://www.proz.com/doc/5138)

### Inferences
- Proposed starter glossary (my own translations, to be reviewed by a native speaker before use):

  | English | Urdu | Note |
  |---|---|---|
  | Add to order | آرڈر میں شامل کریں | "آرڈر" is the common loanword |
  | View order | آرڈر دیکھیں | |
  | Confirm order | آرڈر کی تصدیق کریں | |
  | Allergens | الرجی پیدا کرنے والے اجزاء | short label: الرجی اجزاء |
  | Contains | شامل ہے / پر مشتمل | |
  | Menu | مینو | |
  | Table | ٹیبل / میز | ٹیبل is more common in restaurants |
  | Total | کل رقم | |
  | Cancel | منسوخ کریں | |

- Keep dish names as owner-entered data with an optional `name_ur` field. Don't machine-translate names (e.g. "Chicken Karahi" → "چکن کڑاہی", not a literal translation of "wok").
- MT pitfalls to watch for: literal "tum" register, Hindi-leaning vocabulary from IN-trained models, wrong gender agreement on verbs, and English loanwords (order, menu, bill) being replaced by obscure Persianate coinages that customers don't use. Allergen text has safety consequences and must never be machine-generated (and per CLAUDE.md the model never decides allergen status).
- Roman Urdu is widely used in Pakistani chat and marketing. A guest UI choice of "English | اردو" covers most users. Roman Urdu as a third locale isn't warranted.

### Gaps
- I found no sourced data on Roman Urdu prevalence in Pakistani app UIs, nor any public foodpanda or bank Urdu string set to copy terminology from.
- The glossary above is unsourced (my own translation) and needs native review.

## Accessibility for Urdu (screen readers)

### Takeaway
Android TalkBack supports "Urdu (Pakistan)" through Google TTS. With correct `lang="ur"` it can read the guest app. I couldn't confirm iOS VoiceOver Urdu voice support. Correct `lang` on `<html>` and `lang="en"` on English islands is the main thing to get right.

### Cited Findings
- Google's TalkBack language list includes "Urdu (Pakistan)". — [Google: Languages supported by TalkBack](https://support.google.com/accessibility/android/answer/11101402?hl=en)
- Pakistani research groups have built Urdu TTS and screen-reader projects, which suggests mainstream support has been historically thin. — [KICS project](https://www.kics.edu.pk/project/index/272); [CLE dialog project](https://cle.org.pk/dialog/scope.html)

### Inferences
- Set `lang="ur"` on `<html>`, `lang="en"` on embedded English, `aria-label`s translated, and keep prices as text (not images), so TTS reads numbers correctly.
- Don't render Urdu text as images in the web UI. That is acceptable only on the printed ticket.

### Gaps
- I couldn't confirm iOS VoiceOver Urdu voice availability (Apple's language list wasn't retrieved). I also didn't test how TalkBack reads `Rs 1,250` in an Urdu context.
