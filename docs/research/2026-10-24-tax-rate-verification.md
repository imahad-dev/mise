# Restaurant sales tax rates — verification against official texts

Checked 2026-10-24. Only primary legal texts count here; news and vendor blogs were used only to
find them.

## Punjab (PRA) — used by Angeethi House, Lahore

| Payment | Rate | From |
|---|---|---|
| Debit or credit card, mobile wallet, QR scanning | 8%, without input tax adjustment | 1 July 2026 |
| Others (cash, bank transfer, anything else) | 16% | 1 July 2026 |

- **Punjab Finance Act 2026 (L of 2026)**, punjablaws.gov.pk/lawspdf//3018.pdf. Section 1(2):
  in force from 1 July 2026. In the Second Schedule, Part III (Reduced Rate Services), S/N 4
  clause (a), the word "Five" is replaced with "Eight".
- **PRA, Punjab Sales Tax on Services Act 2012, 17th edition 2026-2027**,
  pra.punjab.gov.pk/Downloads/THE-PUNJAB-SALES-TAX-ON-SERVICES-ACT-2012-17th-Edition-2026-2027.pdf.
  - Second Schedule Part III, S/N 4, covers restaurants, including cafés, coffee shops, deras and
    eateries.
  - Clause (a) reads "Eight percent without input tax adjustment where payment against services
    is received through debit or credit cards, mobile wallets or QR scanning". Its footnote says:
    substituted for "Five" by the Punjab Finance Act 2026, assented 1 July 2026.
  - Clause (b) reads "Sixteen percent for others".
- Before 1 July 2026 the reduced rate was 5%. A PRA notification of 19 February 2026 still quoted
  5%.

## Islamabad Capital Territory (FBR) — used by Kehwa & Crumb, Islamabad

| Payment | Rate | From |
|---|---|---|
| Debit or credit card, mobile wallet, QR scanning | 5%, no input tax adjustment or refund | Finance Act 2023 |
| Cash | 15% | Finance Act 2023 |

- **ICT (Tax on Services) Ordinance 2001, as amended up to 30-06-2025**,
  download1.fbr.gov.pk/Docs/2025711172945966ICTOUpdatedupto30.06.2025.pdf. Schedule Table-1,
  S/N 1(ii), covers restaurants: (a) five percent for card, mobile wallet or QR; (b) fifteen
  percent where payment is received in cash. The entry was substituted by the Finance Act 2023.
- **Federal Finance Act 2026 (Act XLIII of 2026)**, gazette of 26 June 2026,
  download1.fbr.gov.pk/Docs/20266291261044366FinanceAct2026.pdf. It amends the Motor Vehicles
  Taxation Act, Customs Act, Sales Tax Act, Income Tax Ordinance, Federal Excise Act and the
  Finance Acts 2018 and 2022. It does not amend the ICT (Tax on Services) Ordinance. FBR's page
  still lists the 30-06-2025 consolidation as the latest.
- **Gap:** the ICT text names only cash for the 15% rate. Bank transfer is not addressed, so the
  demo applies 15% and labels that as an assumption.

## Corrections to the earlier research

- Punjab 8% was right. The earlier notes rested on news reports; it is now confirmed in the
  enacted Act.
- ICT 15% / 5% was right, but its source is the Finance Act 2023 entry, not a 2025 change.
- **The reduced rate does not cover bank transfer.** The earlier design put `bank_transfer` in the
  digital class. It now belongs to the standard class.
- Sindh, KP and Balochistan were not checked. The demo venues do not use them.
