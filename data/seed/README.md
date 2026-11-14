# Seed Data

Seed data files for Mise. Each venue file represents one restaurant's complete menu. All four venues are fictional; prices and costs are illustrative (see each file's `_note`).

> [!WARNING]
> The seed script is a **development and demonstration tool only**. Running the seed overwrites existing records, resetting menu data, pricing, translations, and **verified flags** (`allergen_verified`, `dietary_verified`) back to the initial seed state. Never run this script against a production database.

## Behavior

1. **Restaurant**: Upserted by `slug`, including `restaurant.service_charge_rate` (0 when absent).
2. **Tables**: Matched by `label`. A table without a token is assigned a cryptographically secure token (`secrets.token_urlsafe(12)`) on initial creation. Existing table tokens are preserved on re-seed unless `--rotate-qr` is explicitly specified.
3. **Menu Items**: Matched by stable UUID `uuid5(namespace, "<slug>:<key>")`. Items and translations are updated in-place. The item price and unit cost are always those of its cheapest option.
4. **Options**: Matched by `uuid5(namespace, "<slug>:<key>:<label>")`. Options no longer in the file are deleted.
5. **Verified Flags**: Overwritten to match seed JSON definitions.

## Files

- `angeethi_house.json` — Angeethi House, Lahore (`PB`): 26 dishes, 20 portion options, 12 tables (T1-T8, F1-F4) and a "Takeaway" counter QR (pickup prefix `P`).
- `kehwa_and_crumb.json` — Kehwa & Crumb, Islamabad (`ICT`): 22 items, 15 size options, 8 tables (T1-T8) and a "Counter" counter QR (pickup prefix `K`).
- `tikka_town.json` — Tikka Town, Manchester (`GB`): 28 dishes, English only, in GBP. VAT 20% is included in menu prices and the venue's optional service charge is 10% (`service_charge_rate`), added outside tax. 12 tables (T1-T10, B1, B2), no counter QR.
- `noor_and_zaatar.json` — Noor & Za'atar, Dubai (`AE-DU`): 24 dishes in English and Arabic, in AED. VAT 5% is included in menu prices; no service charge. 10 tables (T1-T8, M1, M2), no counter QR. The Arabic is a draft translation awaiting review by a native speaker.
- `demo_users.json` — not a venue: the demo owner (all four venues) and one staff user per venue. They have random unusable passwords and sign in only through `/api/auth/demo-login`.

The Pakistani venue files are English and Urdu in PKR; Tikka Town is English only in GBP and Noor & Za'atar English and Arabic in AED. Allergens are marked `allergen_verified: false`. `sim_weight`, `option_weights` and the top-level `simulation` block describe simulated demand; the seeder ignores them.

## Usage

```bash
# Seed all four venues (demo users too when DEMO_MODE=true)
docker compose exec -T api python scripts/seed.py

# One venue, plus demo users explicitly
docker compose exec -T api python scripts/seed.py --file data/seed/kehwa_and_crumb.json --demo-users data/seed/demo_users.json

# Re-seed and regenerate all table QR tokens
docker compose exec -T api python scripts/seed.py --rotate-qr
```
