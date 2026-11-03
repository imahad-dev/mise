# Pakistan restaurant payments, tax and invoicing (research notes, compiled 2026-10-22)

Scope: what a demo restaurant product needs to model payments and bills realistically for Pakistan without claiming tax compliance. Research budget was limited (about 15 lookups). Where only news or vendor sources exist, that is stated. **Nothing here is tax advice. Re-verify every rate against the authority's own notification before showing it as fact.**

## Payments: methods in use, SBP initiatives, recording practice, merchant fees

### Takeaway
Raast P2M (interoperable QR, free for payers) has been live since late 2023 and was the fastest-growing merchant channel through FY25. Cards over bank POS terminals are the other main digital channel. Provincial tax rules now give restaurants a strong reason to separate digital payments (card, wallet, QR) from cash on every bill, because the tax rate depends on the payment method. I found no reliable figure for each method's share of restaurant payments, and no source for MDR (merchant fee) levels.

### Cited Findings
- SBP launched the interoperable **Raast P2M** service. It accepts QR code, Raast alias (e.g. mobile number), IBAN and Request-to-Pay. Banks, MFBs and EMIs had to enable P2M in app, internet banking and USSD channels by **1 March 2024**. Merchant acquirers had to integrate so their merchants could accept Raast P2M by **31 March 2024**. Regulated entities may **not charge the paying customer** any fee for Raast payments. — [SBP PSD Circular No. 4 of 2023](https://www.sbp.org.pk/psd/2023/C4.htm); [Business Recorder](https://www.brecorder.com/news/40276991/digital-payments-sbp-launches-raast-p2m-service)
- Raast merchant service providers onboard merchants after due diligence and deploy QR codes to SBP's specification. I found **no restaurant-specific QR mandate** from SBP. — [SBP PSD Circular No. 4 of 2023](https://www.sbp.org.pk/psd/2023/C4.htm)
- FY25 (Jul 2024–Jun 2025): 838,856 of 1,092,044 QR-enabled merchants were using Raast P2M QR to accept payments, up from 516,317 the year before. The POS network reached 195,849 terminals at 159,284 merchant locations, with almost 1 million card payments a day. — [SBP Annual Payment Systems Review FY25](https://www.sbp.org.pk/assets/document/publications/Annual-Payment-Systems-Review-FY25.pdf); [Profit](https://profit.pakistantoday.com.pk/2025/11/03/sbp-releases-annual-payment-systems-review-for-fy25/)
- Raast handled 2.76 billion payments in FY26 (secondary report on the FY26 review; I did not verify it against SBP's text). — [Pakera](https://pakera.pk/raast-2-76-billion-payments-fy26-sbp-payment-systems-review/)
- P2M uptake has been described as slow in major markets. — [Express Tribune](https://tribune.com.pk/story/2592641/p2m-uptake-slow-in-major-markets)
- One bank's merchant page states **0% MDR** on the Raast P2M scheme. This is a single bank FAQ, not an SBP rule. — [Bank Alfalah Raast P2M QR](https://www.bankalfalah.com/business-banking/retail-payment-solution/raast-p2m-qr/)
- A 2026 article claims SBP enforced a "Unified Raast P2M Interoperable QR Standard" with one EMVCo QR per merchant. It cites no SBP circular. **Treat as unverified.** — [NextGen.pk](https://nextgen.pk/news/sbp-unified-raast-qr-standard-gcc-buna-cross-border-bridge-2026)
- Tax rules tie the rate to payment method: in Punjab, Sindh and ICT, debit card, credit card, mobile wallet and QR payments get a lower restaurant rate than cash (see the tax section). — [Geo fact-check](https://www.geo.tv/latest/673313-true-punjab-has-increased-sales-tax-on-restaurant-bills-paid-by-card-to-8); [Profit (ICT)](https://profit.pakistantoday.com.pk/2025/07/02/hotels-marriage-halls-beauty-parlours-and-professional-services-in-islamabad-capital-territory-to-face-15-sales-tax/)
- The FBR POS invoice must record **"mode of payment, cash or credit card"**. — [FBR POS Booklet, Sales Tax Rule 150ZEB(5)](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf)
- A Tier-1 retailer is defined to include any retailer that has acquired a card or digital-payment POS from a bank or an SBP-authorised provider. Taking card payments therefore pulls a retailer into FBR integration. — [FBR POS Booklet, s.2(43A)(f) Sales Tax Act](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf)
- KP's Finance Act 2026 penalty table reportedly includes Rs 50,000 or 10% of the amount for business payments not made or received through the business bank account (secondary source). — [Pakera](https://pakera.pk/kpra-penalties-late-return-default-surcharge-finance-act-2026-khyber-pakhtunkhwa/)

### Inferences
- A realistic payment model has these method values: `cash`, `card` (debit or credit, via a bank POS terminal), `wallet` (JazzCash, Easypaisa and similar), `raast_qr` (Raast P2M QR or alias), and possibly `bank_transfer` (IBFT). The tax engine needs one more derived flag, `digital: true/false`, because provinces tax by "card / wallet / QR" versus "cash and others".
- **Split payments complicate the tax.** If a bill is part cash and part card, the rate depends on the method, so the tax on the bill depends on the split. None of the sources says how authorities treat mixed-tender bills. The safest demo approach is one of two: tax each payment portion at its own method's rate, with a visible "illustrative" label, or allow only one tender per bill for tax purposes. Document whichever you choose as an assumption.
- Store a reference number per digital payment: the RRN or approval code for cards, the Raast transaction ID or STAN, or the wallet transaction ID. For cash, store tendered amount and change. For end-of-day close, compare expected cash (sum of cash payments minus change) with the counted drawer, and match digital totals against the acquirer or wallet settlement. This is standard POS practice; I found no Pakistan-specific source for it.

### Gaps
- No reliable 2024–2026 share of restaurant payments by method (cash vs JazzCash vs Easypaisa vs Raast vs card vs IBFT). SBP publishes economy-wide channel data, not data by sector.
- No sourced card MDR or wallet merchant fee levels for Pakistan, apart from the single Bank Alfalah 0% Raast claim.
- No source on how restaurants in Pakistan actually record split bills, partial payments or cash reconciliation.
- No confirmed SBP circular from 2025–2026 that mandates QR acceptance by merchants or restaurants.

## FBR POS integration and invoice requirements (federal; ICT restaurants and Tier-1 retailers)

### Takeaway
Under Sales Tax Rules 2006 Chapter XIV-A (rule 150ZA), registered restaurants, cafés, coffee shops, eateries, snack bars and hotels must install FBR-approved fiscal devices or software and register each POS. They must print an FBR fiscal invoice number and QR code on the bill, and must show prices and tax separately on menus. Penalties for fake or QR-less invoices start at Rs 500,000 or 200% of the tax involved, whichever is higher, and premises can be sealed. Customers verify invoices through the Tax Asaan app.

### Cited Findings
All of the following are from the [FBR POS Booklet (legal provisions, updated 18.09.2023)](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf), which compiles the Sales Tax Act 1990 and Sales Tax Rules 2006:
- **Rule 150ZA**: Chapter XIV-A applies to registered restaurants, cafés, coffee shops, eateries, snack bars and hotels with those activities. Under **rule 150ZB(1)–(2)** they must install an FBR-approved fiscal electronic device or software and register every branch and every POS, with POS registration number, business name, branch name and address, POS ID and registration date.
- **Rule 150ZB(4)**: all restaurants, bakeries, caterers and sweetmeat shops must **show prices and the amount of tax separately on menu cards or menu boards**.
- **Rule 150ZEB(5)** sets the data each POS invoice must carry:
  - POS registration number
  - unique sequential invoice number
  - date and time of sale
  - buyer name where recorded
  - item-wise description and price exclusive of tax
  - item-wise quantity
  - tax rate per item
  - total sales value
  - discount
  - tax charged
  - mode of payment (cash or card)
- **Rule 150ZEB(6)** sets the extra items printed on the invoice: QR code generated from the FBR fiscal invoice number, the FBR fiscal invoice number, business name, sales tax registration number, and outlet name or location.
- Process: the POS sends each sale to FBR's sales data controller, which returns the fiscal invoice number. The POS then prints the fiscal invoice with that number and the QR code.
- **Rule 150ZEB(17)**: each outlet must display a signboard with the FBR logo, the text "Integrated with FBR" and each POS registration number. **This is exactly the kind of claim a demo must not copy.**
- **Rule 150ZEG**: FBR provides a facility for customers to verify that an invoice reached FBR, and to upload unverified invoices. **Rule 150ZEO(2)** names the **"Tax Asaan" application** or POS Dashboard as a source for reporting unverified invoices, which can lead to sealing.
- **S.R.O. 1279(I)/2021** levies a POS service charge of **Rupee one per invoice** issued through integrated POS. It is collected from the customer and deposited with the monthly return.
- **Sales Tax Act s.33 (item 24)**: issuing an invoice without the prescribed invoice number or QR code, or with a duplicate or counterfeit one, carries a penalty of **Rs 500,000 or 200% of tax involved, whichever is higher**. On conviction it can also bring up to 2 years' simple imprisonment and a fine of up to Rs 2 million, and premises can be sealed.
- For a **notified Tier-1 retailer that does not integrate**, penalties escalate:
  - Rs 500,000 for the first default
  - Rs 1 million for the second
  - Rs 2 million for the third
  - Rs 3 million for the fourth, each at 15-day intervals
  - sealing if default continues

  The first-default penalty is waived if the retailer integrates before the second-default penalty. Under s.8B(6), input tax is reduced by 60% for non-integration.
- **S.R.O. 1006(I)/2021** standardises the invoice format. It is referenced in the booklet; field details were summarised from secondary sources. The format requires business STRN and NTN, POS registration number, a unique sequential invoice number, the FBR fiscal invoice number, the FBR POS logo and a verifiable QR code (7x7 mm). Buyer name is needed when the invoice exceeds Rs 100,000. — [BOL News](https://www.bolnews.com/latest-news/fbr-makes-information-mandatory-for-valid-pos-invoices/); [ProPakistani 2021](https://propakistani.pk/2021/08/09/fbr-now-requires-name-of-the-buyer-from-retailers-if-invoice-is-over-rs-100000/)
- The fiscal invoice number format is shown as `XXXXXX-DDMMYYHHMMSS-0001` in the official booklet, according to a search summary. Third-party guides give different formats. — [WoBooks](https://wobooks.com/post/fbr-pos-integration-step-by-step-guide-for-pakistani-retailers-2026); [BACO Consultants](https://bacoconsultants.com/blogs/fbr-pos-integration-tier-1-retailers-2026)
- Enforcement example: RTO Islamabad sealed five restaurants and imposed Rs 1.5 million in total penalties for fake receipts. In another case, two Islamabad restaurants were fined Rs 0.5 million each after receipts were found inauthentic through POS tracking (2024 reports). — [The News](https://www.thenews.com.pk/print/1253758-fbr-seals-five-restaurants-for-issuing-fake-receipts); [The News](https://www.thenews.com.pk/print/1244753-fbr-seals-two-restaurants-over-fake-invoices)

### Inferences
- **Do not generate anything that looks like an FBR fiscal invoice number, an FBR QR code or the FBR POS logo**, even as mock data. Counterfeit or duplicate fiscal numbers and QR codes are the specific offence in s.33 item 24. A demo bill should carry only its own internal bill number, clearly labelled.
- Rule 150ZB(4) (tax shown separately on menus) supports a demo design that shows the net price plus a tax line, rather than tax-inclusive prices only.

### Gaps
- I could not confirm whether the booklet (2023) is fully current as of late 2026, or what changes FBR's separate 2025–2026 "digital invoicing" regime makes for restaurants.
- I could not read the full text of S.R.O. 1006(I)/2021 (the PDF section was not extracted in detail).

## Provincial and ICT sales tax rates on restaurant services (2025–2026)

### Takeaway
Rates differ by jurisdiction and, in Punjab, Sindh and ICT, by payment method. Current best-sourced figures, all to be re-verified, are below.

| Jurisdiction | Cash rate | Card, wallet or QR rate | Effective from | Confidence |
|---|---|---|---|---|
| Punjab | 16% | 8% (was 5% in FY2025-26) | 1 July 2026 | Medium (news and fact-check only) |
| Sindh | 15% | 8% | FY2024-25 onward | Medium (2026 status unverified) |
| ICT | 15% | 5% | 1 July 2025 (structure since Finance Act 2023) | Medium |
| Balochistan | 4% on food services (raised from 2%) | No card rule found | Finance Act 2026 | Low (single APP report) |
| KP | Not found | Not found | — | Do not show a figure |

### Cited Findings
- **Punjab (PRA), FY2026-27**: the card, wallet and QR rate for hotels and restaurants rose from **5% to 8% effective 1 July 2026** under the Punjab Finance Act 2026. Cash and other methods remain at **16%**. PRA spokesman Talha Malik said Punjab previously charged 5% "whereas the rate in the other provinces was 8%". — [Geo fact-check, updated 16 Jul 2026](https://www.geo.tv/latest/673313-true-punjab-has-increased-sales-tax-on-restaurant-bills-paid-by-card-to-8); [Profit, 1 Jul 2026](https://profit.pakistantoday.com.pk/2026/07/01/punjab-increases-restaurant-sales-tax-on-digital-payments-to-8percent-from-today); [ProPakistani, 3 Jul 2026](https://propakistani.pk/2026/07/03/punjab-increases-restaurant-card-payment-tax/)
- Punjab FY2025-26 (now superseded) was 5% for debit card, credit card, wallet and QR, and 16% otherwise. — same sources as above
- The PRA directed businesses to update invoicing and billing systems. — [ProPakistani](https://propakistani.pk/2026/07/03/punjab-increases-restaurant-card-payment-tax/)
- A practitioner blog says the reduced rate is "without input tax adjustment". It also claims that from a 2 July 2026 notification, banks deduct the tax on digital payments for listed services. Both are single secondary claims and unverified. — [Faubix](https://einvoicing.faubix.com/blog/pra-punjab-sales-tax-changes-2026)
- Restaurants in Punjab must issue invoices through PRA's e-IMS system, reportedly including those with monthly sales up to Rs 500,000. This comes from a search summary; I did not fetch the primary source. — [TechJuice](https://techjuice.pk/pra-exposes-massive-tax-fraud-at-restaurants-in-four-cities)
- **Sindh (SRB)**: the standard rate is **15%**. Restaurant services paid by debit card, credit card, mobile wallet or QR are reduced to **8%**. Restaurants may apply for a dispensation to keep charging 15% on digital payments with input tax adjustment, but only for branches whose POS is integrated with SRB. — [Express Tribune](https://tribune.com.pk/story/2482253/15-service-tax-reinstated-on-card-payments-at-restaurants-in-sindh); [ProPakistani 2024](https://propakistani.pk/2024/07/23/sindh-increases-tax-on-card-payments-at-restaurants-cafes/amp); [SRB restaurant list page](https://www.srb.gos.pk/srb/other-services/) (could not fetch: certificate error)
- The Sindh Finance Bill 2025 kept restaurants at the 8% reduced rate and the standard rate at 15%. — [PwC / A.F. Ferguson Sindh Finance Bill 2025 memo](https://www.pwc.com.pk/en/tax-memorandum/AFFsTaxMemorandumonSindhFinanceBill2025.pdf)
- **Conflict on the Sindh dispensation list**: reports describe 58 Karachi establishments allowed to charge 15% on digital payments, and another report frames the same list the other way round. The Pakistan Tax Bar Association (July 2025) cited 73 restaurants. — [Geo](https://www.geo.tv/latest/555650-karachis-58-restaurants-authorised-to-collect-nearly-double-service-tax); [Profit](https://profit.pakistantoday.com.pk/2025/07/18/pakistan-tax-bar-association-accuses-sindh-revenue-board-of-creating-disparity-in-digital-payment-at-restaurants)
- **ICT (FBR, ICT Tax on Services Ordinance 2001)**: restaurants (including cafés, ice cream parlours, coffee shops, food huts and similar) pay **5% for debit/credit card or QR payments, without input tax adjustment**, and **15% for cash**, from 1 July 2025. The dual structure dates from the Finance Act 2023. — [Profit, 2 Jul 2025](https://profit.pakistantoday.com.pk/2025/07/02/hotels-marriage-halls-beauty-parlours-and-professional-services-in-islamabad-capital-territory-to-face-15-sales-tax/); [ProPakistani](https://propakistani.pk/2025/07/02/fbr-imposes-15-gst-on-marriage-halls-hotels-clubs-farmhouses-in-islamabad/)
  - **Conflict**: the PRA spokesman's July 2026 statement that "other provinces" charge 8% does not match ICT's 5% card rate. Either ICT changed in the Finance Act 2026 (not found) or the statement refers to provinces only.
- **Balochistan (BRA)**: a July 2026 APP report says the Finance Act 2026 raised the rate on food services (restaurants, hotels, cafés) from **2% to 4%**. BRA told providers to use POS systems. I found no card or cash differential. — [APP](https://www.app.com.pk/?p=1247386)
- **Khyber Pakhtunkhwa (KPRA)**: I found no authoritative current rate for restaurants.
  - A 2024 draft regulation says restaurants charge the Second Schedule rate and may display tax-inclusive prices only if the menu, price list and invoice say so. — [KPRA draft STS Regulations 2024](https://kpra.gov.pk/wp-content/uploads/2024/04/Draft-KP-STS-Regulations-2024.pdf)
  - Secondary sources cite a standard rate of 15–16% and reduced rates (e.g. 1% for dhabas). These conflict and look outdated. — [TaxationPK](https://taxationpk.com/insights/a-guide-to-tax-rates-in-khyber-pakhtunkhwa-kpra/)
  - The Finance Act 2026 penalty table reportedly sets Rs 500,000 or 5% of tax for restaurants that fail to install RIMS, IMRS or e-invoicing. — [Pakera](https://pakera.pk/kpra-penalties-late-return-default-surcharge-finance-act-2026-khyber-pakhtunkhwa/)

### Inferences
- Model the tax rate as data keyed by (jurisdiction, payment class, effective_from), never hard-coded. Show it as "sample rate as of {date}, source {link}". Rates changed on 1 July in both 2025 and 2026, which matches Pakistan's fiscal year, so expect yearly changes.
- For the demo, choose one jurisdiction (e.g. Punjab), apply its two-tier rate, and label it illustrative.

### Gaps
- No official PRA, SRB, KPRA, BRA or FBR notification text was fetched for the 2026 rates. Punjab's figures rest on news and a fact-check quoting PRA; the SRB site failed TLS.
- I could not confirm whether Sindh or ICT changed restaurant rates in their Finance Acts 2026.
- KPRA restaurant rate for 2025–2026 is unknown.
- Details of SRB and PRA e-invoicing integration (APIs, invoice fields) were not researched.

## Mandatory bill fields, service charge, and safe wording for a demo

### Takeaway
A realistic sample bill shows:
- business name and address
- NTN and provincial or federal registration number
- a sequential bill number
- date and time
- item lines with prices excluding tax
- tax rate and tax amount
- discount
- total
- payment mode

It must not show an FBR or provincial fiscal number, a QR code or a logo. I found no source on how service charge is taxed.

### Cited Findings
- Federal POS invoice content (rule 150ZEB(5)–(6)) is listed in the FBR section above. — [FBR POS Booklet](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf)
- Restaurants must show prices and tax separately on menus (federal rule 150ZB(4)). In KP, the draft rules allow tax-inclusive prices only when the menu, price list and invoice say so. — [FBR POS Booklet](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf); [KPRA draft 2024](https://kpra.gov.pk/wp-content/uploads/2024/04/Draft-KP-STS-Regulations-2024.pdf)
- Integrated outlets must display "Integrated with FBR" signage with the FBR logo (rule 150ZEB(17)). Integration is a legal status earned through FBR registration and accreditation of the POS. — [FBR POS Booklet](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf)
- POS systems must be accredited by FBR (rule 150ZEC). FBR publishes the accredited brand, model and specification. — [FBR POS Booklet](https://download1.fbr.gov.pk/Docs/2023919991847265Point-of-Sale(POS)-Booklet-(LegalProvision)-updated-18.09.2023.pdf)
- PRA has fined restaurants that charged customers sales tax that was never declared. Showing a "sales tax" line on a bill therefore has real-world weight. — [Profit 2020](https://profit.pakistantoday.com.pk/2020/09/04/pra-cracks-down-on-restaurants-violating-tax-laws); [TechJuice](https://techjuice.pk/pra-exposes-massive-tax-fraud-at-restaurants-in-four-cities)

### Inferences
- **The product must not claim** any of the following:
  - "FBR integrated" or "Integrated with FBR"
  - "FBR accredited POS"
  - "PRA / SRB / KPRA / BRA compliant" or "e-invoicing ready"
  - "Tax Asaan verifiable"
  - "valid sales tax invoice"
  - "fiscal invoice"

  It must not print anything resembling an FBR fiscal invoice number, an FBR or PRA QR code, the FBR POS logo or the Re 1 POS fee line. It also must not imply the rates shown are current law.
- **Safe wording**:
  - On the bill: "Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority."
  - Near the tax line: "Tax shown is illustrative, using {jurisdiction} rates as published on {date}; verify with the revenue authority."
  - For the bill number: "Bill no." (internal), not "Invoice no." or "FBR invoice".
- **Service charge**: model it as a separate line with an explicit, configurable flag for whether it is in the taxable base. Default it to taxable (included) and label that as an assumption, because no source was found.

### Gaps
- No source found on whether restaurant service charges or tips are part of the taxable value under PRA, SRB, KPRA, BRA or the ICT ordinance.
- No source found on mandatory fields for PRA or SRB restaurant invoices specifically, as opposed to FBR's federal rules.
- NTN/STRN display rules for provincial registrations (e.g. PNTN for PRA) were not confirmed.
