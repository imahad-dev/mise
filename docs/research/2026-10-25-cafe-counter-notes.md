# Café counter / pickup ordering: research notes (2026-10-25)

Purpose: inform the design of the Mise demo (counter/pickup + QR self-order). Budget was about 15 tool calls and the search API was rate-limited near the end, so coverage is partial. Gaps are listed explicitly. Do not treat INFERENCE items as facts.

Legend: **[SOURCED]** read on the cited page (via search excerpt or full page scrape) | **[EXCERPT]** only a search-result snippet seen, page not read | **[ANECDOTAL]** forum/social/review snippet | **[INFERENCE]** my reasoning | **[NOT FOUND]** searched or attempted, nothing usable.

## 1. Counter flow in Pakistani cafés (Q1)

- Chain-specific practice (Gloria Jean's Pakistan, Espresso, Tim Hortons Pakistan, Butlers Chocolate Café, local specialty cafés): **[NOT FOUND]**. One search returned only Gloria Jean's Facebook/Instagram/TikTok/TripAdvisor listings (rating, address, "order took longer than expected" review). Nothing on token slips, name calling, table tents or buzzers. Sources seen: facebook.com/GloriaJeansCoffeesPakistan, tripadvisor.com (Gloria Jean's Lahore, 2.8/5 from 8 reviews, [ANECDOTAL], one review complains about a slow order and food temperature).
- Pay-first vs pay-at-pickup prevalence in Pakistani cafés: **[NOT FOUND]**.
- **[INFERENCE]** Counter-service cafés worldwide are overwhelmingly pay-first (cashier takes payment, then the order is made). I would assume the same for Pakistani chain cafés, but I have no source. Table-service cafés and restaurants are pay-after. Verify before claiming anything about Pakistan in README or docs.

## 2. QR / self-order / mobile-order patterns (Q2)

- **Square QR ordering** **[SOURCED]** (squareup.com/help/us/en/article/7142, cached 2026-10-25): customer scans the QR, selects items, adds requests and **pays on their phone**. "Since everything is processed online, there's no need to handle credit cards or cash." After completion the order appears on the POS and feeds the kitchen ticket printer or KDS. Each QR can be tied to an "ordering station" (table/seat/spot), or the guest enters their location manually (events, stadiums). Setup also has text-message alerts, order ticket preferences, ordering hours with time zone, an optional service fee, and a toggle "Accept QR code orders" to stop intake. No pay-later option is described on that page.
- **Square Kiosk Lite** **[SOURCED]** (squareup.com/help/us/en/article/8313): order-ready notification can identify the diner by **name**, **table number**, or **order number**. Order-number notification requires text messages (phone number collected; can be made optional). Dining options such as For Here / To Go are selectable at checkout. Stated purpose: "minimize confusion and order mix-ups during peak hours".
- **Square "order ready" text** **[EXCERPT]** (community.squareup.com thread 252786): staff mark the order ready and an SMS goes to the number entered at checkout. A separate community thread (657488) asks how to show the order number on a TV/screen when ready; the snippet does not show an official answer. Third-party app "TablesReady" exists on the Square marketplace for notifying customers **[EXCERPT]**.
- **me&u** **[SOURCED]** (meandu.com blog "Multi Vendor Ordering", dated 2022-11-21, so older than the 2023+ preference): guest orders and pays on their phone; order lands on the vendor's live order screen and prints to the POS printer; **with counter pickup the vendor can send an SMS when items are ready**. Another me&u page **[EXCERPT]** describes "app-free" QR ordering with payments.
- **Sunday** **[EXCERPT]** (sundayapp.com/order-and-pay): guests scan a QR at the table, split or pay the bill on their phones and tip. This is table-service oriented. Counter-pickup specifics: **[NOT FOUND]**.
- **Starbucks Mobile Order & Pay** **[EXCERPT]**: the order is placed and **paid ahead in the app**, then picked up; a Reddit thread **[ANECDOTAL]** confirms a "Your order is ready" push notification exists. A Facebook fan-group post **[ANECDOTAL]** says (date unclear) orders are made in the order placed rather than by when the customer arrives. Starbucks press release **[EXCERPT]** (about.starbucks.com/press/2026) says scheduled ordering lets customers choose a pickup time. Starbucks UAE page **[EXCERPT]** confirms pay-ahead and "Pickup".
- Tim Hortons app, Mr Yum, Toast pay-later behaviour: **[NOT FOUND]** (Toast search returned only social posts).
- What happens when a guest does not pay online (staff confirm, then release to kitchen): **[NOT FOUND]** in vendor docs I could read. Square's flow avoids the problem by requiring online payment.

## 3. Order number conventions (Q3)
**[NOT FOUND]** from sources (search was rate-limited). The Square kiosk page only shows that "generated order numbers" exist. Everything below is **[INFERENCE]**:
- Short numeric or letter+digit tokens (e.g. `A042` or just `42`) are common in counter service; reset daily per venue so numbers stay short and unambiguous at the counter.
- A "Preparing" / "Ready" two-column board is the usual screen pattern.
- A prefix letter can separate channels (counter vs QR vs table) and avoids collisions when several channels share one counter.

## 4. Kitchen/barista ticket conventions (Q4)
**[NOT FOUND]** for 3–5 minute coffee targets and ticket layout. Only Square's KDS/ticket printer routing is sourced (see Q2). **[INFERENCE]**: the ticket should show the order number large, guest name if given, an unmistakable PICKUP / DINE-IN (For Here / To Go) flag, items with modifiers, and elapsed time since the order was accepted.

## 5. Abuse and edge cases (Q5)
- Vendor documentation on fake/unpaid QR orders: **[NOT FOUND]**.
- Square's QR design sidesteps it: pay online before the order reaches the kitchen **[SOURCED]**, plus the ability to switch intake off. An optional alcohol limit per order exists **[SOURCED]**.
- **[INFERENCE]**, mitigations for a pay-at-counter path: (a) new unpaid orders enter a "awaiting payment" state and do NOT reach the bar/KDS until staff press "Paid / Accept"; (b) auto-expire unconfirmed orders after N minutes; (c) rate-limit per device/session; (d) show the order number to the guest so the cashier can find it; (e) cancel reasons logged (guest left, wrong order, test).

## 6. Pakistan payments (Q6)
- **Raast QR** **[SOURCED]** (jazzcash.com.pk/business/accept-payments/qr-raast-payments): merchants accept instant payments from any bank app or wallet in Pakistan by customers scanning a QR; funds credit the merchant's JazzCash Business account in real time; also supports Till ID. So scan-to-pay at a counter is technically available to small merchants.
- **[EXCERPT]** LinkedIn post (linkedin.com/posts/aamiraftab..., c. Nov 2025): JazzCash "expands digital payment acceptance to 700,000 merchants" and enables Raast QR for cash and card on delivery orders. Figures come from a promotional post; treat as unverified.
- JazzCash social posts show Raast QR promoted for Eid/Qurbani payments **[ANECDOTAL/promo]**.
- Cash share of café sales, card POS penetration in Lahore/Islamabad/Karachi cafés, Easypaisa specifics: **[NOT FOUND]**.
- Realistic demo without a gateway: **[INFERENCE]**. We cannot integrate a real gateway (free-only). Honest options are (1) "pay at counter" as the default, with a staff "mark paid" action (cash/card/Raast QR scan done outside the app), and (2) at most a clearly labelled **simulated** online payment for demo purposes. A real Raast QR requires merchant onboarding; showing one would imply a working payment, so do not.

## Gaps for follow-up (not researched or blocked)
Chain-level practice in Pakistan, vendor behaviour for unpaid QR orders (Toast, Lightspeed, Oscar POS, Blinkco), order number format surveys, coffee ticket-time targets, cash share statistics (State Bank of Pakistan reports), Dawn/Tribune/ProPakistani articles. Searches for the last four were rate-limited (Firecrawl) and not retried.

## Implications for the design
1. Counter/pickup is pay-first by default in the industry (Starbucks pay-ahead, Square QR online payment) **[SOURCED]**; since no real gateway, model it as **pay-at-counter with staff confirmation**, and keep any online "payment" clearly labelled as a demo.
2. State machine: `awaiting_payment` -> `paid/accepted` (releases to kitchen/bar) -> `preparing` -> `ready` -> `collected`, plus `cancelled`/`expired`. Unpaid orders never appear on the bar queue **[INFERENCE]**.
3. Guest sees a short per-venue, daily-resetting order number (e.g. letter + 3 digits) and optionally a first name; staff can find the order by number **[INFERENCE]**.
4. Ready notification: in-page status for the guest plus a "Ready" board; SMS/push are out of scope (no provider, free-only), name/number calling at the counter is the fallback (Square supports name, table number, or order number **[SOURCED]**).
5. Ticket/KDS shows order number large, name, PICKUP vs DINE-IN, items, elapsed timer **[INFERENCE]**.
6. Fulfilment type at checkout: For Here / To Go (Square wording **[SOURCED]**); table number only for dine-in.
7. Owner can pause QR intake (Square has an "Accept QR code orders" toggle **[SOURCED]**) and set ordering hours in the venue's time zone **[SOURCED]**.
8. Do not claim anything about Pakistani café practice in README or docs until the gaps above are filled; keep wording to what is implemented.
