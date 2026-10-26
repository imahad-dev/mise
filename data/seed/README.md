# Seed Data

Seed data files for Mise. Each venue file represents one restaurant's complete menu. Both venues are fictional; prices and costs are illustrative (see each file's `_note`).

> [!WARNING]
> The seed script is a **development and demonstration tool only**. Running the seed overwrites existing records, resetting menu data, pricing, translations, and **verified flags** (`allergen_verified`, `dietary_verified`) back to the initial seed state. Never run this script against a production database.

## Behavior

1. **Restaurant**: Upserted by `slug`.
2. **Tables**: Matched by `label`. A table without a token is assigned a cryptographically secure token (`secrets.token_urlsafe(12)`) on initial creation. Existing table tokens are preserved on re-seed unless `--rotate-qr` is explicitly specified.
3. **Menu Items**: Matched by stable UUID `uuid5(namespace, "<slug>:<key>")`. Items and translations are updated in-place. The item price and unit cost are always those of its cheapest option.
4. **Options**: Matched by `uuid5(namespace, "<slug>:<key>:<label>")`. Options no longer in the file are deleted.
5. **Verified Flags**: Overwritten to match seed JSON definitions.

## Files

- `angeethi_house.json` — Angeethi House, Lahore (`PB`): 26 dishes, 20 portion options, 12 tables (T1-T8, F1-F4) and a "Takeaway" counter QR (pickup prefix `P`).
- `kehwa_and_crumb.json` — Kehwa & Crumb, Islamabad (`ICT`): 22 items, 15 size options, 8 tables (T1-T8) and a "Counter" counter QR (pickup prefix `K`).
- `demo_users.json` — not a venue: the demo owner (both venues) and one staff user per venue. They have random unusable passwords and sign in only through `/api/auth/demo-login`.

Venue files are English only, in PKR, with allergens marked `allergen_verified: false`. `sim_weight`, `option_weights` and the top-level `simulation` block describe simulated demand; the seeder ignores them.

## Usage

```bash
# Seed both venues (demo users too when DEMO_MODE=true)
docker compose exec -T api python scripts/seed.py

# One venue, plus demo users explicitly
docker compose exec -T api python scripts/seed.py --file data/seed/kehwa_and_crumb.json --demo-users data/seed/demo_users.json

# Re-seed and regenerate all table QR tokens
docker compose exec -T api python scripts/seed.py --rotate-qr
```
