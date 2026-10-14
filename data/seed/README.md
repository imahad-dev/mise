# Seed Data

Seed data files for Mise. Each JSON file represents one restaurant's complete menu.

> [!WARNING]
> The seed script is a **development and demonstration tool only**. Running the seed overwrites existing records, resetting menu data, pricing, translations, and **verified flags** (`allergen_verified`, `dietary_verified`) back to the initial seed state. Never run this script against a production database.

## Behavior

1. **Restaurant**: Upserted by `slug`.
2. **Tables**: Matched by `label`. A table without a token is assigned a cryptographically secure token (`secrets.token_urlsafe(12)`) on initial creation. Existing table tokens are preserved on re-seed unless `--rotate-qr` is explicitly specified.
3. **Menu Items**: Matched by stable UUID derived from deterministic seed item `key` (or Italian name fallback). Items and translations are updated in-place.
4. **Verified Flags**: Overwritten to match seed JSON definitions.

## Files

- `trattoria_da_mario.json` — Italian trattoria, 25 items, EN + IT translations, EU-14 allergens, varied margins, 6 dining tables (no pre-assigned tokens in JSON).

## Usage

```bash
# Seed development database
docker compose exec -T api python scripts/seed.py

# Re-seed and regenerate all table QR tokens
docker compose exec -T api python scripts/seed.py --rotate-qr
```
