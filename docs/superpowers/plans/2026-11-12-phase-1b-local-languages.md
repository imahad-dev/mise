# Phase 1b · Local Languages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guests at the two Pakistani venues can use the guest app in English or Urdu (right-to-left, Latin-digit money). Each venue offers only its own languages, and Italian is gone.

**Architecture:**
- The API owns which languages a venue offers (`restaurant.languages`) and refuses any other.
- The guest venue response carries `languages` and `default_language`.
- The guest app's `[lang]` layout checks the URL language on the server, redirects to the visit's language, and sets `lang` and `dir` before first paint.
- Dish names already have per-language translations. Sizes, choice groups and choices get a small `translations` JSONB map, so Urdu labels reach the guest while kitchen, tickets and bills keep the English `label`.

**Tech stack:**
- API: FastAPI, async SQLAlchemy, Alembic, pytest in Docker (`api-test`).
- Guest app: Next.js 15 App Router, React 19, Tailwind v4 (`rtl:` variant, logical utilities), `next/font/google` (Noto Naskh Arabic), Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-09-four-identities-design.md`, section "Phase 1b · Local languages".
**Research:** `docs/research/2026-10-22-pakistan-notes/urdu_ui.md`.

---

## Decisions made while planning

1. **The URL follows the visit's language.** The guest picks a language on the scan page, and that is stored on the session. The `[lang]` layout redirects any other language segment to `/<session language>/menu`, or to the venue's default if the session holds a language the venue no longer offers. So `/ar/menu` at Angeethi sends an English guest to `/en/menu`, as the spec asks. There is no in-menu language switch in this phase; a guest switches by scanning again.
2. **A language segment that is not `en`, `ur` or `ar` gets the neutral not-found page** (`notFound()`), before any session lookup.
3. **Translated labels live in a JSONB `translations` map** (`{"ur": "…"}`) on `menu_item_option`, `menu_choice_group` and `menu_choice`, defaulting to `{}`. The guest menu shows `translations[session.language]`, falling back to `label`. Order snapshots, the kitchen, tickets and bills keep reading `label`, so they stay English. A guest's own order page shows those snapshot labels, so choice names appear in English there (dish names follow the existing guest-name snapshot).
4. **A missing `language` on session create means the venue's default**, not a hard-coded `"en"`.
5. **The assistant answers in English** whatever the session language, and its menu context is built from English names.
6. **Money stays Latin-digit.**
   - `formatPrice` and `percent` pass `numberingSystem: "latn"`.
   - In right-to-left pages, `.figure` is `direction: ltr; unicode-bidi: isolate`.
   - PKR already formats through `en-PK`.

## File map

**API (`services/api`)**
- `src/schemas/guest.py`: `SupportedLanguage = Literal["en","ur","ar"]`. `GuestVenue` gains `languages` and `default_language`. `language` on create becomes optional.
- `src/routers/guest.py`:
  - `venue_of` and `venue_for_qr` return the languages.
  - Create and patch refuse an unoffered language with 422.
  - The menu uses label translations.
- `src/schemas/owner.py`: `MenuIngestRequest.language: Literal["en","ur","ar"] = "en"`.
- `src/services/guest_chat.py`: always English.
- `src/models/menu.py`: `translations` JSONB on `MenuItemOption`, `MenuChoiceGroup` and `MenuChoice`.
- `alembic/versions/0022_label_translations.py`: new.
- `tests/test_guest_languages.py`: new.
- Tests whose `"it"` changes to `"ur"`: `tests/test_order_path.py`, `tests/test_schema_constraints.py`, `tests/test_simulator_concurrency.py`.
- `tests/test_seed_urdu.py`: new.

**Data and scripts**
- `scripts/seed.py`: reads `translations` on options, groups and choices.
- `data/seed/angeethi_house.json`, `data/seed/kehwa_and_crumb.json`: `languages: ["en","ur"]`, plus Urdu for every item, option, group and choice.
- `services/inference/mock/src/canned.py`: `TRANSLATION` becomes Urdu.
- `packages/api-client/openapi.json`, `packages/api-client/src/generated/schema.d.ts`: regenerated.

**UI package (`packages/ui`)**
- `src/format.ts` and `src/format.test.ts`: Latin digits.
- `src/theme.css`: `.figure` isolation in right-to-left pages.

**Guest app (`apps/guest-web/src`)**
- `i18n/languages.ts` (new): the language list, own-script names, `isRtl`, and `languageFor`. Tested in `i18n/languages.test.ts`.
- `i18n/ur.ts` (new) replaces `i18n/it.ts` (deleted). `i18n/index.ts` changes, and `i18n/i18n.test.ts` gains completeness tests.
- `lib/pay.ts`: `percent` uses Latin digits.
- `lib/naskh.ts` (new): the Noto Naskh Arabic font.
- `lib/venue-server.ts`: carries the languages and the session language.
- `app/[lang]/layout.tsx`: language check, redirect, `lang`/`dir` wrapper.
- `app/q/[token]/page.tsx`: passes the languages to `BrandShell`.
- `app/globals.css`: right-to-left font variables and line height.
- `components/BrandShell.tsx`: `Venue` gains the languages.
- `components/ScanForm.tsx`: the picker shows the venue's languages, sets `dir` on the form, and uses logical classes.
- `components/ScanAgain.tsx`: `lang` and `dir`.
- Logical classes and mirrored arrows: `components/DishSheet.tsx`, `components/PaySheet.tsx`, `components/chat-panel.tsx`, `app/[lang]/orders/[id]/page.tsx`.
- Tests whose `it` changes to `ur`: `components/allergen-chip.test.tsx`, `components/CallWaiter.test.tsx`, `components/PaySheet.test.tsx`, `lib/choices.test.ts`, `lib/pay.test.ts`.
- `components/ScanForm.test.tsx`: new.

**Owner app:** `apps/owner-web/src/app/(dashboard)/menu/ingest/page.tsx`: language options become English, Urdu and Arabic.

**End-to-end:** `e2e/urdu.spec.ts` (new), `e2e/one-venue.spec.ts`, `e2e/helpers.ts`.

**Docs:** `README.md`, `docs/architecture.md`.

## Commands used throughout

- **Start the stack:**
  ```bash
  LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait
  ```
- **Python tests:** rebuild `api-test` first.
  ```bash
  docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/<file> -q
  ```
- **Guest unit tests:**
  ```bash
  npm --prefix apps/guest-web exec vitest run <path>
  ```
  `ui` and `owner-web` use the same command with their own prefix.
- **Reset the database:** needed after the date changes, because pickup labels restart at midnight.
  ```bash
  docker compose --profile edge --profile test down -v
  LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait
  docker compose exec -T api alembic upgrade head
  docker compose exec -T api python scripts/seed.py
  ```
- **End-to-end:**
  ```bash
  npx playwright test e2e/<spec>
  ```
- `make` is not available in the shell, so run the underlying commands.
- **Known flaky Python tests** (each passes when run alone):
  - `test_service_calls.py::test_call_resolve_and_cooldown`
  - `test_settle_safeguards.py::test_claim_order_settle_rounds`
  - `test_order_path.py::test_order_integrity_error_non_idempotency_reraised`
- **Never stage** `.gitignore`, `.claude/` or `.impeccable/`.

---

### Task 1: API refuses languages a venue doesn't offer, and the venue response lists its languages

**Files:**
- Modify: `services/api/src/schemas/guest.py:28-50`
- Modify: `services/api/src/routers/guest.py` (`venue_of`, `create_guest_session`, `venue_for_qr`, `patch_guest_session`)
- Modify: `services/api/src/schemas/owner.py:205`
- Modify: `services/api/src/services/guest_chat.py:96-100`
- Modify: `services/inference/mock/src/canned.py:14-18`
- Modify (`"it"` → `"ur"`): `services/api/tests/test_order_path.py`, `services/api/tests/test_schema_constraints.py`, `services/api/tests/test_simulator_concurrency.py`
- Modify: `data/seed/angeethi_house.json` and `data/seed/kehwa_and_crumb.json`. Only `"languages": ["en", "ur"]` changes here; the Urdu content comes in Task 3.
- Create: `services/api/tests/test_guest_languages.py`

- [ ] **Step 1: Write the failing tests**

`services/api/tests/test_guest_languages.py`:

```python
"""A venue offers only its own languages (spec 2026-11-09, phase 1b)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed import load_seed_data, seed_data
from src.auth import GUEST_COOKIE_NAME
from src.models import DiningTable, Restaurant


@pytest.fixture
async def angeethi(db_session: AsyncSession) -> tuple[Restaurant, str]:
    await seed_data(load_seed_data("data/seed/angeethi_house.json"), db_session, rotate_qr=False)
    r = (await db_session.execute(select(Restaurant).where(Restaurant.slug == "angeethi-house"))).scalar_one()
    qr = (await db_session.execute(select(DiningTable.qr_token).where(DiningTable.restaurant_id == r.id))).scalars().first()
    return r, qr


async def _session(client: AsyncClient, qr: str, **body):
    return await client.post("/api/guest/sessions", json={"qr_token": qr, **body})


async def test_venue_lists_its_languages(client: AsyncClient, angeethi):
    _, qr = angeethi
    v = (await client.get(f"/api/guest/venues/{qr}")).json()
    assert v == {"slug": "angeethi-house", "name": "Angeethi House", "languages": ["en", "ur"], "default_language": "en"}
    s = (await _session(client, qr, language="ur")).json()
    assert s["language"] == "ur"
    assert s["venue"]["languages"] == ["en", "ur"]


@pytest.mark.parametrize("lang", ["it", "UR", "ur-PK", "", "fr"])
async def test_unknown_language_refused(client: AsyncClient, angeethi, lang):
    _, qr = angeethi
    assert (await _session(client, qr, language=lang)).status_code == 422


async def test_language_the_venue_does_not_offer_is_refused(client: AsyncClient, angeethi):
    _, qr = angeethi
    resp = await _session(client, qr, language="ar")
    assert resp.status_code == 422
    assert "language" in resp.json()["detail"].lower()


async def test_missing_language_is_the_venue_default(client: AsyncClient, angeethi, db_session: AsyncSession):
    r, qr = angeethi
    r.languages, r.default_language = ["ur"], "ur"  # a venue without English
    await db_session.flush()
    assert (await _session(client, qr)).json()["language"] == "ur"
    assert (await _session(client, qr, language="en")).status_code == 422


async def test_patch_refuses_unoffered_language_and_keeps_the_old_one(client: AsyncClient, angeethi):
    _, qr = angeethi
    created = await _session(client, qr, language="ur")
    client.cookies.set(GUEST_COOKIE_NAME, created.cookies[GUEST_COOKIE_NAME])
    assert (await client.patch("/api/guest/session", json={"language": "ar"})).status_code == 422
    assert (await client.patch("/api/guest/session", json={"language": "it"})).status_code == 422
    assert (await client.get("/api/guest/session")).json()["language"] == "ur"
    assert (await client.patch("/api/guest/session", json={"language": "en"})).json()["language"] == "en"
```

Check the fixture names `client` and `db_session`, the import path of `GUEST_COOKIE_NAME`, and the seed import against `tests/test_order_path.py`, and copy whatever it uses.

- [ ] **Step 2: Run the tests and see them fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_guest_languages.py -q`

Expected: FAIL. The venue has no `languages` key, and `ur` returns 422 from the old Literal.

- [ ] **Step 3: Implement**

`schemas/guest.py`:

```python
SupportedLanguage = Literal["en", "ur", "ar"]


class CreateGuestSessionRequest(BaseModel):
    qr_token: str
    language: SupportedLanguage | None = None  # None: the venue's default
    dietary_preferences: list[DietaryPreference] = []
    allergens_to_avoid: list[EU14Allergen] = []


class GuestVenue(BaseModel):
    """The scanned venue as a guest may see it: public slug, name and offered languages."""

    slug: str
    name: str
    languages: list[str]
    default_language: str
```

`routers/guest.py`:
- Add a helper:

  ```python
  VENUE_COLUMNS = (Restaurant.slug, Restaurant.name, Restaurant.languages, Restaurant.default_language)


  def _venue(row) -> GuestVenue:
      return GuestVenue(slug=row.slug, name=row.name, languages=list(row.languages), default_language=row.default_language)


  def _offered(venue: GuestVenue, language: str) -> str:
      if language not in venue.languages:
          raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This venue does not offer that language")
      return language
  ```

- `venue_of` selects `*VENUE_COLUMNS` and returns `_venue(row)`. `venue_for_qr` does the same with its join.
- In `create_guest_session`, after the table is found:

  ```python
  venue = await venue_of(db, table.restaurant_id)
  language = _offered(venue, payload.language or venue.default_language)
  ```

  Then use `language=language` in the `GuestSession(...)`, and `"venue": venue` in the response.
- In `patch_guest_session`:

  ```python
  venue = await venue_of(db, session.restaurant_id)
  if payload.language is not None:
      session.language = _offered(venue, payload.language)
  ```

  Reuse `venue` in the response. The 422 is raised before any change, so nothing is committed.
- Add `422: {"description": "Language not offered by this venue"}` to the `responses=` of both routes.

`schemas/owner.py:205`: `language: Literal["en", "ur", "ar"] = "en"`. Add the `Literal` import if it is missing.

`services/guest_chat.py`: build `_build_menu_context(items, "en")`, and replace `f"Respond in {guest_language}. "` with `"Respond in English. "`. Leave a one-line comment: `# phase 1b: the assistant answers in English; only its labels are translated`. Keep the `guest_language` parameter so callers are unchanged. If a test in `tests/test_guest_chat*.py` asserts "Respond in it", change it to English and say why in the commit.

`canned.py`: `TRANSLATION = {"language": "ur", "name": "پیزا مارگریٹا", "description": "ٹماٹر، موزاریلا اور تازہ تلسی کے ساتھ کلاسک پیزا"}`.

Seed files: set `"languages": ["en", "ur"]` in the `restaurant` block of both.

Existing tests: replace every language value `"it"` with `"ur"`.
- In `test_order_path.py` and `test_simulator_concurrency.py`: `language="it"`, `languages=["en", "it"]` and `{"language": "it"}`.
- In `test_schema_constraints.py`: `ARRAY['en', 'it'], 'it'` becomes `ARRAY['en', 'ur'], 'ur'`, and the `'it'` translation rows become `'ur'`.
- Leave `ARRAY['it'], 'fr'` (the bad default-language check) as `ARRAY['ur'], 'fr'`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `docker compose --profile test run --rm api-test pytest tests/test_guest_languages.py tests/test_order_path.py tests/test_schema_constraints.py tests/test_simulator_concurrency.py tests/ -q -k "guest or order_path or schema or simulator or chat"`

Expected: PASS, apart from the known flaky tests, which pass alone.

- [ ] **Step 5: Regenerate the API client**

```bash
docker compose up -d --build --wait api
docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json
npm --prefix packages/api-client run generate
```

Expected: `schema.d.ts` shows `language?: ("en" | "ur" | "ar") | null` and `GuestVenue` with `languages` and `default_language`. Run `grep -n '"it"' packages/api-client/src/generated/schema.d.ts` and expect no output.

- [ ] **Step 6: Commit**

```bash
git add services/api/src services/api/tests services/inference/mock/src/canned.py data/seed/angeethi_house.json data/seed/kehwa_and_crumb.json packages/api-client
git commit -m "feat(api): venues offer only their own languages — en, ur, ar; Italian removed

Tests that used 'it' as a sample language now use 'ur'; 'it' is no longer accepted."
```

---

### Task 2: Translated labels for sizes and choices

**Files:**
- Create: `services/api/alembic/versions/0022_label_translations.py`
- Modify: `services/api/src/models/menu.py` (classes `MenuItemOption` ~l.161, `MenuChoiceGroup` ~l.243, `MenuChoice` ~l.279)
- Modify: `services/api/src/routers/guest.py`: `_guest_choice` and the menu loop (~l.330-370)
- Modify: `scripts/seed.py`: option upsert (~l.390-410) and `seed_choices` (~l.135-160)
- Test: `services/api/tests/test_guest_languages.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `test_guest_languages.py`)

```python
from src.models import MenuChoice, MenuChoiceGroup, MenuItem, MenuItemOption


async def _menu(client: AsyncClient, qr: str, lang: str) -> list[dict]:
    created = await _session(client, qr, language=lang)
    client.cookies.set(GUEST_COOKIE_NAME, created.cookies[GUEST_COOKIE_NAME])
    return (await client.get("/api/guest/menu")).json()["items"]


async def _translate_karahi(db: AsyncSession) -> MenuItem:
    from sqlalchemy.orm import selectinload

    item = (
        await db.execute(
            select(MenuItem)
            .options(selectinload(MenuItem.options), selectinload(MenuItem.choice_groups).selectinload(MenuChoiceGroup.choices))
            .join(Restaurant)
            .where(Restaurant.slug == "angeethi-house", MenuItem.category == "Karahi")
        )
    ).scalars().first()
    item.options[0].translations = {"ur": "آدھا کلو"}
    item.choice_groups[0].translations = {"ur": "مرچ"}
    item.choice_groups[0].choices[0].translations = {"ur": "ہلکی"}
    item.choice_groups[0].choices[1].translations = {}  # untranslated: falls back to English
    await db.flush()
    return item


async def test_urdu_labels_reach_the_guest_and_fall_back_to_english(client, angeethi, db_session):
    _, qr = angeethi
    item = await _translate_karahi(db_session)
    dish = next(i for i in await _menu(client, qr, "ur") if i["id"] == str(item.id))
    assert dish["options"][0]["label"] == "آدھا کلو"
    group = dish["choice_groups"][0]
    assert group["label"] == "مرچ"
    assert group["choices"][0]["label"] == "ہلکی"
    assert group["choices"][1]["label"] == item.choice_groups[0].choices[1].label


async def test_english_guest_sees_english_labels(client, angeethi, db_session):
    _, qr = angeethi
    item = await _translate_karahi(db_session)
    dish = next(i for i in await _menu(client, qr, "en") if i["id"] == str(item.id))
    assert dish["options"][0]["label"] == item.options[0].label
    assert dish["choice_groups"][0]["label"] == item.choice_groups[0].label


async def test_translations_never_leak_raw_to_the_guest(client, angeethi, db_session):
    _, qr = angeethi
    await _translate_karahi(db_session)
    for dish in await _menu(client, qr, "ur"):
        assert "translations" not in dish
        for o in dish.get("options", []):
            assert "translations" not in o
```

If the dishes are ordered so that `.first()` is not Chicken Karahi, filter on the name through `MenuTranslation`. The test only needs any Karahi item that has options and groups.

- [ ] **Step 2: Run the tests and see them fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_guest_languages.py -q`

Expected: FAIL with `AttributeError: 'MenuItemOption' object has no attribute 'translations'`, or the column missing.

- [ ] **Step 3: Implement**

`alembic/versions/0022_label_translations.py`:

```python
"""Per-language labels for sizes, choice groups and choices (guest-facing only).

Revision ID: 0022_label_translations
Revises: 0021_dish_choices
Create Date: 2026-11-12 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_label_translations"
down_revision: str | None = "0021_dish_choices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("menu_item_option", "menu_choice_group", "menu_choice")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("translations", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "translations")
```

In `models/menu.py`, add to each of the three classes, under `label`:

```python
    # {"ur": "…"}: what the guest sees in that language; kitchen, tickets and bills keep `label`.
    translations: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
```

Import `JSONB` from `sqlalchemy.dialects.postgresql` and `text` from `sqlalchemy`, if they are not already imported.

In `routers/guest.py`, add the helper:

```python
def _label(obj, language: str) -> str:
    return (obj.translations or {}).get(language) or obj.label
```

- Change `_guest_choice(c, avoid)` to `_guest_choice(c, avoid, language)`, using `label=_label(c, language)`.
- In the menu loop, use `GuestMenuOption(id=o.id, label=_label(o, session.language), price=o.price)`, and `label=_label(g, session.language)` for the group.
- Pass `session.language` into `_guest_choice`.
- Grep every caller of `_guest_choice` and update them all.

In `scripts/seed.py`:
- Option update branch: `opt.translations = opt_data.get("translations", {})`.
- New `MenuItemOption(...)`: add `translations=opt_data.get("translations", {})`.
- `MenuChoiceGroup(...)`: add `translations=g.get("translations", {})`.
- `MenuChoice(...)`: add `translations=c.get("translations", {})`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `docker compose --profile test run --rm api-test pytest tests/test_guest_languages.py tests/test_order_path.py tests/test_choices*.py -q`

Expected: PASS.

Then check that the migration upgrades and downgrades cleanly:

```bash
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic downgrade -1
docker compose exec -T api alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add services/api/alembic/versions/0022_label_translations.py services/api/src/models/menu.py services/api/src/routers/guest.py scripts/seed.py services/api/tests/test_guest_languages.py
git commit -m "feat(api): Urdu labels for sizes and choices reach the guest; kitchen keeps English"
```

---

### Task 3: Urdu menus for Angeethi House and Kehwa & Crumb

**Files:**
- Modify: `data/seed/angeethi_house.json` (27 items, 20 options, 6 groups and their choices)
- Modify: `data/seed/kehwa_and_crumb.json` (23 items, 15 options, 5 groups and their choices)
- Create: `services/api/tests/test_seed_urdu.py`

- [ ] **Step 1: Write the failing test**

```python
"""Every guest-visible menu word at the Pakistani venues has an Urdu version (phase 1b)."""

import json
import re

import pytest

ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")
FILES = ["data/seed/angeethi_house.json", "data/seed/kehwa_and_crumb.json"]


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("path", FILES)
def test_venue_offers_english_and_urdu(path):
    r = _load(path)["restaurant"]
    assert r["languages"] == ["en", "ur"]
    assert r["default_language"] == "en"


@pytest.mark.parametrize("path", FILES)
def test_every_dish_size_and_choice_has_urdu(path):
    missing = []
    for item in _load(path)["items"]:
        ur = item["translations"].get("ur") or {}
        if not ARABIC_SCRIPT.search(ur.get("name", "")):
            missing.append(f"{item['key']}: name")
        if item["translations"]["en"].get("description") and not ARABIC_SCRIPT.search(ur.get("description") or ""):
            missing.append(f"{item['key']}: description")
        for o in item.get("options", []):
            if not ARABIC_SCRIPT.search(o.get("translations", {}).get("ur", "")) and not re.fullmatch(r"[\d½¼¾.]+\s*(kg|g|ml|l)?", o["label"]):
                missing.append(f"{item['key']}: option {o['label']}")
        for g in item.get("choice_groups", []):
            if not ARABIC_SCRIPT.search(g.get("translations", {}).get("ur", "")):
                missing.append(f"{item['key']}: group {g['label']}")
            for c in g["choices"]:
                if not ARABIC_SCRIPT.search(c.get("translations", {}).get("ur", "")):
                    missing.append(f"{item['key']}: choice {c['label']}")
    assert missing == []


@pytest.mark.parametrize("path", FILES)
def test_urdu_never_names_the_platform(path):
    assert "Mise" not in json.dumps(_load(path), ensure_ascii=False).replace("_note", "")
```

The option exemption covers pure measures such as `1 kg`. Those still get an Urdu translation (`ایک کلو`) where it reads more naturally, but a bare number is allowed.

- [ ] **Step 2: Run the test and see it fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_seed_urdu.py -q`

Expected: FAIL, with every item listed as missing.

- [ ] **Step 3: Write the Urdu content**

Rules (from the spec and the research note):
- **Dish names are written as Pakistani customers say them**, in Urdu script. They are transliterated, not translated.
  - Required spellings, which the end-to-end test uses: Chicken Karahi → `چکن کڑاہی`, Naan → `نان`, Doodh Patti Chai → `دودھ پتی چائے`, Cappuccino → `کیپوچینو`.
  - Others: Chicken Tikka → `چکن تکہ`, Seekh Kebab → `سیخ کباب`, Daal → `دال`, Raita → `رائتہ`, Lassi → `لسی`.
- **Descriptions** are short natural Urdu, in a polite neutral register: `ٹماٹر، ادرک اور ہری مرچ کے ساتھ کڑاہی میں پکا چکن`.
- **Sizes and groups:**
  - Sizes: `½ kg` → `آدھا کلو`, `1 kg` → `ایک کلو`, Regular → `ریگولر`, Large → `لارج`.
  - Groups: Spice → `مرچ`, Leave out → `یہ نہ ڈالیں`, Extras → `اضافی`.
  - Spice levels: Mild → `ہلکی`, Medium → `درمیانی`, Hot → `تیز`.
  - Chai sweetness: Normal → `نارمل`.
- **Choices:** Onions → `پیاز`, Green chilli → `ہری مرچ`, Ginger → `ادرک`, Extra shot → `ایکسٹرا شاٹ`, Almond milk → `بادام کا دودھ`.
- Add `"ur": {"name": …, "description": …}` next to `"en"` in each item's `translations`. Add `"translations": {"ur": "…"}` to every option, group and choice.
- **Do not change** any `label`, `key`, price, allergen or flag. The IDs come from the labels (`uuid5` in `seed.py`), so changing a label would orphan order history.
- Ingredients stay English.
- Write the JSON as UTF-8 with Urdu characters in place (`ensure_ascii=False` if you script it), and keep the file's existing 2-space indent.

- [ ] **Step 4: Run the test and see it pass, then reseed**

Run: `docker compose --profile test run --rm api-test pytest tests/test_seed_urdu.py tests/test_seed*.py -q`

Expected: PASS.

Then:

```bash
docker compose exec -T api python scripts/seed.py
```

Expected: it finishes without errors and reports items updated.

- [ ] **Step 5: Commit**

```bash
git add data/seed/angeethi_house.json data/seed/kehwa_and_crumb.json services/api/tests/test_seed_urdu.py
git commit -m "feat(data): Urdu dish, size and choice names for Angeethi House and Kehwa & Crumb (draft translation)"
```

---

### Task 4: Money stays Latin-digit and isolated

**Files:**
- Modify: `packages/ui/src/format.ts`
- Modify: `packages/ui/src/format.test.ts`
- Modify: `packages/ui/src/theme.css:197-201`
- Modify: `apps/guest-web/src/lib/pay.ts:156-158`
- Modify (in Task 5, with the dictionary swap): `apps/guest-web/src/lib/pay.test.ts`

- [ ] **Step 1: Write the failing tests**

In `packages/ui/src/format.test.ts`, replace the Italian cases ("formats euros for Italian with comma decimals", and the `"it"` GBP and AED lines) with:

```ts
const EASTERN_DIGITS = /[٠-٩۰-۹]/;

it("keeps Latin digits for Arabic and Urdu pages", () => {
  for (const locale of ["ar", "ur", "ar-AE"]) {
    for (const [amount, currency] of [[105, "AED"], [23.63, "GBP"], [1250, "PKR"]] as const) {
      const text = formatPrice(amount, currency, locale);
      expect(text).not.toMatch(EASTERN_DIGITS);
      expect(text.replace(/[^\d.]/g, "")).toMatch(/^\d/);
    }
  }
});

it("PKR is the same in every language", () => {
  expect(formatPrice(1250, "PKR", "ur")).toBe(formatPrice(1250, "PKR", "en"));
  expect(formatPrice(1250, "PKR", "ur")).toBe("Rs 1,250");
});
```

The commit message says why: Italian is no longer a guest language, so its formatting cases were replaced by the two new page languages.

- [ ] **Step 2: Run the tests and see them fail**

Run: `npm --prefix packages/ui exec vitest run src/format.test.ts`

Expected: FAIL, because `ar` produces Arabic-Indic digits.

- [ ] **Step 3: Implement**

In `format.ts`, change the doc comment to `e.g. €13.00 (en), Rs 2,100 (PKR, whole rupees); digits are always Latin.` and the generic branch to:

```ts
    return new Intl.NumberFormat(locale, { style: "currency", currency, numberingSystem: "latn" }).format(amount);
```

In `theme.css`, add after `.figure { … }`, still inside the same layer:

```css
  /* Money reads left to right in Latin digits inside Urdu and Arabic text. */
  [dir="rtl"] .figure {
    direction: ltr;
    unicode-bidi: isolate;
  }
```

In `apps/guest-web/src/lib/pay.ts`:

```ts
/** A rate as a fraction ("0.125") to a percentage in the guest's language, always in Latin digits: "12.5". */
export const percent = (rate: string, lang: string) =>
  new Intl.NumberFormat(lang, { maximumFractionDigits: 2, numberingSystem: "latn" }).format(Number(rate) * 100);
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npm --prefix packages/ui exec vitest run`, then `npm --prefix apps/guest-web exec vitest run src/lib/pay.test.ts src/lib/money-face.test.tsx src/lib/figure.test.tsx`

Expected: PASS. `pay.test.ts` still uses `"it"` here and changes in Task 5.

- [ ] **Step 5: Commit**

```bash
git add packages/ui/src/format.ts packages/ui/src/format.test.ts packages/ui/src/theme.css apps/guest-web/src/lib/pay.ts
git commit -m "feat(ui): money and rates stay Latin-digit and left-to-right in Urdu and Arabic

Italian price-format cases replaced by ar/ur cases: Italian is no longer a guest language."
```

---

### Task 5: Urdu dictionary replaces Italian

**Files:**
- Create: `apps/guest-web/src/i18n/languages.ts`
- Create: `apps/guest-web/src/i18n/languages.test.ts`
- Create: `apps/guest-web/src/i18n/ur.ts`
- Delete: `apps/guest-web/src/i18n/it.ts`
- Modify: `apps/guest-web/src/i18n/index.ts:1-12`
- Modify: `apps/guest-web/src/i18n/i18n.test.ts`
- Modify (`it` → `ur`): `apps/guest-web/src/components/allergen-chip.test.tsx`, `apps/guest-web/src/components/CallWaiter.test.tsx`, `apps/guest-web/src/components/PaySheet.test.tsx`, `apps/guest-web/src/lib/choices.test.ts`, `apps/guest-web/src/lib/pay.test.ts`

- [ ] **Step 1: Write the failing tests**

`i18n/languages.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { GUEST_LANGUAGES, LANGUAGE_NAMES, isGuestLanguage, isRtl, languageFor } from "./languages";

describe("guest languages", () => {
  it("knows exactly en, ur and ar", () => {
    expect([...GUEST_LANGUAGES]).toEqual(["en", "ur", "ar"]);
    for (const bad of ["it", "EN", "ur-PK", "", "..", "en/../ar"]) expect(isGuestLanguage(bad)).toBe(false);
  });

  it("names each language in its own script", () => {
    expect(LANGUAGE_NAMES).toEqual({ en: "English", ur: "اردو", ar: "العربية" });
  });

  it("only Urdu and Arabic are right-to-left", () => {
    expect([isRtl("en"), isRtl("ur"), isRtl("ar")]).toEqual([false, true, true]);
  });

  it("the page follows the visit's language when the venue offers it", () => {
    const venue = { languages: ["en", "ur"], defaultLanguage: "en" };
    expect(languageFor({ ...venue, language: "ur" })).toBe("ur");
    expect(languageFor({ ...venue, language: "en" })).toBe("en");
  });

  it("a visit language the venue does not offer falls back to the venue default", () => {
    expect(languageFor({ languages: ["en", "ur"], defaultLanguage: "en", language: "it" })).toBe("en");
    expect(languageFor({ languages: ["en"], defaultLanguage: "en", language: "ar" })).toBe("en");
    expect(languageFor({ languages: ["en", "ur"], defaultLanguage: "en", language: undefined })).toBe("en");
  });

  it("a broken default never yields a language outside the known three", () => {
    expect(languageFor({ languages: [], defaultLanguage: "it", language: "it" })).toBe("en");
  });
});
```

In `i18n/i18n.test.ts`, replace the Italian cases with:

```ts
import { en } from "./en";
import { ur } from "./ur";

function leaves(obj: unknown, prefix = ""): [string, string][] {
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    typeof v === "string" ? [[`${prefix}${k}`, v] as [string, string]] : leaves(v, `${prefix}${k}.`),
  );
}

describe("Urdu dictionary", () => {
  const enLeaves = new Map(leaves(en));
  const urLeaves = new Map(leaves(ur));

  it("has every English key and nothing extra", () => {
    expect([...urLeaves.keys()].sort()).toEqual([...enLeaves.keys()].sort());
  });

  it("has no empty value and never names the platform", () => {
    for (const [key, value] of urLeaves) {
      expect(value.trim(), key).not.toBe("");
      expect(value, key).not.toMatch(/mise/i);
    }
  });

  it("keeps every placeholder of the English text", () => {
    for (const [key, value] of enLeaves) {
      const holes = value.match(/\{\w+\}/g) ?? [];
      for (const hole of holes) expect(urLeaves.get(key), `${key} ${hole}`).toContain(hole);
    }
  });

  it("is written in Urdu script, apart from brand and method names", () => {
    const latinOnly = new Set(["pay.methods.wallet", "pay.methods.raast", "pay.labels.raast_id", "pay.labels.jazzcash", "pay.labels.easypaisa", "pay.labels.iban"]);
    for (const [key, value] of urLeaves) {
      if (!latinOnly.has(key)) expect(value, key).toMatch(/[؀-ۿ]/);
    }
  });

  it("serves Urdu for ur and English for an unknown locale", () => {
    expect(getDictionary("ur").allergenStatus.contains).toBe(ur.allergenStatus.contains);
    expect(getDictionary("it")).toBe(en);
    expect(translate("it", "allergenStatus.contains")).toBe("Contains");
  });
});
```

Keep the existing English and fallback cases that don't mention Italian. Adjust the `getDictionary`/`translate` imports to whatever the file already imports.

In the other five test files, change every Italian case to Urdu:
- `allergen-chip.test.tsx`: "renders localized text for Urdu locale", with `locale="ur"`, expecting `ur.allergenStatus.contains` (import `ur`).
- `CallWaiter.test.tsx:31`: `lang: "ur"`, with the expected strings taken from `ur.call.*`.
- `PaySheet.test.tsx:137`: "names the rate in Urdu with Latin digits". Render with `lang="ur"`, expect the text built from `ur.pay.vatIncluded` with `20` and the formatted amount, and expect no `[٠-٩۰-۹]` anywhere in the dialog.
- `choices.test.ts:120`: "uses the Urdu leave-out wording", expecting `cartChoiceText(line, money, getDictionary("ur").dish.leaveOut)` to equal `"Hot, Extra shot +Rs 150, " + ur.dish.leaveOut.replace("{label}", "onions")`.
- `pay.test.ts`:
  - `claimMessage(claim("card"), getDictionary("ur"), "ur", "PKR")` equals `ur.pay.card`.
  - `percent("0.1250", "ur")` is `"12.5"`, and `percent("0.1250", "ar")` is `"12.5"`.
  - `percent("0.2000", "ur")` is `"20"`.
  - The `paidText` cases are rebuilt from `ur.pay.paidAmount` / `ur.pay.paidVatIncluded` with Latin numbers.
  - `serviceLine(…, getDictionary("ur").menu.serviceNotice, "ur")`.
  - `menuTaxNote(true, getDictionary("ur"))` equals `ur.menu.pricesIncludeVat`.

Build expected strings from `ur` rather than pasting Urdu literals, so the tests check the wiring and the dictionary test checks the words.

- [ ] **Step 2: Run the tests and see them fail**

Run: `npm --prefix apps/guest-web exec vitest run src/i18n src/components/allergen-chip.test.tsx src/components/CallWaiter.test.tsx src/components/PaySheet.test.tsx src/lib/choices.test.ts src/lib/pay.test.ts`

Expected: FAIL, because `./languages` and `./ur` are not found.

- [ ] **Step 3: Implement**

`i18n/languages.ts`:

```ts
/** The guest app's languages: English plus each venue's local language (spec 2026-11-09, phase 1b). */
export const GUEST_LANGUAGES = ["en", "ur", "ar"] as const;
export type GuestLanguage = (typeof GUEST_LANGUAGES)[number];

/** Each language in its own name and script, as the scan page shows it. */
export const LANGUAGE_NAMES: Record<GuestLanguage, string> = { en: "English", ur: "اردو", ar: "العربية" };

export const isGuestLanguage = (s: string): s is GuestLanguage => (GUEST_LANGUAGES as readonly string[]).includes(s);

export const isRtl = (lang: string) => lang === "ur" || lang === "ar";

/** The language a guest page should be in: the visit's, if the venue offers it, else the venue's default. */
export function languageFor(v: { languages: string[]; defaultLanguage: string; language?: string }): GuestLanguage {
  if (v.language && v.languages.includes(v.language) && isGuestLanguage(v.language)) return v.language;
  return isGuestLanguage(v.defaultLanguage) ? v.defaultLanguage : "en";
}
```

`i18n/ur.ts`: a complete `TranslationDict`, in the same key order as `en.ts`, starting:

```ts
import type { TranslationDict } from "./types";

// DRAFT TRANSLATION: hand-written, awaiting review by a native Urdu speaker. Until then the allergen
// and safety text below (staffNotice, ui.noticeShort, allergens, allergenStatus,
// ui.allergenWarning*, ui.allergenAckCheckbox, dish.leaveOutNotice) must not be relied on alone;
// the allergen status itself is always decided by server code.
export const ur: TranslationDict = {
  staffNotice:
    "نوٹ: الرجی کی معلومات اور غذائی نشانیاں صرف رہنمائی کے لیے ہیں۔ آرڈر کرنے سے پہلے براہِ کرم عملے سے الرجی کے تمام خطرات کی تصدیق کر لیں۔ یہ طبی ضمانت نہیں ہے۔",
  allergens: {
    gluten: "گلوٹن",
    milk: "دودھ",
    eggs: "انڈے",
    fish: "مچھلی",
    crustaceans: "جھینگا اور کیکڑا",
    molluscs: "سیپ اور گھونگے",
    tree_nuts: "خشک میوے",
    peanuts: "مونگ پھلی",
    soy: "سویا",
    celery: "اجوائن کا پتا",
    mustard: "سرسوں",
    sesame: "تل",
    sulphites: "سلفائٹس",
    lupin: "لیوپن",
  },
  dietary: { vegetarian: "سبزی خور", vegan: "ویگن", gluten_free: "گلوٹن سے پاک" },
  allergenStatus: { contains: "شامل ہے", unverified: "تصدیق شدہ نہیں", no_declared_match: "کوئی ظاہر شدہ الرجن نہیں" },
  ui: {
    welcomeTitle: "{venue} میں خوش آمدید",
    scanAgain: "براہِ کرم اپنی ٹیبل کا QR کوڈ دوبارہ اسکین کریں۔",
    noticeShort: "الرجی کی معلومات صرف رہنمائی ہیں۔ آرڈر سے پہلے عملے سے پوچھ لیں۔",
    allergyToggle: "کوئی الرجی یا خاص غذا؟ ہمیں بتائیں",
    selectLanguage: "زبان",
    continueToMenu: "مینو دیکھیں",
    cartTitle: "آپ کا آرڈر",
    placeOrder: "آرڈر کی تصدیق کریں",
    allergenWarningTitle: "الرجی کی تنبیہ",
    allergenAckCheckbox: "میں نے عملے سے بات کر لی ہے اور اس آرڈر کے الرجی کے خطرات سمجھتا/سمجھتی ہوں",
    backToMenu: "مینو پر واپس",
    // …every remaining ui key, translated
  },
  // …menu, dish, bill, pay, counter, call, order: every key, translated
};
```

The implementer writes every remaining value. Rules:
- Use the polite register (آپ).
- Keep loanwords as customers say them: آرڈر, مینو, بل, ٹیبل, ویٹر, QR.
- Keep every `{placeholder}` and the `“{button}”` quoting.
- Keep payment brand names (JazzCash, Easypaisa, Raast, IBAN) in Latin script.
- Say nothing the English doesn't say.

Fixed strings that the end-to-end tests depend on:

| Key | Urdu |
|---|---|
| `ui.continueToMenu` | `مینو دیکھیں` |
| `ui.placeOrder` | `آرڈر کی تصدیق کریں` |
| `ui.cartTitle` | `آپ کا آرڈر` |
| `ui.checkout` | `آرڈر دیکھیں` |
| `pay.button` | `بل ادا کریں` |
| `pay.methods.cash` | `نقد` |
| `pay.cash` | `ویٹر {total} لینے آ رہا ہے۔` |
| `dish.addToOrder` | `آرڈر میں شامل کریں · {total}` |
| `ui.allergenAckCheckbox` | the value shown above |

`i18n/index.ts`: replace `it` with `ur` in the import, the `export { en, ur }` line and the `dictionaries` map. Delete `it.ts`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `npm --prefix apps/guest-web exec vitest run`, then `npm --prefix apps/guest-web run lint`

Expected: all PASS, and lint is clean.

Check that Italian is gone from the guest app:

```bash
grep -rn "Italian\|Italiano\|from \"./it\"" apps/guest-web/src
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src/i18n apps/guest-web/src/components/allergen-chip.test.tsx apps/guest-web/src/components/CallWaiter.test.tsx apps/guest-web/src/components/PaySheet.test.tsx apps/guest-web/src/lib/choices.test.ts apps/guest-web/src/lib/pay.test.ts
git commit -m "feat(guest): Urdu dictionary replaces Italian (safety text marked draft translation)

Italian test cases rewritten for Urdu: Italian is no longer a guest language."
```

---

### Task 6: Right-to-left pages on the server, and the Urdu font

**Files:**
- Create: `apps/guest-web/src/lib/naskh.ts`
- Modify: `apps/guest-web/src/lib/venue-server.ts`
- Modify: `apps/guest-web/src/app/[lang]/layout.tsx`
- Modify: `apps/guest-web/src/app/q/[token]/page.tsx`
- Modify: `apps/guest-web/src/components/BrandShell.tsx:11-14` (`Venue`)
- Modify: `apps/guest-web/src/components/ScanAgain.tsx`
- Modify: `apps/guest-web/src/app/globals.css` (after the `[data-brand]` block)
- Test: `apps/guest-web/src/lib/venue-server.test.ts` (create, or extend if it exists)

- [ ] **Step 1: Write the failing test**

`lib/venue-server.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "signed" }) }) }));
vi.mock("react", async (orig) => ({ ...(await orig<typeof import("react")>()), cache: (f: unknown) => f }));

const session = {
  id: "visit-1",
  language: "ur",
  venue: { slug: "angeethi-house", name: "Angeethi House", languages: ["en", "ur"], default_language: "en" },
};

afterEach(() => vi.unstubAllGlobals());

describe("venueFromSession", () => {
  it("carries the venue's languages and the visit's language", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(session))));
    const { venueFromSession } = await import("./venue-server");
    expect(await venueFromSession()).toEqual({
      slug: "angeethi-house",
      name: "Angeethi House",
      visitId: "visit-1",
      languages: ["en", "ur"],
      defaultLanguage: "en",
      language: "ur",
    });
  });

  it("an old API answer without languages means English only", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...session, venue: { slug: "x", name: "X" } }))));
    const { venueFromSession } = await import("./venue-server");
    expect(await venueFromSession()).toMatchObject({ languages: ["en"], defaultLanguage: "en" });
  });
});
```

Keep the `ScanAgain` test in `components/ScanAgain.test.tsx`, and add:

```tsx
it("an Urdu not-found page is right-to-left", () => {
  const html = renderToStaticMarkup(<ScanAgain lang="ur" />);
  expect(html).toMatch(/<main[^>]* lang="ur"/);
  expect(html).toMatch(/<main[^>]* dir="rtl"/);
});
```

Use the render helper that the file already uses.

- [ ] **Step 2: Run the tests and see them fail**

Run: `npm --prefix apps/guest-web exec vitest run src/lib/venue-server.test.ts src/components/ScanAgain.test.tsx`

Expected: FAIL. There is no `languages` field, and no `dir` attribute.

- [ ] **Step 3: Implement**

`lib/venue-server.ts`:
- `ServerVenue` gains:

  ```ts
  /** Languages this venue offers, and its default (phase 1b). */
  languages: string[];
  defaultLanguage: string;
  /** The visit's chosen language; only on session-resolved pages. */
  language?: string;
  ```

- Add the helper:

  ```ts
  function venueOf(v: { slug: string; name: string; languages?: string[]; default_language?: string }) {
    return { slug: v.slug, name: v.name, languages: v.languages ?? ["en"], defaultLanguage: v.default_language ?? "en" };
  }
  ```

- `venueFromSession` returns `s?.venue?.slug ? { ...venueOf(s.venue), visitId: s.id, language: s.language } : null`.
- `venueFromQr` returns `v?.slug ? venueOf(v) : null`.

`lib/naskh.ts`:

```ts
import { Noto_Naskh_Arabic } from "next/font/google";

/** Urdu and Arabic text (Naskh: a third of Nastaliq's size, no clipping; research urdu_ui.md).
 *  Not preloaded, and limited to Arabic code points, so English pages never download it. */
export const naskh = Noto_Naskh_Arabic({
  subsets: ["arabic"],
  weight: ["400", "700"],
  display: "swap",
  preload: false,
  variable: "--font-naskh",
});
```

`app/[lang]/layout.tsx` (the full component body):

```tsx
import { notFound, redirect } from "next/navigation";
import { isGuestLanguage, isRtl, languageFor } from "../../i18n/languages";
import { naskh } from "../../lib/naskh";
// …existing imports

export default async function GuestLayout({ children, params }: { children: React.ReactNode; params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isGuestLanguage(lang)) notFound();
  const v = await venueFromSession();
  if (!v) return <ScanAgain lang={lang} />;
  const want = languageFor(v);
  if (want !== lang) redirect(`/${want}/menu`);
  const rtl = isRtl(lang);
  return (
    // display: contents keeps the page layout; lang and dir are inherited, and sheets (<dialog>) sit inside.
    <div lang={lang} dir={rtl ? "rtl" : "ltr"} className={`contents ${rtl ? naskh.variable : ""}`}>
      <BrandShell key={v.slug} venue={{ slug: v.slug, name: v.name, languages: v.languages, defaultLanguage: v.defaultLanguage }} welcomeFor={v.visitId}>
        {children}
      </BrandShell>
    </div>
  );
}
```

`components/BrandShell.tsx`: `Venue` gains optional `languages?: string[]` and `defaultLanguage?: string`. The context default value gets `languages: ["en"], defaultLanguage: "en"`, and the provider passes them through from `venue`. Check where the context value is built and add the two fields there.

`app/q/[token]/page.tsx`: no change is needed beyond the type, because `venue={v}` now carries the languages. Confirm with `tsc`.

`components/ScanAgain.tsx`: import `isRtl`, and add `lang={lang} dir={isRtl(lang) ? "rtl" : "ltr"}` to `<main>`.

`app/globals.css`, after the `[data-brand]` block:

```css
/* Urdu and Arabic pages: Naskh for Arabic-script text, the venue's own fonts for Latin text
   (Naskh is limited to Arabic code points), and the taller line Naskh needs. */
[dir="rtl"] [data-brand] {
  --font-sans: var(--font-naskh), var(--brand-text);
  --font-serif: var(--font-naskh), var(--brand-display);
  line-height: 1.7;
}
```

This works because `[data-brand]` computes `font-family: var(--font-sans)` on the same element, and this rule is more specific.

- [ ] **Step 4: Run the tests and see them pass**

Run: `npm --prefix apps/guest-web exec vitest run`, `npm --prefix apps/guest-web run lint`, and `npm --prefix apps/guest-web exec tsc --noEmit`

Expected: PASS.

- [ ] **Step 5: Check by hand in the browser pane**

Rebuild: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait`.

1. Create an Urdu session with a direct API call, or wait for Task 7's picker.
2. Open `http://localhost:3000/ur/menu`.
   - Expected: the `<div dir="rtl" lang="ur">` is in the first HTML response. Check with View Source or `curl -s -b "mise_guest=…" http://localhost:3000/ur/menu | grep -o 'dir="rtl"'`.
   - Expected: Urdu dish names render in Naskh, and prices read `Rs 1,100` left to right.
3. Open `/it/menu`. Expected: the neutral not-found page.
4. Open `/ar/menu` with an English session. Expected: a redirect to `/en/menu`.
5. Open `/en/menu` with an English session in the network panel. Expected: no `noto-naskh` font request.

- [ ] **Step 6: Commit**

```bash
git add apps/guest-web/src/lib/naskh.ts apps/guest-web/src/lib/venue-server.ts apps/guest-web/src/lib/venue-server.test.ts "apps/guest-web/src/app/[lang]/layout.tsx" apps/guest-web/src/components/BrandShell.tsx apps/guest-web/src/components/ScanAgain.tsx apps/guest-web/src/components/ScanAgain.test.tsx apps/guest-web/src/app/globals.css
git commit -m "feat(guest): Urdu pages are right-to-left from the server, in Noto Naskh; wrong language redirects"
```

---

### Task 7: Scan page shows only the venue's languages; logical layout everywhere

**Files:**
- Modify: `apps/guest-web/src/components/ScanForm.tsx`
- Create: `apps/guest-web/src/components/ScanForm.test.tsx`
- Modify: `apps/guest-web/src/components/DishSheet.tsx:231`
- Modify: `apps/guest-web/src/components/PaySheet.tsx:171`
- Modify: `apps/guest-web/src/components/chat-panel.tsx:76`
- Modify: `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx:372`

- [ ] **Step 1: Write the failing tests**

`components/ScanForm.test.tsx`:

```tsx
// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
let venue = { slug: "angeethi-house", name: "Angeethi House", branded: false, languages: ["en", "ur"], defaultLanguage: "en" };
vi.mock("./BrandShell", () => ({ useVenue: () => venue }));

import { ScanForm } from "./ScanForm";

beforeEach(() => {
  push.mockReset();
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 201 })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ScanForm languages", () => {
  it("offers only the venue's languages, each in its own name", () => {
    render(<ScanForm token="t" />);
    expect(screen.getByRole("button", { name: "English" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "اردو" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Italiano|العربية/ })).toBeNull();
  });

  it("shows no picker when the venue has one language", () => {
    venue = { ...venue, languages: ["en"] };
    render(<ScanForm token="t" />);
    expect(screen.queryByRole("button", { name: "English" })).toBeNull();
    expect(screen.queryByText("Language")).toBeNull();
    venue = { ...venue, languages: ["en", "ur"] };
  });

  it("choosing Urdu turns the form right-to-left and sends ur, then opens /ur/menu", async () => {
    const { container } = render(<ScanForm token="t" />);
    fireEvent.click(screen.getByRole("button", { name: "اردو" }));
    expect(container.querySelector('[dir="rtl"][lang="ur"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "مینو دیکھیں" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/ur/menu"));
    const body = JSON.parse((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.language).toBe("ur");
  });

  it("starts on the venue's default language", () => {
    venue = { ...venue, defaultLanguage: "ur" };
    const { container } = render(<ScanForm token="t" />);
    expect(container.querySelector('[dir="rtl"]')).not.toBeNull();
    venue = { ...venue, defaultLanguage: "en" };
  });

  it("the selected language is announced as pressed", () => {
    render(<ScanForm token="t" />);
    expect(screen.getByRole("button", { name: "English" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "اردو" }).getAttribute("aria-pressed")).toBe("false");
  });
});
```

If `@testing-library/react` is not installed in guest-web, use the render style of an existing jsdom test (for example `CallWaiter.test.tsx`).

- [ ] **Step 2: Run the tests and see them fail**

Run: `npm --prefix apps/guest-web exec vitest run src/components/ScanForm.test.tsx`

Expected: FAIL. The picker still shows a hard-coded "🇮🇹 Italiano".

- [ ] **Step 3: Implement**

In `ScanForm.tsx`:
- Imports: `import { LANGUAGE_NAMES, isGuestLanguage, isRtl, type GuestLanguage } from "../i18n/languages";`
- State:

  ```tsx
  const { slug, name, branded, languages = ["en"], defaultLanguage = "en" } = useVenue();
  const offered = languages.filter(isGuestLanguage);
  const [language, setLanguage] = useState<GuestLanguage>(isGuestLanguage(defaultLanguage) ? defaultLanguage : "en");
  ```

- The outermost `<div className="min-h-screen …">` gains `lang={language} dir={isRtl(language) ? "rtl" : "ltr"}`.
- Replace the language card with:

  ```tsx
  {offered.length > 1 && (
    <div className="bg-card p-4 rounded-2xl border border-line space-y-2.5">
      <p className="block text-xs font-semibold uppercase tracking-wider text-ink-muted">{dict.ui.selectLanguage}</p>
      <div className="grid grid-cols-2 gap-2">
        {offered.map((code) => (
          <button
            key={code}
            type="button"
            lang={code}
            aria-pressed={language === code}
            onClick={() => setLanguage(code)}
            className={`py-2 px-3 rounded-xl text-sm font-medium transition-all ${
              language === code ? "bg-terracotta text-cream shadow-md shadow-ink/10" : "bg-paper-2 text-ink-muted hover:bg-line"
            }`}
          >
            {LANGUAGE_NAMES[code]}
          </button>
        ))}
      </div>
    </div>
  )}
  ```

  The `<label>` with no control becomes a `<p>`. The flags are dropped: a flag is a country, not a language.
- Line 191: `text-left` becomes `text-start`. Line 198: `ml-1` becomes `ms-1`.

Other components:
- `DishSheet.tsx:231`: `ml-2` → `ms-2`.
- `PaySheet.tsx:171`: `left-[22px]` → `start-[22px]`, and `left-0.5` → `start-0.5`. Tailwind v4 has `start-*` (inset-inline-start).
- `chat-panel.tsx:76`: `fixed right-4` → `fixed end-4`.
- `orders/[id]/page.tsx:372`: `← {dict.ui.backToMenu}` becomes `<span aria-hidden className="inline-block rtl:-scale-x-100">←</span> {dict.ui.backToMenu}`.

Then look for anything missed:

```bash
grep -rnE "\b(ml|mr|pl|pr|left|right|text-left|text-right|rounded-l|rounded-r|border-l|border-r|space-x)-" apps/guest-web/src --include=*.tsx | grep -v test | grep -v "(landing)"
```

Expected: no output. The landing page is the platform demo page, not a guest screen, and stays as it is.

- [ ] **Step 4: Run the tests and see them pass**

Run: `npm --prefix apps/guest-web exec vitest run`, then `npm --prefix apps/guest-web run lint`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src/components/ScanForm.tsx apps/guest-web/src/components/ScanForm.test.tsx apps/guest-web/src/components/DishSheet.tsx apps/guest-web/src/components/PaySheet.tsx apps/guest-web/src/components/chat-panel.tsx "apps/guest-web/src/app/[lang]/orders/[id]/page.tsx"
git commit -m "feat(guest): scan page offers only the venue's languages; guest screens use direction-neutral layout"
```

---

### Task 8: Owner menu import lists English, Urdu and Arabic

**Files:**
- Modify: `apps/owner-web/src/app/(dashboard)/menu/ingest/page.tsx:~110-120`
- Test: the existing ingest page test if one exists (`grep -rln "ingest" apps/owner-web/src --include=*.test.tsx`), otherwise the check below.

- [ ] **Step 1: Change the options**

Replace the language `<option>` list with these, and make sure the state's initial value is `"en"`:

```tsx
<option value="en">English</option>
<option value="ur">Urdu (اردو)</option>
<option value="ar">Arabic (العربية)</option>
```

- [ ] **Step 2: Check**

Run:

```bash
npm --prefix apps/owner-web exec vitest run
npm --prefix apps/owner-web run lint
grep -rn "Italian\|value=\"it\"" apps/owner-web/src
```

Expected: tests PASS, and the grep prints nothing.

- [ ] **Step 3: Commit**

```bash
git add "apps/owner-web/src/app/(dashboard)/menu/ingest/page.tsx"
git commit -m "feat(owner): menu import languages are English, Urdu and Arabic"
```

---

### Task 9: End-to-end, a whole visit in Urdu

**Files:**
- Modify: `e2e/helpers.ts` (`openTableMenu` and `placeOrder` gain an optional language)
- Create: `e2e/urdu.spec.ts`
- Modify: `e2e/one-venue.spec.ts`: add an Urdu walk

- [ ] **Step 1: Extend the helpers**

In `e2e/helpers.ts`:

```ts
const VIEW_MENU: Record<string, string> = { en: "View Menu", ur: "مینو دیکھیں" };
const CONFIRM: Record<string, string> = { en: "Confirm Order", ur: "آرڈر کی تصدیق کریں" };
const ACK: Record<string, string> = {
  en: "I have spoken with staff and understand the allergen risks",
  ur: "میں نے عملے سے بات کر لی ہے اور اس آرڈر کے الرجی کے خطرات سمجھتا/سمجھتی ہوں",
};

export async function openTableMenu(page: Page, qrToken: string, lang: "en" | "ur" = "en") {
  await page.goto(`${GUEST}/q/${qrToken}`);
  if (lang !== "en") await page.getByRole("button", { name: "اردو" }).click();
  await page.getByRole("button", { name: VIEW_MENU[lang] }).click();
  await expect(page).toHaveURL(new RegExp(`/${lang}/menu$`));
  await skipWelcome(page);
}

export async function acknowledgeAllergens(page: Page, lang: "en" | "ur" = "en") {
  const ack = page.getByText(ACK[lang]);
  if (await ack.isVisible()) await ack.click();
}

export async function placeOrder(page: Page, lang: "en" | "ur" = "en") {
  await acknowledgeAllergens(page, lang);
  await page.getByRole("button", { name: CONFIRM[lang] }).click();
  await expect(page).toHaveURL(new RegExp(`/${lang}/orders/[0-9a-f-]{36}$`));
  return page.url().split("/").pop() ?? "";
}
```

Existing callers keep the English default.

- [ ] **Step 2: Write the spec** (`e2e/urdu.spec.ts`)

```ts
import { expect, test, type Page } from "@playwright/test";
import { ANGEETHI, GUEST, approveOrder, clearDemoLimits, openTable, openTableMenu, placeOrder, resetVenue, venueTables, type VenueTable } from "./helpers";

// Phase 1b: a guest at Angeethi House uses the app in Urdu, right to left, with Latin-digit money.

const EASTERN_DIGITS = /[٠-٩۰-۹]/;
let tables: Record<string, VenueTable>;

test.beforeEach(() => clearDemoLimits());

test.describe.serial("Urdu at Angeethi House", () => {
  test.beforeAll(async () => {
    await resetVenue(ANGEETHI);
    tables = await venueTables(ANGEETHI);
  });

  async function urduMenu(page: Page, label: string) {
    await openTable(ANGEETHI, label);
    await openTableMenu(page, tables[label].qr_token, "ur");
  }

  test("the scan page offers English and Urdu only, and Urdu turns it right-to-left", async ({ page }) => {
    await page.goto(`${GUEST}/q/${tables.T1.qr_token}`);
    await expect(page.getByRole("button", { name: "English" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Italiano|العربية/ })).toHaveCount(0);
    await page.getByRole("button", { name: "اردو" }).click();
    await expect(page.locator('[dir="rtl"][lang="ur"]').first()).toBeVisible();
  });

  test("the menu is Urdu, right-to-left, with Rs prices in Latin digits, from the first byte", async ({ page }) => {
    await urduMenu(page, "T2");
    const html = await (await page.request.get(`${GUEST}/ur/menu`)).text();
    expect(html).toContain('dir="rtl"');
    await expect(page.getByRole("heading", { name: "چکن کڑاہی" })).toBeVisible();
    const price = page.locator(".figure").filter({ hasText: /^Rs\s[\d,]+$/ }).first();
    await expect(price).toBeVisible();
    await expect(price).toHaveCSS("direction", "ltr");
    expect(await page.locator("main").innerText()).not.toMatch(EASTERN_DIGITS);
  });

  test("an order is placed and paid in Urdu; the kitchen still reads English", async ({ page, browser }) => {
    test.setTimeout(120_000);
    await urduMenu(page, "T3");
    await page.getByRole("button", { name: "نان", exact: false }).first().click();
    await page.getByRole("button", { name: /آرڈر دیکھیں/ }).click();
    await expect(page.getByRole("dialog", { name: "آپ کا آرڈر" })).toBeVisible();
    const id = await placeOrder(page, "ur");
    await approveOrder(id);
    await page.goto(`${GUEST}/ur/menu`);
    await page.getByRole("button", { name: "بل ادا کریں" }).click();
    const pay = page.getByRole("dialog", { name: "بل ادا کریں" });
    await pay.getByRole("button", { name: /^نقد/ }).click();
    await expect(pay.getByRole("status")).toContainText(/Rs\s[\d,]+/);
    expect(await pay.innerText()).not.toMatch(EASTERN_DIGITS);

    const kitchen = await (await browser.newContext()).newPage();
    const { staffPage, OWNER } = await import("./helpers");
    await staffPage(kitchen, ANGEETHI);
    await kitchen.goto(`${OWNER}/kitchen`);
    await expect(kitchen.getByText("Naan", { exact: true }).first()).toBeVisible();
    await kitchen.context().close();
  });

  test("at 320 px in Urdu the assistant never covers a dish and nothing scrolls sideways", async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 320, height: 640 } });
    const page = await ctx.newPage();
    await urduMenu(page, "T4");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const chat = page.getByRole("button", { name: /{venue}|Angeethi/ }).last();
    const lastAdd = page.getByRole("button", { name: /شامل|Add/ }).last();
    await lastAdd.scrollIntoViewIfNeeded();
    const [a, b] = [await chat.boundingBox(), await lastAdd.boundingBox()];
    if (a && b) expect(a.y + a.height <= b.y || b.y + b.height <= a.y || a.x + a.width <= b.x || b.x + b.width <= a.x).toBe(true);
    await ctx.close();
  });

  test("a language the venue does not offer falls back to the visit's language", async ({ page }) => {
    await openTable(ANGEETHI, "T5");
    await openTableMenu(page, tables.T5.qr_token, "en");
    await page.goto(`${GUEST}/ar/menu`);
    await expect(page).toHaveURL(/\/en\/menu$/);
    await page.goto(`${GUEST}/it/menu`);
    await expect(page.getByRole("heading", { name: "Angeethi House" })).toHaveCount(0);
  });
});
```

The 320 px test needs the right locators. Before finalising, read `e2e/dish-choices.spec.ts` and the existing 320 px test in `e2e/` (`grep -rln "320" e2e`), and reuse that file's selectors for the assistant button and the dish Add buttons instead of the guesses above. The add-button accessible name comes from the menu page's `aria-label`, which may still be English, `Add {name}`. If it is English in Urdu mode, translate it through the dictionary and add a `ui.addDish` key (`"{name} شامل کریں"`). Use the same exact-name pattern for Naan.

- [ ] **Step 3: Extend the one-venue test**

In `e2e/one-venue.spec.ts`, add a test that runs the existing "walk every guest page" helper with `openTableMenu(page, qr, "ur")` for Angeethi. It asserts the same things: no other venue's name, logo file or font, and no "Mise", in text, title, manifest or image sources. Reuse the file's existing walk function with a language parameter rather than copying it.

- [ ] **Step 4: Run**

Reset the database first if the date has changed.

```bash
npx playwright test e2e/urdu.spec.ts e2e/one-venue.spec.ts
npx playwright test
```

Expected: all PASS. The whole suite also passes, which shows the English defaults are unchanged.

- [ ] **Step 5: Commit**

```bash
git add e2e/helpers.ts e2e/urdu.spec.ts e2e/one-venue.spec.ts apps/guest-web/src
git commit -m "test(e2e): a whole visit in Urdu — right-to-left, Latin-digit money, English kitchen, fallback"
```

---

### Task 10: Docs, and a whole-branch check

**Files:**
- Modify: `README.md` (the languages section, and any mention of Italian)
- Modify: `docs/architecture.md` (guest languages, the `translations` column, right-to-left)

- [ ] **Step 1: Update the docs**

The README says, in the project's own words:
- The guest app is English plus each venue's local language: Urdu at the Pakistani venues now, Arabic for Dubai in phase 2.
- Urdu pages are right-to-left, set from the server, in Noto Naskh Arabic, with money in Latin digits.
- **The Urdu text is a draft translation**, and its allergen and safety wording awaits review by a native speaker. The allergen status itself is always server code.
- The owner app, kitchen and bills stay in English.

`docs/architecture.md` describes:
- `restaurant.languages` and the 422 for a language the venue doesn't offer.
- The `translations` JSONB on options, groups and choices: guest-facing only, with snapshots keeping `label`.
- The `[lang]` layout redirect rule.

Remove every "Italian" mention:

```bash
grep -rn "Italian\|Italiano" README.md docs/architecture.md
```

Expected: no output.

- [ ] **Step 2: Run the whole-branch checks**

```bash
docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest -q
npm --prefix packages/ui exec vitest run
npm --prefix apps/guest-web exec vitest run
npm --prefix apps/owner-web exec vitest run
npm --prefix apps/guest-web run lint
npm --prefix apps/owner-web run lint
bash scripts/check_branding.sh
grep -rn "\"it\"\|'it'" services/api/src apps/guest-web/src apps/owner-web/src packages/ui/src --include=*.py --include=*.ts --include=*.tsx | grep -v "it(\"\|it('"
```

Expected:
- Everything passes, apart from the known flaky Python tests, which pass alone.
- The branding check is clean.
- The last grep finds no `it` language code.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/architecture.md
git commit -m "docs: guest languages — Urdu (draft translation), right-to-left, Italian removed"
```

---

## Spec coverage check

| Spec item | Task |
|---|---|
| Languages per venue (Angeethi and Kehwa: en and ur) | 1, 3 |
| Italian removed: dictionary, route, API, owner import | 5, 6, 1, 8 |
| Venue response carries languages; picker in own names, hidden with one language | 1, 6, 7 |
| API refuses an unoffered language with 422 (create and change) | 1 |
| Routes `/en|ur|ar`; any other segment is not-found; unoffered language falls back | 6 |
| `lang` and `dir` from the server; sheets follow | 6 |
| Logical utilities; arrows mirror, icons don't | 7 |
| Money Latin-digit and isolated | 4 |
| Bottom stack at 320 px both ways | 9 |
| Noto Naskh 400/700, only on ur/ar, line height 1.7; venue fonts for Latin | 6 |
| Full `ur.ts`, every key, polite register | 5 |
| Urdu dish, size and choice names | 2, 3 |
| Safety text marked draft (dictionary and README) | 5, 10 |
| Ingredient tags stay English; assistant answers English with labels translated | 3, 1, 5 |
| Owner, kitchen and bills stay English | 2, 9 |
| Tests listed in the spec | 1, 4, 5, 7, 9 |
