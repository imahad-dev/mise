# Pakistan restaurant operations, WhatsApp, devices and connectivity

Research date: 2026-10-22. About 16 tool calls. Many front-of-house details (KOT language, café token systems, staff WhatsApp groups) have no good written sources. Those details are under Inferences or Gaps and are marked ANECDOTAL/UNSOURCED. Do not present them as fact.

## Desi family restaurant service flow (order taking, KOT, billing, service charge, tipping, parcel, delivery)

### Takeaway
Pakistani POS vendors describe the standard flow: an order is linked to a table, then routed by item type to a kitchen printer, a KDS or a prep station. Menus price karahi by half/full or by weight (500g / 1kg). Raita and salad are often separately priced items. Formal restaurants commonly add a ~10% service charge, and casual places get a rounded-up tip. Restaurants run their own motorbike riders for delivery and resent aggregator commissions.

### Cited Findings
- Dine-in orders are linked to a table. Once submitted, the POS sends them to a KDS, a kitchen printer or the relevant prep station, routed by item type (drinks to the beverage counter, grill items to the grill, desserts to dessert). Payment methods listed: cash, debit/credit cards, QR payments, mobile wallets, bank transfers. Vendor marketing, undated. — [Oscar POS blog](https://oscar.pk/blog/how-does-a-restaurant-pos-system-work-in-pakistan)
- Per-item mapping to KOT printers (for example, one cuisine's items print at that station's printer) is a standard setup. KOT printing normally runs on the local network between the billing terminal and the kitchen printer or KDS. Indian/generic vendor docs, not Pakistan-specific. — [PosBytz help](https://help.posbytz.com/en/article/kot-mapping-and-setup-13b87c2/); [Petpooja glossary](https://blog.petpooja.com/glossary/digital-kot/)
- Pakistani POS must handle GST compliance, cash plus digital wallets, and possibly Foodpanda integration. Vendor blog. — [Hysabone](https://blog.hysabone.com/?p=66)
- FBR directed restaurants, hotels, guest houses and marriage halls to integrate their POS with FBR from 1 July 2024. — [ProPakistani, Mar 2024](https://propakistani.pk/2024/03/22/fbr-directs-number-of-businesses-including-educational-institutions-hospitals-to-integrate-with-pos-system/amp/)
- FBR installed POS at 40,000 retail outlets in FY2024-25, about 38% of Tier-1 retailers, so coverage is partial. — [Profit](https://profit.pakistantoday.com.pk/?p=216834)
- Vendor guides describe an FBR invoice number and a verification QR on each receipt. This is a secondary description, so check it against FBR technical docs. — [Medium/BTC vendor post](https://btcpk.medium.com/fbr-integrated-pos-software-73c3647cc251)
- Portions on delivery-app menus: chicken karahi sold half/full (from Rs 1,150, Sahiwal). Desi chicken karahi sold by weight: 1kg Rs 1,350, 500g Rs 1,050. Salad and raita each Rs 90. A half-karahi deal bundles 5 roti + raita + salad for Rs 1,300. Listings undated, seen 2026. — [Foodpanda: Hafiz Food Corner](https://www.foodpanda.pk/restaurant/k3mn/hafiz-food-corner-sahiwal); [Foodpanda: Herry Khichen](https://www.foodpanda.pk/restaurant/azi5/herry-khichen)
- Service charge and tips: formal hotels and restaurants typically add a 10% service charge. In low/mid-end restaurants the bill is rounded up to the nearest Rs 100/1,000 and the change is left as a tip. Secondary source. — [Wikipedia tipping list](https://en.wikipedia.org/wiki/List_of_tipping_customs_by_country)
- Restaurateurs (2019) said a minimum 10% tip is expected, and one suggested 14–16%. — [Dawn Images](https://images.dawn.com/news/1178376)
- A 2018 column says only about half of a service charge typically reaches staff. Opinion piece. — [Express Tribune](https://tribune.com.pk/article/14333/ginsoys-ridiculous-service-charge-and-social-medias-wonders?amp=1)
- Own-rider delivery: in 2020 the All Pakistan Restaurant Association organised a boycott of ~200 eateries over Foodpanda raising commission from 18% to 35%. Foodpanda had demanded restaurants stop using their own riders. Restaurants wanted to deliver Foodpanda orders with their own riders and to get customer data. — [Dawn 2020](https://www.dawn.com/news/amp/1580703); [Profit](https://profit.pakistantoday.com.pk/?p=101301)
- Commissions ranged from ~8% for multinational chains to 35%+ for small eateries. Own delivery is cheap because of cheap labour, cheap motorbike fuel and minimal rider insurance requirements (2020). — [Dawn 2020](https://www.dawn.com/news/amp/1580703)

### Inferences
- A KDS should support per-station routing (tandoor, karahi/handi, BBQ, drinks/juice) as the default model, mirroring printer-per-station KOT.
- Portion must be a first-class modifier (half/full, 500g/1kg, per-piece roti/naan). Raita, salad and naan are billable line items, not free sides. Deals/combos are common.
- Service charge should be a configurable % (default 0, often 10%) shown separately from tax. Tip should be optional/rounding.
- Order channels need dine-in, parcel/takeaway and own-rider delivery tags.
- ANECDOTAL/UNSOURCED (general knowledge, not verified in this session): waiters mostly take orders on paper pads in mid/low-tier desi places. Fresh roti/naan is typically sent in rounds from the tandoor rather than all at once. Families are seated in a separate "family hall/section" in many traditional places. The bill is usually brought to the table on request, and payment happens at the table (cash in a folder) or at the counter. Mineral water and cold drinks (Pepsi/Coke, 1.5L bottles for families) are ordered and charged separately. Treat all of these as hypotheses to validate with restaurant interviews.

### Gaps
- No sourced data on paper pad vs handheld order-taking prevalence, family hall norms, fresh-naan sequencing, or pay-at-table vs pay-at-counter split.
- No authoritative current provincial sales tax rate for restaurants (PRA/SRB/ICT). One vendor blog says 13–16%, but that is unverified.
- No 2024–2026 data on Foodpanda commission or on the share of restaurants using their own riders.
- Service charge legality/regulation was not found.

## Café/coffee spot flow (counter ordering, tokens, stations, peaks)

### Takeaway
Coffee is still niche compared with tea, but third-wave cafés are growing in Lahore, Karachi and Islamabad. Cafés act as hang-out spaces where customers linger. No written source describes token/buzzer or name-calling practice.

### Cited Findings
- Pakistan consumes about 735 cups of tea per cup of coffee (2024 import data). Coffee is "a very niche phenomenon." — [Profit, "Coffee nation"](https://profit.pakistantoday.com.pk/?p=203904)
- Coffee arrived in "three waves". Lahore's Third Culture Coffee is cited as third-wave (2023). — [Profit 2023](https://profit.pakistantoday.com.pk/2023/11/05/is-coffee-pakistans-cup-of-tea)
- Lahore café owners say cafés encourage people to stay, unlike restaurants. Customers are largely students and young professionals. Long queues form for iced drinks in summer at Tim Hortons. — [The Standard](https://thestandard.com.pk/the-third-space/)

### Inferences
- The café mode should support counter-order + pay-first + order number/name-called pickup, plus optional table service. Barista (drinks) and kitchen (food) are separate KDS stations.
- Long dwell times mean guests may add orders to an open tab/session over time.
- ANECDOTAL/UNSOURCED: chains (Tim Hortons, Gloria Jean's) use counter order and name-called pickup. Smaller cafés often do table service. Evening and late-night peaks (after ~8pm, later on weekends) are common in Pakistani cities.

### Gaps
- No sourced data on buzzer/token usage, peak hours or café staffing models.

## Kitchen ticket format (language, naming, modifiers, printer widths)

### Takeaway
Nothing specific to Pakistan was found. The only sourced material is generic KOT routing.

### Cited Findings
- A KOT is the slip (paper or digital) telling the kitchen what to prepare, for which table, and with what modifications. — [Petpooja glossary](https://blog.petpooja.com/glossary/digital-kot/)
- Pakistani vendor pages list "receipt printer" and "kitchen printer" without paper widths. — [Oscar POS](https://oscar.pk/blog/how-does-a-restaurant-pos-system-work-in-pakistan)

### Inferences
- ANECDOTAL/UNSOURCED: menus and KOTs in Pakistan are typically English or Roman-Urdu item names ("Chicken Karahi Half", "Seekh Kabab", "Roghni Naan"). Modifiers are in Roman Urdu ("kam mirch", "boneless", "extra makhan", "tez mirch"). 80mm thermal printers are the norm at restaurants, with 58mm at small outlets and handheld/Bluetooth printers. Design the KDS with short item names, large type, portion as a prominent badge, and free-text modifiers that allow Roman Urdu.

### Gaps
- No source on KOT language, Urdu-script use or thermal printer width prevalence in Pakistan. Validate with local POS vendors or by photographing real KOTs.

## Order-of-service conventions (fresh roti later, sides, water, drinks)

### Takeaway
The only sourced point is that raita, salad and roti are sold as separate or bundled items on menus. Sequencing conventions are unsourced.

### Cited Findings
- Raita and salad are priced separately (Rs 90 each). Combo deals bundle roti, raita and salad. — [Foodpanda: Herry Khichen](https://www.foodpanda.pk/restaurant/azi5/herry-khichen); [Foodpanda: Hafiz Food Corner](https://www.foodpanda.pk/restaurant/k3mn/hafiz-food-corner-sahiwal)

### Inferences
- Support "fire later / send in rounds" for tandoor bread, and repeat-item quick-add ("2 more naan") from the guest QR flow.

### Gaps
- No source for "fresh naan sent later" or for free-vs-paid raita/salad norms at dine-in (delivery menus may differ from dine-in).

## Role of WhatsApp (ordering, bills, staff coordination, catalogs, API cost)

### Takeaway
WhatsApp is widely used for direct ordering, but sourcing on it is mostly vendor marketing. The WhatsApp Business Platform charges per message since 1 July 2025, and Pakistan utility/auth rates rose from 1 April 2026. Free service-window replies make it feasible for low volume, but it needs a BSP/Meta setup. That conflicts with this project's free-only policy, so for a demo, wa.me deep links (free) are the realistic option.

### Cited Findings
- Meta moved to per-message pricing for template messages from 1 July 2025. Utility templates sent inside an open customer-service window are free. Messages are free for 72h within a free-entry-point window. Volume tiers lower utility/auth rates. — [Meta WhatsApp pricing docs](https://developers.facebook.com/docs/whatsapp/pricing)
- Meta lists a Pakistan-specific increase in utility and authentication rates effective 1 April 2026. Auth-international rates for Pakistan were lowered from 1 April 2025. — [Meta pricing page](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
- A Salesforce PDF lists Pakistan at 58.4 (marketing) and 12.35 (utility), but gives no currency or date and likely predates 2025. Do not rely on it. — [Salesforce PDF](https://www.salesforce.com/en-us/wp-content/uploads/sites/4/documents/PDF/WhatsApp-Business-Messaging-1000.pdf)
- A white-label ordering vendor pitches WhatsApp direct ordering to Pakistani restaurants and claims aggregators charge 25–30% per order. Vendor claim. — [Deonde](https://deonde.co/pakistan/online-ordering-and-delivery-system.shtml)
- In 2017, patrons were already switching to direct orders and restaurants were approaching customers directly. — [Profit 2017](https://profit.pakistantoday.com.pk/2017/12/18/foodpanda-after-the-highs-hitting-the-proverbial-trough)
- WhatsApp has been subject to national disruptions. In August 2024 a slowdown cut speeds 30–40% (WISPAP) and P@SHA estimated losses of ~$300m. The government blamed an undersea cable fault, while industry blamed a "national firewall". — [Intellinews](https://intellinews.com/pakistan-s-national-firewall-may-lead-to-300mn-in-losses-warns-it-industry-association-339024); [ABC/AP](https://abcnews.go.com/International/wireStory/faulty-undersea-internet-cable-caused-recent-internet-disruptions-113016691)

### Inferences
- For the demo: offer a "share bill/receipt on WhatsApp" via a `wa.me`/share-intent link (no API cost, no personal data sent to us). Do not depend on WhatsApp for kitchen-critical flows.
- ANECDOTAL/UNSOURCED: restaurant staff and owners coordinate in WhatsApp groups. Many restaurants take delivery orders by phone/WhatsApp and post menus as images or WhatsApp Business catalogs.

### Gaps
- No current exact PKR/USD per-message rate for Pakistan was retrieved; read Meta's country rate card directly. No data on WhatsApp Business adoption among Pakistani restaurants.

## Devices and connectivity (smartphones, Android, low-end, data cost, 4G, power cuts, outages)

### Takeaway
Android is about 91% of mobile OS share. Mobile data is among the world's cheapest at ~$0.10–0.12/GB. About 146M 3G/4G subscriptions exist, but internet penetration is only ~46% of people. Phones are mostly locally assembled budget brands, and half of output is still 2G feature phones. Load-shedding of 6–12h/day on high-loss feeders and national internet slowdowns make offline-tolerant, local-first kitchen operation important.

### Cited Findings
- 190M cellular connections (75.2% of population) and 116M internet users (45.7%) in early 2025. 66.9M social media identities. — [DataReportal Digital 2025 Pakistan](https://datareportal.com/reports/digital-2025-pakistan)
- End-2025: 194M cellular connections, 117M internet users (45.6%). — [DataReportal Digital 2026 Pakistan](https://datareportal.com/reports/digital-2026-pakistan)
- PTA, June 2025: 146.05M 3G/4G subscribers (Jazz 54.55M, Zong 42.39M, Telenor 27.67M, Ufone 19.61M). — [PhoneWorld](https://www.phoneworld.com.pk/pakistan-adds-1-38-million-new-3g-4g-users-in-june-2025-pta-report/)
- PTA Annual Report 2024-25: broadband above 150M, penetration above 60%, and 95% of cellular networks on 4G. FTTH above 2M in mid-2025. — [Profit](https://profit.pakistantoday.com.pk/?p=201771)
- Statcounter mobile OS, Pakistan: Android 90.71% / iOS 9.18% (Aug 2026), and Android 91.85% / iOS 8.02% (Jun 2026). — [Statcounter](https://gs.statcounter.com/os-market-share/mobile/pakistan)
- 2025: 30.21M phones locally assembled, meeting 93% of demand. 52% were smartphones (15.64M) and 48% 2G. Top assemblers were Infinix, VGO Tel, Vivo and Itel. Replacement cycle stretched to ~3.5 years. — [Profit](https://profit.pakistantoday.com.pk/?p=203720); [MEA Tech Watch](https://meatechwatch.com/2026/01/22/local-mobile-phone-manufacturing-dipped-in-december-2025-pta/)
- Smartphone share of devices on networks: estimates conflict, 70% vs 48%. — summarised from [Profit](https://profit.pakistantoday.com.pk/?p=203720); [MEA Tech Watch](https://meatechwatch.com/?p=32484)
- Mobile data costs Rs 27/GB (Jul–Dec FY2025) and Rs 34.3/GB (Jul–Dec FY2026), about $0.12/GB, sixth cheapest globally (Economic Survey). — [MEA Tech Watch](https://meatechwatch.com/2025/06/16/pakistan-offers-some-of-the-worlds-cheapest-mobile-data-with-prices-dropping-65-since-2018/); [TechJuice](https://www.techjuice.pk/pakistan-ranks-6th-globally-for-cheapest-mobile-data/)
- Karachi: K-Electric says about 70% of the city is exempt from load-shedding, while the remaining 30% of feeders face 6–10h scheduled cuts. NEPRA data from 620 feeders showed very-high-loss feeders averaging 12h14m daily outages and high-loss feeders 10h39m. NEPRA ordered an end to excess cuts after a Rs 50M penalty (Sep 2026). — [Express Tribune](https://tribune.com.pk/story/2627009/nepra-orders-k-electric-to-end-load-shedding)
- K-Electric asked the government to take over 300 high-loss feeders, which carry 87% of its losses (Jun 2025). — [Profit](https://profit.pakistantoday.com.pk/2025/06/01/k-electric-seeks-government-control-of-300-loss-making-feeders/)
- August 2024 national internet slowdown: speeds down 30–40%, and firms reported 40–80% slower connections. — [Barchart/AP](https://www.barchart.com/story/news/28097817/pakistan-suffers-internet-slowdown-as-government-denies-setting-up-a-national-firewall)
- Vendors still advertise "works without internet" as a traditional-POS selling point. — [Oscar POS](https://oscar.pk/blog/how-does-a-restaurant-pos-system-work-in-pakistan)

### Inferences
- The guest web app must be light (budget Android, Chrome; Infinix/Itel/Tecno class), work on 4G, and keep JS small. iOS still matters for upscale cafés (~9%).
- Many diners (especially older family members) may not have smartphones or data. Waiter-entered orders must remain a first-class path alongside QR.
- Kitchen/KDS should survive internet loss: local-network operation, a UPS for router + KDS + printer, queueing and retrying orders, and a clear "offline" banner. Restaurants usually run generators/UPS during load-shedding (ANECDOTAL), but routers may drop during switchover.

### Gaps
- No 2025 LESCO/Lahore or Islamabad load-shedding hours. No data on restaurant UPS/generator use or on the frequency of restaurant Wi-Fi/ISP outages. Android OS version distribution is unknown.

## Language realities (guests and staff)

### Takeaway
No source was found on kitchen staff English literacy or on Roman Urdu vs Urdu script in restaurants. Everything here is unsourced.

### Cited Findings
- Menus on delivery platforms list items in English/Roman Urdu transliteration ("Chicken Karahi", "Raita", "Roti"). — [Foodpanda listings](https://www.foodpanda.pk/restaurant/k3mn/hafiz-food-corner-sahiwal)

### Inferences
- ANECDOTAL/UNSOURCED: kitchen staff often have limited English reading. Item names are recognised as transliterated words, and spoken Urdu/Punjabi/Pashto/Sindhi is used in the kitchen. Guests at cafés and urban restaurants read English menus. Roman Urdu dominates informal digital text (WhatsApp). KDS should use short, familiar dish names, colour and icons, big numbers for table/portion, and minimal UI words. Note that the project currently supports only `en`/`it` (CLAUDE.md), so adding Urdu would be a scope decision.

### Gaps
- No literacy statistics for restaurant workers. No study on Roman Urdu vs Nastaliq usage in menus or KOTs. Validate through interviews.
