# Phase 2 · Noor & Za'atar and Tikka Town Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two new demo venues work end to end:
- **Noor & Za'atar:** Dubai, AED, 5% VAT included, no service charge, English and Arabic.
- **Tikka Town:** Manchester, GBP, 20% VAT included, optional 10% service charge outside tax, English only.

Each has its own menu, 90 days of demo history and its own guest brand package. An Arabic guest dictionary is added, so every venue's local language is in place.

**Architecture:**
- **No new tax or language code.** `GB` and `AE-DU` already exist in `data/tax_jurisdictions.json`. `ar` and right-to-left already work from phase 1b.
- **Each venue is a seed file**, registered in the seed script, the demo-venue list and the demo users.
- **Each brand is a static `VENUE_BRANDS` entry** in `packages/ui` plus a package folder in `apps/guest-web/src/brands/<slug>/`, following the Angeethi House and Kehwa & Crumb packages file for file.
- **Guest screens already read only `--brand-*` variables**, so no shared screen changes.

**Tech stack:**
- Seed JSON, the seed and simulation scripts, pytest in Docker (`api-test`).
- Next.js 15, `next/font/google`, `gsap` + `@gsap/react`, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-09-four-identities-design.md`. Sections: "Phase 2", "Phase 1 · Identities", "Animations", "Failures" and "Tests".

---

## Decisions made while planning

1. **Demo history is 90 days for every venue.** `scripts/simulate.py --days` defaults to 90, up from 56, so all four venues have the same depth.
2. **No counter QR at the new venues.** The spec lists tables only (10 and 12), so there is no `pickup_prefix`.
3. **Brand colours** come from the round-1 logos (`docs/brand/round-1/`), drawn from the user's palette set. They must pass the contrast test in `packages/ui/src/venue-brands.test.ts`.
   - **Noor:** royal blue `#014BAA` and light cream `#F8F3F0` (7.3:1). The decoration colour is saffron `#E9A93B`.
   - **Tikka:** the logo orange `#EC5E27` on milk is only about 3.2:1, below the 4.5:1 that the masthead text check needs. So the masthead and buttons use brick red `#9E2B12` (7.3:1 on milk `#FDFDF1`), and the decoration colour is mustard `#E8B23A`. The logo files stay byte-identical to round 1: the mark keeps its own orange tile, and the lockup is milk on transparent over brick.
4. **Fonts:**
   - **Noor:** El Messiri (display; Latin and Arabic glyphs) and Figtree (text).
   - **Tikka:** Bebas Neue (condensed display) and Archivo (text).
   - All are free (OFL). On `ar` pages, the phase 1b rule puts Noto Naskh first for Arabic-script text. That is unchanged.
5. **Arabic register:** Modern Standard Arabic, plain and polite, readable across the Gulf.
   - Dish names follow the local menu spelling (مجبوس دجاج, هريس, شاي كرك).
   - Use Arabic letters (ي ك ه), never the Urdu ones (ی ک ہ).
   - Money and numbers stay in Latin digits.
6. **Allergen data is conservative.**
   - Each dish lists the EU-14 allergens a typical recipe contains, with `allergen_verified: false`, like the other venues. When in doubt, include it.
   - Examples: za'atar and tahini mean sesame; batter means gluten; Yorkshire pudding means gluten, eggs and milk; ghee means milk.
   - A dish choice may add an allergen, never remove one.
7. **One translation test for all venues.** The Urdu-only seed and dictionary tests from phase 1b become tests over each (file or dictionary, language). The Urdu cases keep running unchanged.

## File map

**Data and scripts**
- `data/seed/tikka_town.json` (new)
- `data/seed/noor_and_zaatar.json` (new, English and Arabic)
- `data/seed/demo_users.json`: the owner gets four venues; one staff user per new venue.
- `data/seed/README.md`
- `scripts/seed.py`: `DEFAULT_SEED_FILES`, and reads `restaurant.service_charge_rate`.
- `scripts/simulate.py`: `--days` default 90.

**API (`services/api`)**
- `src/config.py`: `demo_restaurant_slugs` gains both slugs.
- `tests/test_seed.py`: appended.
- `tests/test_seed_new_venues.py` (new)
- `tests/test_new_venue_bills.py` (new)
- `tests/test_seed_urdu.py` → `tests/test_seed_translations.py` (renamed, parametrised)

**Shared UI (`packages/ui`)**
- `src/venue-brands.ts` and `src/venue-brands.test.ts`

**Guest app (`apps/guest-web`)**
- `src/i18n/ar.ts` (new)
- `src/i18n/index.ts`
- `src/i18n/i18n.test.ts`
- `public/venues/{noor-and-zaatar,tikka-town}/{mark,lockup}.svg`
- `src/brands/assets.test.ts`
- `src/brands/noor-and-zaatar/` (new): `fonts.ts`, `Motif.tsx`, `Welcome.tsx`, `Loader.tsx`, `index.ts`, `package.test.tsx`
- `src/brands/tikka-town/` (new): the same six files
- `src/brands/index.ts`

**Owner app (`apps/owner-web`)**
- `public/venues/{noor-and-zaatar,tikka-town}/{mark,lockup}.svg`
- `src/lib/venue-fonts.ts`

**End-to-end**
- `e2e/helpers.ts`
- `e2e/new-venues.spec.ts` (new)
- `e2e/one-venue.spec.ts`

**Docs**
- `README.md`
- `docs/architecture.md`

## Commands used throughout

- **Start the stack:** `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait`
- **Reset the database:** needed after the date changes, and after adding a seed file or demo slug.
  ```bash
  docker compose --profile edge --profile test down -v
  LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait
  docker compose exec -T api alembic upgrade head
  docker compose exec -T api python scripts/seed.py
  docker compose exec -T api python scripts/simulate.py
  ```
- **Python tests:** `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/<file> -q`
- **Python lint:** `uv run --project services/api ruff check services/ scripts/` and `uv run --project services/api ruff format --check services/ scripts/`
- **Unit tests:** run from inside the package, e.g. `cd apps/guest-web && npx vitest run`; the same for `apps/owner-web` and `packages/ui`. The repo-root vitest config picks up everything and has failures that predate this work, so don't use it.
- **JavaScript lint:** `npm --prefix apps/guest-web run lint`, and the same for owner-web.
- **End-to-end:** `npx playwright test e2e/<spec>` from the repo root.
- **Known flaky Python tests** (each passes alone):
  - `test_service_calls.py::test_call_resolve_and_cooldown`
  - `test_settle_safeguards.py::test_claim_order_settle_rounds`
  - `test_order_path.py::test_order_integrity_error_non_idempotency_reraised`
- `make` is not available. Never stage `.gitignore`, `.claude/` or `.impeccable/`.

---

### Task 1: Seed plumbing — service charge rate and 90 days of history

**Files:**
- Modify: `scripts/seed.py` (restaurant create ~l.195-210, update ~l.213-250)
- Modify: `scripts/simulate.py:52` and its usage docstring
- Test: `services/api/tests/test_seed.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `test_seed.py`; reuse its imports and `db_session` fixture, adding `from decimal import Decimal` if missing)

```python
async def test_seed_reads_the_service_charge_rate(db_session):
    data = load_seed_data("data/seed/angeethi_house.json")
    data["restaurant"] = {**data["restaurant"], "slug": "svc-test", "name": "Svc Test",
                          "tax_jurisdiction": "GB", "currency": "GBP",
                          "service_charge_rate": "0.10", "payment_details": {}}
    data.pop("simulation", None)
    await seed_data(data, db_session)
    r = (await db_session.execute(select(Restaurant).where(Restaurant.slug == "svc-test"))).scalar_one()
    assert r.service_charge_rate == Decimal("0.10")
    data["restaurant"]["service_charge_rate"] = "0.125"
    await seed_data(data, db_session)  # re-seed updates it
    await db_session.refresh(r, ["service_charge_rate"])
    assert r.service_charge_rate == Decimal("0.125")


async def test_seed_without_a_service_rate_keeps_zero(db_session):
    await seed_data(load_seed_data("data/seed/angeethi_house.json"), db_session)
    r = (await db_session.execute(select(Restaurant).where(Restaurant.slug == "angeethi-house"))).scalar_one()
    assert r.service_charge_rate == Decimal("0")
```

If the GB venue refuses the copied PKR data (payment details or prices), adjust only the test's copied data. The seed code is what's under test.

- [ ] **Step 2: Run and see it fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_seed.py -q -k service`

Expected: FAIL. The rate stays 0.

- [ ] **Step 3: Implement**

In the `Restaurant(...)` create call in `scripts/seed.py`:

```python
            service_charge_rate=Decimal(str(rest_data.get("service_charge_rate", "0"))),
```

In the update branch:

```python
        restaurant.service_charge_rate = Decimal(str(rest_data.get("service_charge_rate", "0")))
```

Import `Decimal` if it is missing. The database check (`0 ≤ rate ≤ 0.20`) still guards bad values.

In `scripts/simulate.py`: `parser.add_argument("--days", type=int, default=90)`, and `[--days 90]` in the docstring.

Then run `grep -rn "56" scripts/simulate.py scripts/*.sh Makefile docs/analytics.md README.md` and update only the mentions that refer to the simulation length.

- [ ] **Step 4: Run and see it pass**

Run: `docker compose --profile test run --rm api-test pytest tests/test_seed.py tests/test_simulator*.py -q`, then the Python lint.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed.py scripts/simulate.py services/api/tests/test_seed.py
git commit -m "feat(seed): read restaurant.service_charge_rate; demo history is 90 days"
```

Also add any doc that mentioned 56 days.

---

### Task 2: Tikka Town — seed, menu, demo users, registration

**Files:**
- Create: `data/seed/tikka_town.json`
- Modify: `data/seed/demo_users.json`, `scripts/seed.py:40`, `services/api/src/config.py:77`
- Create: `services/api/tests/test_seed_new_venues.py`, `services/api/tests/test_new_venue_bills.py`

- [ ] **Step 1: Write the failing tests**

`services/api/tests/test_seed_new_venues.py`:

```python
"""The phase 2 venues seed as the spec says (2026-11-09, phase 2)."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from scripts.seed import DEFAULT_SEED_FILES, load_seed_data, seed_data
from src.config import settings
from src.models import DiningTable, MenuItem, Restaurant

EU14 = {"gluten", "milk", "eggs", "fish", "crustaceans", "molluscs", "tree_nuts", "peanuts",
        "soy", "celery", "mustard", "sesame", "sulphites", "lupin"}

VENUES = {
    "tikka-town": dict(file="data/seed/tikka_town.json", name="Tikka Town", city="Manchester",
                       currency="GBP", jurisdiction="GB", service="0.10", tables=12,
                       languages=["en"], items=(26, 30), tz="Europe/London"),
}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("slug", VENUES)
def test_registered_everywhere(slug):
    v = VENUES[slug]
    assert v["file"] in DEFAULT_SEED_FILES
    assert slug in settings.demo_restaurant_slugs
    users = _load("data/seed/demo_users.json")
    assert slug in users["owner"]["venues"]
    assert [s for s in users["staff"] if s["venue"] == slug], "one staff user per venue"


@pytest.mark.parametrize("slug", VENUES)
def test_seed_file_is_well_formed(slug):
    v = VENUES[slug]
    data = _load(v["file"])
    r = data["restaurant"]
    assert (r["slug"], r["name"], r["city"], r["currency"], r["tax_jurisdiction"]) == (
        slug, v["name"], v["city"], v["currency"], v["jurisdiction"])
    assert r["languages"] == v["languages"] and r["default_language"] == "en"
    assert r["timezone"] == v["tz"]
    assert len([t for t in data["tables"] if t.get("kind", "table") == "table"]) == v["tables"]
    assert not [t for t in data["tables"] if t.get("kind") == "counter"]
    lo, hi = v["items"]
    assert lo <= len(data["items"]) <= hi
    keys = [i["key"] for i in data["items"]]
    assert len(keys) == len(set(keys)), "keys are unique"
    assert {m for m, _ in data["simulation"]["payment_mix"]} <= {"cash", "card"}
    for item in data["items"]:
        assert set(item["allergens"]) <= EU14, item["key"]
        assert item["allergen_verified"] is False, item["key"]
        assert item["ingredients"], item["key"]
        assert 0 < item["unit_cost"] < item["price"], item["key"]
        for g in item.get("choice_groups", []):
            for c in g["choices"]:
                assert set(c.get("allergens", [])) <= EU14, f"{item['key']}: {c['label']}"


@pytest.mark.parametrize("slug", VENUES)
async def test_seeds_into_the_database(slug, db_session):
    v = VENUES[slug]
    await seed_data(load_seed_data(v["file"]), db_session)
    r = (await db_session.execute(select(Restaurant).where(Restaurant.slug == slug))).scalar_one()
    assert r.service_charge_rate == Decimal(v["service"])
    tables = await db_session.scalar(
        select(func.count()).select_from(DiningTable).where(DiningTable.restaurant_id == r.id))
    assert tables == v["tables"]
    items = await db_session.scalar(
        select(func.count()).select_from(MenuItem).where(MenuItem.restaurant_id == r.id))
    assert items == len(_load(v["file"])["items"])


def test_tikka_town_has_the_spec_dishes():
    names = {i["translations"]["en"]["name"].lower() for i in _load("data/seed/tikka_town.json")["items"]}
    for dish in ["lamb chops", "seekh kebab", "chicken tikka", "chicken tikka masala",
                 "masala fish and chips", "chicken tikka pie", "lancashire hotpot",
                 "chips and curry sauce", "bombay potatoes", "manchester tart", "eccles cake",
                 "sticky toffee pudding", "gulab jamun", "mango lassi", "masala chai", "nihari",
                 "keema naan", "samosa chaat", "karahi", "balti", "sunday roast"]:
        assert any(dish in n for n in names), dish
```

`services/api/tests/test_new_venue_bills.py` runs `tests/test_global_bills.py`'s GB checks against the real seed file. Read `test_global_bills.py` first and import its helpers for opening a table, placing an order, reading the staff bill and settling. Don't copy them. Then write a `tikka` fixture that seeds `data/seed/tikka_town.json` and returns what its `uk` fixture returns, and three tests. Each test's requests and expected-value arithmetic come from the named `test_global_bills.py` test, using a real Tikka dish and its seeded price. Every assertion in the source test carries over, and none may be dropped.

| New test | Source in `test_global_bills.py` | What it proves |
|---|---|---|
| `test_tikka_bill_is_gbp_with_vat_included_and_service_on_its_own_line` | `test_uk_bill_includes_vat_and_offers_cash_and_card_only` | GBP, 20% VAT included, a separate optional 10% service line on the subtotal outside tax, methods `["cash", "card"]` |
| `test_tikka_settles_in_gbp_with_and_without_service` | `test_uk_settle_with_service`, `test_uk_settle_without_service` | both exact totals settle |
| `test_tikka_refuses_a_method_the_uk_does_not_list` | `test_raast_refused_on_a_uk_bill` | `raast` refused, the bill stays open |

- [ ] **Step 2: Run and see them fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_seed_new_venues.py tests/test_new_venue_bills.py -q`

Expected: FAIL. The file is missing and the venue is not registered.

- [ ] **Step 3: Write `data/seed/tikka_town.json`** (follow `angeethi_house.json` key for key)

```json
{
  "_note": "Fictional venue. Prices and costs are illustrative (2025-26 Manchester ranges), not quotes.",
  "restaurant": {
    "name": "Tikka Town",
    "slug": "tikka-town",
    "city": "Manchester",
    "tax_jurisdiction": "GB",
    "service_charge_rate": "0.10",
    "service_extra_label": "More naan / chips",
    "payment_details": {},
    "timezone": "Europe/London",
    "currency": "GBP",
    "languages": ["en"],
    "default_language": "en",
    "active": true
  },
  "tables": [{"label": "T1"}, {"label": "T2"}, {"label": "T3"}, {"label": "T4"}, {"label": "T5"}, {"label": "T6"},
             {"label": "T7"}, {"label": "T8"}, {"label": "T9"}, {"label": "T10"}, {"label": "B1"}, {"label": "B2"}],
  "simulation": {
    "lunch_rate": [6, 6, 7, 7, 10, 16, 14],
    "dinner_rate": [12, 13, 14, 16, 28, 32, 20],
    "lunch_hours": [12, 15],
    "dinner_hours": [17, 23],
    "party_size_weights": [0.08, 0.3, 0.15, 0.27, 0.1, 0.1],
    "dishes_per_guest": 1.7,
    "payment_mix": [["card", 0.85], ["cash", 0.15]]
  },
  "items": []
}
```

If `payment_details: {}` is refused, read `validate_payment_details` in `scripts/seed.py` and use the smallest valid value for a cash/card venue, for example `{"sample": true}`.

`items`: 26 to 30 dishes. Prices are in GBP with two decimals (e.g. `13.95`), with `unit_cost` below `price`.
- **Include:** the spec's full list (the test names): lamb chops, seekh kebab, chicken tikka, karahi, balti, nihari, keema naan, samosa chaat, chicken tikka masala, masala fish and chips, chicken tikka pie with minted peas, spiced Lancashire hotpot, chips and curry sauce, cheesy chips masala, Bombay potatoes, Sunday roast with masala gravy and Yorkshire pudding, Manchester tart, Eccles cake with Lancashire cheese, sticky toffee pudding, gulab jamun, mango lassi, masala chai.
- **Fill to 26-30** with breads (plain naan, garlic naan) and drinks (Vimto, a soft drink).
- **Per item:**
  - `key` and `category` (Grill, Curries, Mancunian Classics, Sides, Breads, Desserts, Drinks).
  - `ingredients`: the main 3-5. The first ones are shown as tags.
  - `allergens` (decision 6) and `allergen_verified: false`.
  - The diet flags, plus `dietary_verified: false` and `available: true`.
  - `featured`: mark 6-8 signature dishes; phase 3 uses it.
  - `sort_order`, `translations.en` {name, description}, and `sim_weight`.
- **Choices** use the phase 3A format, as in `angeethi_house.json`:
  - A Spice pick (Mild/Medium/Hot) on grills and curries.
  - A Leave out group (Onions, Green chilli, Coriander) where natural.
  - Regular/Large options on mango lassi.
  - An "Add cheese" extra on chips, which adds `milk`.
- **Descriptions** say only what the ingredients and allergens support.

Register the venue:
- `demo_users.json`: add `"tikka-town"` to `owner.venues`, plus `{"email": "demo-staff+tikka-town@mise.demo", "name": "Demo staff (Tikka)", "venue": "tikka-town"}`.
- `scripts/seed.py:40`: add `"data/seed/tikka_town.json"`.
- `src/config.py:77`: add `"tikka-town"`.

Then find code or tests that assume exactly two demo venues:

```bash
grep -rn "demo_restaurant_slugs\|kehwa-and-crumb" services/api/src services/api/tests e2e apps/guest-web/src apps/owner-web/src --include=*.py --include=*.ts --include=*.tsx
```

Fix any test that hard-codes two venues to use the configured list, and say why in the commit. Never weaken a test.

- [ ] **Step 4: Run and see them pass**

Run the full Python suite (`pytest -q`) and the Python lint. Then reset, seed and simulate with the commands above.

Expected: PASS, and both scripts report Tikka Town without errors.

- [ ] **Step 5: Commit**

```bash
git add data/seed/tikka_town.json data/seed/demo_users.json scripts/seed.py services/api/src/config.py services/api/tests
git commit -m "feat(data): Tikka Town — Manchester, GBP, 20% VAT included, optional 10% service, 12 tables"
```

---

### Task 3: Noor & Za'atar — seed with an English and Arabic menu

**Files:**
- Create: `data/seed/noor_and_zaatar.json`
- Modify: `data/seed/demo_users.json`, `scripts/seed.py:40`, `services/api/src/config.py:77`
- Modify: `services/api/tests/test_seed_new_venues.py`, `services/api/tests/test_new_venue_bills.py`
- Rename and generalise: `services/api/tests/test_seed_urdu.py` → `services/api/tests/test_seed_translations.py`

- [ ] **Step 1: Write the failing tests**

Add to `VENUES` in `test_seed_new_venues.py`:

```python
    "noor-and-zaatar": dict(file="data/seed/noor_and_zaatar.json", name="Noor & Za'atar", city="Dubai",
                            currency="AED", jurisdiction="AE-DU", service="0", tables=10,
                            languages=["en", "ar"], items=(22, 26), tz="Asia/Dubai"),
```

Add these tests:

```python
def test_noor_has_the_spec_dishes():
    names = {i["translations"]["en"]["name"].lower() for i in _load("data/seed/noor_and_zaatar.json")["items"]}
    for dish in ["chicken machboos", "lamb machboos", "harees", "thareed", "balaleet", "luqaimat",
                 "karak chai", "hummus", "moutabal", "za'atar manakish", "cheese manakish",
                 "mixed grill", "shish tawook", "mutton biryani", "lime"]:
        assert any(dish in n for n in names), dish


def test_sesame_is_declared_wherever_zaatar_or_tahini_is():
    for item in _load("data/seed/noor_and_zaatar.json")["items"]:
        text = " ".join(item["ingredients"]).lower()
        if any(w in text for w in ("za'atar", "zaatar", "tahini", "sesame")):
            assert "sesame" in item["allergens"], item["key"]
```

Rename the Urdu seed test: `git mv services/api/tests/test_seed_urdu.py services/api/tests/test_seed_translations.py`. Parametrise every test in it over these cases:

```python
SCRIPT = re.compile(r"[؀-ۿ]")
CASES = [
    ("data/seed/angeethi_house.json", "ur"),
    ("data/seed/kehwa_and_crumb.json", "ur"),
    ("data/seed/noor_and_zaatar.json", "ar"),
]
URDU_ONLY = re.compile(r"[کیہھے]")  # ک ی ہ ھ ے
ARABIC_ONLY = re.compile(r"[كي]")                    # ك ي
```

- Each existing test takes `(path, lang)` and checks `translations[lang]` instead of `"ur"`. Its assertions stay the same, including the measure exemption.
- `test_venue_offers_english_and_urdu` becomes `test_venue_offers_english_and_its_language`, asserting `["en", lang]`.
- Add `test_uses_only_its_own_scripts_letters`. It walks every translated string. An `ar` file must not match `URDU_ONLY`, and a `ur` file must not match `ARABIC_ONLY`.
- The commit message says the Urdu cases are unchanged.

In `test_new_venue_bills.py`, add a `noor` fixture (seeding `data/seed/noor_and_zaatar.json`) and two tests built the same way as Task 2:

| New test | Source in `test_global_bills.py` | What it proves |
|---|---|---|
| `test_noor_bill_is_aed_with_vat_included_and_no_service` | `test_dubai_bill_no_service_and_vat_included` | AED, 5% VAT included, no service line, methods `["cash", "card"]`; settling the exact total succeeds; `raast` is refused |
| `test_noor_claim_asking_for_service_records_none` | `test_service_asked_where_none_applies_is_not_recorded` | no service is recorded |

- [ ] **Step 2: Run and see them fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_seed_new_venues.py tests/test_seed_translations.py tests/test_new_venue_bills.py -q`

Expected: FAIL. The Noor file is missing.

- [ ] **Step 3: Write `data/seed/noor_and_zaatar.json`**

```json
{
  "_note": "Fictional venue. Prices and costs are illustrative (2025-26 Dubai ranges), not quotes.",
  "restaurant": {
    "name": "Noor & Za'atar",
    "slug": "noor-and-zaatar",
    "city": "Dubai",
    "tax_jurisdiction": "AE-DU",
    "service_extra_label": "More bread",
    "payment_details": {},
    "timezone": "Asia/Dubai",
    "currency": "AED",
    "languages": ["en", "ar"],
    "default_language": "en",
    "active": true
  },
  "tables": [{"label": "T1"}, {"label": "T2"}, {"label": "T3"}, {"label": "T4"}, {"label": "T5"},
             {"label": "T6"}, {"label": "T7"}, {"label": "T8"}, {"label": "M1"}, {"label": "M2"}],
  "simulation": {
    "lunch_rate": [8, 8, 9, 9, 14, 12, 9],
    "dinner_rate": [14, 15, 16, 18, 30, 28, 18],
    "lunch_hours": [12, 16],
    "dinner_hours": [19, 23],
    "party_size_weights": [0.05, 0.2, 0.15, 0.3, 0.15, 0.15],
    "dishes_per_guest": 1.6,
    "payment_mix": [["card", 0.8], ["cash", 0.2]]
  },
  "items": []
}
```

`payment_details` follows the same rule as Task 2.

`items`: 22 to 26 dishes. Prices are in AED, whole or half dirhams (e.g. `48.00`).
- **Order:** Emirati home cooking first, then Levantine and Pakistani: chicken machboos, lamb machboos, harees, thareed, balaleet, luqaimat with date syrup, karak chai, hummus, moutabal, za'atar manakish, cheese manakish, mixed grill, shish tawook, mutton biryani, fresh lime-mint.
- **Fill to 22-26** with lamb kofta, tabbouleh, fattoush, muhammara (`tree_nuts`: walnuts), Arabic coffee, laban and a soft drink.
- **Translations:**
  - Every item has `translations.en` and `translations.ar` {name, description} (decision 5).
  - Every option, group and choice has `"translations": {"ar": "…"}`.
- **Fixed Arabic spellings** (the end-to-end tests use them):

  | English | Arabic |
  |---|---|
  | Chicken Machboos | مجبوس دجاج |
  | Karak Chai | شاي كرك |
  | Hummus | حمص |
  | Za'atar Manakish | مناقيش زعتر |
  | Spice (group) | الحرارة |
  | Mild / Medium / Hot | خفيف / متوسط / حار |
  | Leave out (group) | بدون |
  | Onions | بصل |
  | Regular / Large | عادي / كبير |

- **Choices:**
  - A Spice pick on the grills and machboos.
  - Leave out where natural.
  - Regular/Large on karak and lime-mint.
  - "Add cheese" on za'atar manakish, which adds `milk`.
- **Allergens** (decision 6):
  - za'atar and tahini → `sesame`
  - manakish dough → `gluten`
  - laban, cheese and ghee → `milk`
  - harees and thareed → `gluten`
  - balaleet → `eggs` and `gluten`
- Never change a `label` after seeding, because IDs are derived from labels.

Register the venue:
- `demo_users.json`: add it to the owner's venues, plus `{"email": "demo-staff+noor-and-zaatar@mise.demo", "name": "Demo staff (Noor)", "venue": "noor-and-zaatar"}`.
- `DEFAULT_SEED_FILES`: add the file.
- `demo_restaurant_slugs`: add `"noor-and-zaatar"`.

- [ ] **Step 4: Run and see them pass**

Run the full Python suite and the Python lint. Then reset, seed and simulate.

Expected: four venues are seeded and simulated without errors.

- [ ] **Step 5: Commit**

```bash
git add data/seed services/api/src/config.py scripts/seed.py services/api/tests
git commit -m "feat(data): Noor & Za'atar — Dubai, AED, 5% VAT included, English and Arabic menu, 10 tables

test_seed_urdu.py becomes test_seed_translations.py over (file, language); the Urdu cases are unchanged."
```

---

### Task 4: Arabic guest dictionary

**Files:**
- Create: `apps/guest-web/src/i18n/ar.ts`
- Modify: `apps/guest-web/src/i18n/index.ts`, `apps/guest-web/src/i18n/i18n.test.ts`

- [ ] **Step 1: Write the failing test**

In `i18n.test.ts`, turn `describe("Urdu dictionary", …)` into `describe.each([["ur", ur], ["ar", ar]] as const)("%s dictionary", (code, dict) => { … })`.
- Every existing test inside uses `dict`, with the same assertions and the same `latinOnly` set.
- The existing `ur.staffNotice` assertion moves into the second test below.
- Add these two tests:

```ts
  it("uses only its own script's letters", () => {
    const wrong = code === "ar" ? /[کیہھے]/ : /[كي]/;
    for (const [key, value] of new Map(leaves(dict))) expect(value, key).not.toMatch(wrong);
  });

  it("names the staff in its mandatory notice", () => {
    expect(dict.staffNotice).toMatch(code === "ar" ? /الموظفين/ : /عملے سے/);
  });
```

- [ ] **Step 2: Run and see it fail**

Run: `cd apps/guest-web && npx vitest run src/i18n`

Expected: FAIL. `./ar` is not found.

- [ ] **Step 3: Write `ar.ts`**

A complete `TranslationDict`, in the same key order as `en.ts`, starting:

```ts
import type { TranslationDict } from "./types";

// DRAFT TRANSLATION: hand-written, awaiting review by a native Arabic speaker. Until then the
// allergen and safety text below (staffNotice, ui.noticeShort, allergens, allergenStatus,
// ui.allergenWarning*, ui.allergenAckCheckbox, dish.leaveOutNotice) must not be relied on alone;
// the allergen status itself is always decided by server code.
export const ar: TranslationDict = {
```

**Writing rules:**
- Follow decision 5. Use plain polite forms or neutral imperatives.
- Keep every `{placeholder}` and the “{button}” quoting.
- Payment brand names stay in Latin script.
- Never add meaning the English doesn't have.

**Safety text, word for word:**

| Key | Arabic | Note |
|---|---|---|
| `allergens.celery` | `الكرفس` | |
| `allergens.tree_nuts` | `المكسرات (لوز، جوز، كاجو وغيرها)` | |
| `allergens.crustaceans` | `القشريات (روبيان، سلطعون، كركند)` | |
| `allergens.molluscs` | `الرخويات (محار، حبار، بلح البحر)` | |
| `allergenStatus.no_declared_match` | `لا يوجد تطابق مُعلن` | no match with *your* allergens; never "no allergens" |
| `allergenStatus.contains` | `يحتوي على` | the chip renders "{contains}: {names}" |
| `staffNotice` | | must name the staff (الموظفين) |

**Fixed strings** (the end-to-end tests use them):

| Key | Arabic |
|---|---|
| `ui.continueToMenu` | `عرض القائمة` |
| `ui.placeOrder` | `تأكيد الطلب` |
| `ui.cartTitle` | `طلبك` |
| `ui.checkout` | `عرض الطلب` |
| `ui.addDish` | `إضافة {name}` |
| `pay.button` | `دفع الفاتورة` |
| `pay.methods.cash` | `نقدًا` |
| `ui.allergenAckCheckbox` | `تحدثت مع الموظفين وأفهم مخاطر الحساسية لهذا الطلب.` |

In `index.ts`, add `import { ar } from "./ar";`, add `ar` to the `export { … }` line and to the `dictionaries` map.

- [ ] **Step 4: Run and see it pass**

Run: `cd apps/guest-web && npx vitest run`, then `npm --prefix apps/guest-web run lint`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src/i18n
git commit -m "feat(guest): Arabic dictionary (draft translation); completeness tests run for ur and ar"
```

---

### Task 5: Brand data and logo files

**Files:**
- Modify: `packages/ui/src/venue-brands.ts`, `packages/ui/src/venue-brands.test.ts`
- Create: `apps/{guest-web,owner-web}/public/venues/{noor-and-zaatar,tikka-town}/{mark,lockup}.svg`
- Modify: `apps/guest-web/src/brands/assets.test.ts`, `apps/owner-web/src/lib/venue-fonts.ts`

This task is staged, not committed. `brands/index.test.ts` ("has a package for every venue brand") fails until Tasks 6 and 7 add the packages, so the brand work is committed once, at the end of Task 7. **Never skip that assertion.**

- [ ] **Step 1: Write the failing tests**

In `assets.test.ts`:

```ts
const SOURCE: Record<string, string> = {
  "angeethi-house": "angeethi",
  "kehwa-and-crumb": "kehwa",
  "noor-and-zaatar": "noor",
  "tikka-town": "tikka",
};
```

In `packages/ui/src/venue-brands.test.ts`:

```ts
it("has a brand for every demo venue", () => {
  expect(Object.keys(VENUE_BRANDS).sort()).toEqual(["angeethi-house", "kehwa-and-crumb", "noor-and-zaatar", "tikka-town"]);
});
```

- [ ] **Step 2: Run and see it fail**

Run: `cd packages/ui && npx vitest run`

Expected: FAIL. There are only two brands.

- [ ] **Step 3: Implement**

Add to `VENUE_BRANDS`:

```ts
  "noor-and-zaatar": {
    slug: "noor-and-zaatar",
    name: "Noor & Za'atar",
    tokens: {
      deep: "#014BAA",
      onDeep: "#F8F3F0",
      surface: "#F8F3F0",
      surface2: "#ECE4DA",
      card: "#FFFCF8",
      line: "rgb(1 75 170 / 0.15)",
      accent: "#014BAA",
      accentStrong: "#013A85",
      onAccent: "#F8F3F0",
      spark: "#E9A93B",
      // Arches from the logo: round top, nearly square base.
      buttonRadius: "999px 999px 10px 10px",
      cardRadius: "28px 28px 10px 10px",
      headingWeight: "600",
    },
    displayFont: "var(--brand-display-face, Georgia), Georgia, serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
  "tikka-town": {
    slug: "tikka-town",
    name: "Tikka Town",
    tokens: {
      deep: "#9E2B12",
      onDeep: "#FDFDF1",
      surface: "#FDFDF1",
      surface2: "#F6EBD7",
      card: "#FFFFFA",
      line: "rgb(158 43 18 / 0.18)",
      accent: "#9E2B12",
      accentStrong: "#7A200C",
      onAccent: "#FDFDF1",
      spark: "#E8B23A",
      buttonRadius: "2px",
      cardRadius: "2px",
      headingWeight: null,
    },
    displayFont: "var(--brand-display-face, Impact), Impact, 'Arial Narrow', sans-serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
```

Copy the logos byte for byte with `cp`, into both apps:
- `docs/brand/round-1/noor-mark.svg` → `public/venues/noor-and-zaatar/mark.svg`
- `docs/brand/round-1/noor-lockup.svg` → `public/venues/noor-and-zaatar/lockup.svg`
- `docs/brand/round-1/tikka-mark.svg` → `public/venues/tikka-town/mark.svg`
- `docs/brand/round-1/tikka-lockup.svg` → `public/venues/tikka-town/lockup.svg`

`apps/owner-web/src/lib/venue-fonts.ts`:

```ts
import { Anton, Bebas_Neue, El_Messiri, Jost } from "next/font/google";

// Display faces of the venue brands, for the printed QR cards and sample bill only.
const anton = Anton({ subsets: ["latin"], weight: "400", display: "swap" });
const jost = Jost({ subsets: ["latin"], weight: ["300", "400"], display: "swap" });
const messiri = El_Messiri({ subsets: ["latin", "arabic"], weight: ["600"], display: "swap" });
const bebas = Bebas_Neue({ subsets: ["latin"], weight: "400", display: "swap" });

export const VENUE_DISPLAY_CLASS: Record<string, string> = {
  "angeethi-house": anton.className,
  "kehwa-and-crumb": jost.className,
  "noor-and-zaatar": messiri.className,
  "tikka-town": bebas.className,
};
```

Run `grep -rn "kehwa-and-crumb" apps/owner-web/src --include=*.ts --include=*.tsx`. Add both venues to every per-venue map it finds, and to their tests.

- [ ] **Step 4: Run**

Run `cd packages/ui && npx vitest run` and `cd apps/owner-web && npx vitest run`, then the owner lint.

Expected: PASS, including the contrast test for both new brands. guest-web's `brands/index.test.ts` package-count test fails until Task 7, as planned.

- [ ] **Step 5: Stage, don't commit**

```bash
git add packages/ui/src apps/guest-web/public/venues apps/owner-web/public/venues apps/guest-web/src/brands/assets.test.ts apps/owner-web/src/lib/venue-fonts.ts
```

---

### Task 6: Noor & Za'atar brand package

**Files:**
- Create: `apps/guest-web/src/brands/noor-and-zaatar/fonts.ts`, `Motif.tsx`, `Welcome.tsx`, `Loader.tsx`, `index.ts`, `package.test.tsx`
- Modify: `apps/guest-web/src/brands/index.ts`

The identity, from the spec: evening light, deep blue and saffron gold, arches from the logo.
- **Welcome:** a lantern pattern draws itself and lights up, then the mark and the name rise.
- **Loader:** a lantern flickers.

Follow the Angeethi package file for file. Use the impeccable or taste skill, and look at the render before committing. The user asked for real, non-generic branding.

- [ ] **Step 1: Write the failing test** (`package.test.tsx`)

```tsx
// @vitest-environment jsdom
import React from "react";
import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./fonts", () => ({ display: { variable: "font-d" }, text: { variable: "font-t" } }));

import { brand } from "./index";

function reducedMotion(reduce: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: reduce ? q.includes("reduce") : q.includes("no-preference"),
    media: q,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("Noor & Za'atar package", () => {
  beforeEach(() => reducedMotion(false));
  it("exposes fonts and a decorative motif for both places", () => {
    expect(brand.fontClass).toBe("font-d font-t");
    for (const variant of ["masthead", "bar"] as const) {
      const { container } = render(<brand.Motif variant={variant} />);
      expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    }
  });
  it("loader announces its label", () => {
    const { getByRole } = render(<brand.Loader label="Loading menu" />);
    expect(getByRole("status").textContent).toContain("Loading menu");
  });
  it("loader shows the lantern normally and the venue's still mark under reduced motion", async () => {
    const lantern = render(<brand.Loader label="Loading menu" />);
    expect(lantern.container.querySelector("img")).toBeNull();
    expect(lantern.container.querySelector("svg")).not.toBeNull();
    lantern.unmount();
    reducedMotion(true);
    const { container } = render(<brand.Loader label="Loading menu" />);
    await act(async () => {});
    expect(container.querySelector("img")?.getAttribute("src")).toBe("/venues/noor-and-zaatar/mark.svg");
    expect(container.querySelector("svg")).toBeNull();
    expect(container.textContent).toContain("Loading menu");
  });
  it("welcome names the venue and finishes under reduced motion", async () => {
    vi.useFakeTimers();
    reducedMotion(true);
    const onDone = vi.fn();
    const { container } = render(<brand.Welcome name="Noor & Za'atar" onDone={onDone} />);
    expect(container.textContent).toContain("Noor & Za'atar");
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    expect(onDone).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run and see it fail**

Run: `cd apps/guest-web && npx vitest run src/brands/noor-and-zaatar`

Expected: FAIL. The module is not found.

- [ ] **Step 3: Implement**

`fonts.ts`:

```ts
import { El_Messiri, Figtree } from "next/font/google";

// Display with Latin and Arabic glyphs (logo band and Arabic headings share it) and a clean text face. Free (OFL).
export const display = El_Messiri({ subsets: ["latin", "arabic"], weight: ["600"], variable: "--brand-display-face", display: "swap" });
export const text = Figtree({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
```

`Motif.tsx`:

```tsx
import React from "react";

/** A row of arches under the masthead; a saffron thread with lantern beads on the order bar. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-1 w-full">
        <rect y="1.5" width="100" height="1" fill="var(--brand-spark)" opacity="0.7" />
        {[20, 50, 80].map((x) => (
          <circle key={x} cx={x} cy="2" r="1.6" fill="var(--brand-spark)" />
        ))}
      </svg>
    );
  }
  const arches = [0, 12.5, 25, 37.5, 50, 62.5, 75, 87.5];
  return (
    <svg aria-hidden="true" viewBox="0 0 100 10" preserveAspectRatio="none" className="block h-3 w-full">
      {arches.map((x) => (
        <path key={x} d={`M${x + 1} 10 V5 A5.25 5 0 0 1 ${x + 11.5} 5 V10`} fill="none" stroke="var(--brand-spark)" strokeWidth="0.6" opacity="0.8" />
      ))}
    </svg>
  );
}
```

`Loader.tsx`:

```tsx
"use client";

import React, { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false), []);
  return reduced;
}

/** A lantern whose flame flickers; the venue's still mark under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".nz-flame", { opacity: 0.35, scaleY: 0.8, transformOrigin: "50% 100%", duration: 0.18, repeat: -1, yoyo: true, ease: "steps(3)" });
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      {reduced ? (
        // eslint-disable-next-line @next/next/no-img-element -- a small static mark
        <img src="/venues/noor-and-zaatar/mark.svg" alt="" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"} />
      ) : (
        <svg aria-hidden="true" viewBox="0 0 20 30" className={size === "sm" ? "h-6" : "h-10"}>
          <path d="M10 2v3M5 8h10l-1 2v12l1 2H5l1-2V10z" fill="none" stroke="var(--brand-accent)" strokeWidth="1.4" strokeLinejoin="round" />
          <path className="nz-flame" d="M10 13c2 2.5 2 5 0 7c-2-2-2-4.5 0-7z" fill="var(--brand-spark)" />
        </svg>
      )}
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
```

`Welcome.tsx`:

```tsx
"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** A lantern's lattice draws itself and lights, then the mark and name rise. About 2 s; still logo under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const lines = gsap.utils.toArray<SVGPathElement>(".nz-line");
        lines.forEach((p) => {
          const len = p.getTotalLength?.() ?? 100;
          gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
        });
        gsap
          .timeline({ onComplete: onDone })
          .to(lines, { strokeDashoffset: 0, duration: 0.7, stagger: 0.06, ease: "power2.inOut" })
          .to(".nz-glow", { opacity: 0.9, duration: 0.35 }, "-=0.1")
          .from(".nz-mark", { opacity: 0, y: 12, duration: 0.4 }, "-=0.15")
          .from(".nz-name", { opacity: 0, y: 20, duration: 0.45 }, "-=0.1")
          .to({}, { duration: 0.3 });
      });
      mm.add("(prefers-reduced-motion: reduce)", () => {
        // Plain timer, not GSAP: nothing animates here, and it stays testable with fake timers.
        const t = setTimeout(onDone, 1200);
        return () => clearTimeout(t);
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <div ref={root} className="flex flex-col items-center gap-4 text-[var(--brand-on-deep)]">
      <svg aria-hidden="true" viewBox="0 0 80 110" className="h-24 w-20">
        <ellipse className="nz-glow" cx="40" cy="62" rx="22" ry="28" fill="var(--brand-spark)" opacity="0" />
        <path className="nz-line" d="M40 4v10M24 18h32l-4 8v58l4 8H24l4-8V26z" fill="none" stroke="var(--brand-spark)" strokeWidth="2" strokeLinejoin="round" />
        <path className="nz-line" d="M28 40h24M28 60h24M28 80h24M40 26v66" fill="none" stroke="var(--brand-spark)" strokeWidth="1.2" />
        <path className="nz-line" d="M28 26q12 14 24 0M28 92q12-14 24 0" fill="none" stroke="var(--brand-spark)" strokeWidth="1.2" />
      </svg>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="nz-mark h-20 w-20" src="/venues/noor-and-zaatar/mark.svg" alt="" />
      <p className="nz-name font-serif text-4xl">{name}</p>
    </div>
  );
}
```

`index.ts`:

```ts
import type { BrandPackage } from "../types";
import { display, text } from "./fonts";
import { Loader } from "./Loader";
import { Motif } from "./Motif";
import { Welcome } from "./Welcome";

export const brand: BrandPackage = { fontClass: `${display.variable} ${text.variable}`, Motif, Welcome, Loader };
```

In `brands/index.ts`, add `"noor-and-zaatar": () => import("./noor-and-zaatar").then((m) => m.brand),` to `PACKAGES`.

- [ ] **Step 4: Run and look**

Run: `cd apps/guest-web && npx vitest run src/brands`, then the guest lint.

Expected: the Noor package test and the brand import rules pass.

Rebuild the stack (mock settings), then reset, seed and simulate. In the browser pane at 375 px, open a Noor table QR (the demo landing page at `http://localhost:3000/` lists the table links). Check:
- The welcome.
- The masthead arches.
- The order bar.
- The dish sheet, in English and in Arabic.

Fix anything that looks off, such as arch spacing or lantern proportions.

- [ ] **Step 5: Stage, don't commit**

```bash
git add apps/guest-web/src/brands/noor-and-zaatar apps/guest-web/src/brands/index.ts
```

---

### Task 7: Tikka Town brand package, then commit the brand work

**Files:**
- Create: `apps/guest-web/src/brands/tikka-town/fonts.ts`, `Motif.tsx`, `Welcome.tsx`, `Loader.tsx`, `index.ts`, `package.test.tsx`
- Modify: `apps/guest-web/src/brands/index.ts`

The identity, from the spec: loud Northern sign-painting, brick red and mustard, bold condensed type and ticket-stub edges.
- **Welcome:** a skewer slides across and stamps the logo like a shop sign.
- **Loader:** a skewer turns.

Use the impeccable or taste skill, and look at the render.

- [ ] **Step 1: Write the failing test**

`package.test.tsx` is Task 6's test with these replacements, applied to the whole file:
- `Noor & Za'atar` → `Tikka Town`
- `/venues/noor-and-zaatar/mark.svg` → `/venues/tikka-town/mark.svg`
- `"loader shows the lantern normally …"` → `"loader shows the skewer normally …"`
- the variable `lantern` → `skewer`

- [ ] **Step 2: Run and see it fail**

Run: `cd apps/guest-web && npx vitest run src/brands/tikka-town`

Expected: FAIL. The module is not found.

- [ ] **Step 3: Implement**

`fonts.ts`:

```ts
import { Archivo, Bebas_Neue } from "next/font/google";

// Bold condensed shop-sign display and a sturdy grotesque text face. Free (OFL).
export const display = Bebas_Neue({ subsets: ["latin"], weight: "400", variable: "--brand-display-face", display: "swap" });
export const text = Archivo({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
```

`Motif.tsx`:

```tsx
import React from "react";

/** A ticket-stub edge under the masthead (punched half-circles); a mustard skewer on the order bar. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-1 w-full">
        <rect y="1.25" width="100" height="1.5" fill="var(--brand-spark)" />
        {[15, 35, 55, 75].map((x) => (
          <rect key={x} x={x} y="0" width="6" height="4" fill="var(--brand-spark)" />
        ))}
      </svg>
    );
  }
  const holes = Array.from({ length: 20 }, (_, i) => i * 5 + 2.5);
  return (
    <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-2 w-full">
      <rect width="100" height="4" fill="var(--brand-deep)" />
      {holes.map((x) => (
        <circle key={x} cx={x} cy="4" r="1.4" fill="var(--brand-surface)" />
      ))}
    </svg>
  );
}
```

`Loader.tsx`:

```tsx
"use client";

import React, { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false), []);
  return reduced;
}

/** A skewer turns; the venue's still mark under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".tt-skewer", { rotate: 360, transformOrigin: "50% 50%", duration: 1.1, ease: "none", repeat: -1 });
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      {reduced ? (
        // eslint-disable-next-line @next/next/no-img-element -- a small static mark
        <img src="/venues/tikka-town/mark.svg" alt="" className={size === "sm" ? "h-5 w-5" : "h-8 w-8"} />
      ) : (
        <svg aria-hidden="true" viewBox="0 0 30 30" className={size === "sm" ? "h-6" : "h-10"}>
          <g className="tt-skewer">
            <line x1="4" y1="26" x2="26" y2="4" stroke="var(--brand-accent)" strokeWidth="1.6" strokeLinecap="round" />
            <rect x="9" y="15" width="6" height="6" rx="1" transform="rotate(-45 12 18)" fill="var(--brand-spark)" />
            <rect x="15" y="9" width="6" height="6" rx="1" transform="rotate(-45 18 12)" fill="var(--brand-accent)" />
          </g>
        </svg>
      )}
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
```

`Welcome.tsx`:

```tsx
"use client";

import React, { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** A skewer slides across and stamps the logo like a shop sign, then the name. About 2 s; still logo under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".tt-skewer", { xPercent: -160, duration: 0.55, ease: "power3.out" })
          .from(".tt-mark", { scale: 1.6, rotate: -8, opacity: 0, duration: 0.28, ease: "back.out(2.5)" }, "-=0.05")
          .to(".tt-skewer", { opacity: 0, duration: 0.2 }, "<")
          .from(".tt-name", { opacity: 0, y: 18, duration: 0.4 }, "-=0.05")
          .to({}, { duration: 0.45 });
      });
      mm.add("(prefers-reduced-motion: reduce)", () => {
        // Plain timer, not GSAP: nothing animates here, and it stays testable with fake timers.
        const t = setTimeout(onDone, 1200);
        return () => clearTimeout(t);
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <div ref={root} className="flex flex-col items-center gap-4 text-[var(--brand-on-deep)]">
      <div className="relative h-28 w-56">
        <svg aria-hidden="true" viewBox="0 0 220 40" className="tt-skewer absolute inset-x-0 top-10 w-56">
          <line x1="0" y1="20" x2="215" y2="20" stroke="var(--brand-spark)" strokeWidth="3" strokeLinecap="round" />
          {[40, 80, 120, 160].map((x, i) => (
            <rect key={x} x={x} y="8" width="24" height="24" rx="3" fill={i % 2 ? "var(--brand-spark)" : "var(--brand-on-deep)"} />
          ))}
        </svg>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="tt-mark absolute left-1/2 top-0 h-28 w-28 -translate-x-1/2" src="/venues/tikka-town/mark.svg" alt="" />
      </div>
      <p className="tt-name font-serif text-5xl uppercase tracking-wide">{name}</p>
    </div>
  );
}
```

`index.ts` is the same as Task 6's. In `brands/index.ts`, add `"tikka-town": () => import("./tikka-town").then((m) => m.brand),`.

- [ ] **Step 4: Run everything and look**

Run all three unit suites (`packages/ui`, `apps/guest-web`, `apps/owner-web`) and both lints.

Expected: all PASS, including "has a package for every venue brand".

Rebuild the stack, then check both new venues in the browser pane at 375 px:
- The welcome, masthead and motif.
- The order bar and dish sheet.
- In the owner app, each venue's QR card and sample bill.

Fix what looks wrong.

- [ ] **Step 5: Commit the brand work (Tasks 5–7)**

```bash
git add apps/guest-web/src/brands
git commit -m "feat(brand): Noor & Za'atar and Tikka Town — brand data, logos, fonts, motif, welcome and loader"
```

---

### Task 8: End-to-end — a full order at each new venue, Arabic at Noor

**Files:**
- Modify: `e2e/helpers.ts`, `e2e/one-venue.spec.ts`
- Create: `e2e/new-venues.spec.ts`

- [ ] **Step 1: Extend the helpers**

In `e2e/helpers.ts`:
- Add `export const NOOR = "noor-and-zaatar";` and `export const TIKKA = "tikka-town";`.
- Widen the `lang` parameter of `openTableMenu`, `acknowledgeAllergens` and `placeOrder` to `"en" | "ur" | "ar"`.
- Add the Arabic entries, copied exactly from `apps/guest-web/src/i18n/ar.ts`: `VIEW_MENU.ar = "عرض القائمة"`, `CONFIRM.ar = "تأكيد الطلب"`, `ACK.ar = "تحدثت مع الموظفين وأفهم مخاطر الحساسية لهذا الطلب."`.
- `openTableMenu` taps the language button by its own name: `({ ur: "اردو", ar: "العربية" } as const)[lang]` when `lang !== "en"`.

- [ ] **Step 2: Write `e2e/new-venues.spec.ts`**

Read `e2e/urdu.spec.ts` first and reuse its patterns and selectors. Tests:

1. **Tikka Town in English, with the service charge**
   - Open a table and scan. The "Tikka Town" heading is visible.
   - Add Chicken Tikka Masala, picking its required choices.
   - Confirm, and staff approve.
   - Open the pay sheet. The optional 10% service is on its own line, outside tax.
   - Pay by cash.
   - Staff confirm the bill at `${OWNER}/bills` with service, and the print page opens.
   - Prices match `/£\d+\.\d{2}/`.
2. **Noor & Za'atar in Arabic**
   - Scan, tap "العربية", then "عرض القائمة". The URL ends in `/ar/menu`.
   - The server HTML for `/ar/menu` contains `lang="ar" dir="rtl"`.
   - "مجبوس دجاج" is visible.
   - The page has digits and none in `[٠-٩۰-۹]`.
   - Add "شاي كرك" (عادي), confirm with "تأكيد الطلب", and staff approve.
   - Pay with "نقدًا". There is no service line.
   - The kitchen (`${OWNER}/kitchen`) and the staff bill show the English names and no `[؀-ۿ]` characters.
3. **Language rules**
   - Tikka Town's scan page has no language group.
   - With a Tikka session, `/ar/menu` redirects to `/en/menu`.
   - With a Noor English session, `/ur/menu` redirects to `/en/menu`.
4. **Screenshots** (spec: "one screenshot per venue of welcome, menu and sample bill")
   - For each of the four venues, attach PNGs: the welcome before skipping, the menu, and the sample bill print page.
   - Use `testInfo.attach(\`${slug}-welcome\`, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" })`.
   - These are evidence for review, not visual-diff assertions.

- [ ] **Step 3: Extend the one-venue walk**

- **English walk:** confirm it loops over every venue the demo API lists, so all four are covered. If its list is hard-coded, use the API list.
- **Arabic walk:** add one for Noor with `walk(browser, request, venues, NOOR, "ar")`. Take the Arabic strings for the assistant button, Close and scan-again from `ar.ts`, the same way the Urdu run does.

- [ ] **Step 4: Run**

Reset, seed and simulate first. Then:

```bash
npx playwright test e2e/new-venues.spec.ts e2e/one-venue.spec.ts
npx playwright test
```

Expected: all PASS. Report any rerun.

- [ ] **Step 5: Commit**

```bash
git add e2e
git commit -m "test(e2e): a full order at Tikka Town (service charge) and at Noor in Arabic; four-venue walks and screenshots"
```

---

### Task 9: Docs and a whole-branch check

**Files:**
- Modify: `README.md`, `data/seed/README.md`, `docs/architecture.md`

- [ ] **Step 1: Update the docs** (describe only what is implemented and tested)

- `data/seed/README.md`:
  - List both new files with their facts: city, jurisdiction, currency, service, tables, dish count, languages.
  - "Both venues" becomes "All four venues".
  - Note that Noor's menu is English and Arabic, and the Arabic is a draft translation.
- `README.md`:
  - The four demo venues, with their cities and currencies.
  - Arabic at Noor & Za'atar (draft translation, right-to-left).
  - Tikka Town's optional service charge.
  - 90 days of demo history.
- `docs/architecture.md`:
  - The venues list.
  - `service_charge_rate` from the seed.
  - The four brand packages.

- [ ] **Step 2: Run the whole-branch checks**

```bash
docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest -q
uv run --project services/api ruff check services/ scripts/
uv run --project services/api ruff format --check services/ scripts/
cd packages/ui && npx vitest run && cd ../..
cd apps/guest-web && npx vitest run && cd ../..
cd apps/owner-web && npx vitest run && cd ../..
npm --prefix apps/guest-web run lint
npm --prefix apps/owner-web run lint
bash scripts/check_branding.sh
```

Expected: everything passes, apart from the known flaky tests, which pass alone.

Then check by hand in the browser pane, signed in to the owner app with demo login:
- The venue picker lists four venues.
- The Noor and Tikka dashboards show 90 days of history, in AED and GBP.
- The Brief and forecast pages load for both.

- [ ] **Step 3: Commit**

```bash
git add README.md data/seed/README.md docs/architecture.md
git commit -m "docs: four demo venues — Noor & Za'atar (Arabic) and Tikka Town (service charge); 90 days of history"
```

---

## Spec coverage check

| Spec item (phase 2 and the shared tests) | Task |
|---|---|
| Seed files, slugs, cities, currencies, jurisdictions, service, tables, dish counts | 2, 3 |
| No new tax code | 2, 3 (`GB` and `AE-DU`) |
| Demo owner and staff for both venues | 2, 3 |
| 90 days of synthetic history in the venue's currency | 1, 2, 3, 9 |
| Owner venue picker lists all four | 2, 3, 9 |
| 14-allergen data and dish choices | 2, 3 |
| Noor menu in English and Arabic; `ar.ts` with draft safety text | 3, 4 |
| The spec's dish lists | 2, 3 |
| Brand packages from the round-1 logos; the identity table | 5, 6, 7 |
| Contrast, isolation and import rule for all four brands | 5, 6, 7 (the existing tests loop over every brand) |
| AED and GBP settle; Tikka service on its own line outside tax; unlisted method refused | 2, 3 |
| A full order at each new venue; four-venue walk; a screenshot per venue | 8 |
| Docs | 9 |
