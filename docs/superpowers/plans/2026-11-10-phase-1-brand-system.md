# Phase 1 · Brand system, Angeethi House and Kehwa & Crumb · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every guest screen the brand of the venue whose QR code the guest scanned (colours, type, logo, motif, welcome animation, loader), with Angeethi House and Kehwa & Crumb packages, and guarantee a guest never sees another venue or the Mise name.

**Architecture:** The API tells the guest app which venue a session or QR token belongs to. The guest app resolves the venue on the server (`[lang]/layout.tsx`, scan page), sets page metadata from it, and wraps the page in a client `BrandShell`. `BrandShell` sets `--brand-*` CSS variables, which `globals.css` maps onto the existing theme variables, so the shared screens keep their classes and need no venue conditions. Static brand data (colours, names, font stacks) lives in `packages/ui/src/venue-brands.ts` so the owner app can brand the QR card and sample bill too; each venue's code (fonts, motif, welcome, loader) is a lazily loaded package in `apps/guest-web/src/brands/<slug>/`.

**Tech Stack:** FastAPI + pytest; Next.js 15 App Router, React 19, Tailwind v4, `next/font/google`, `gsap` + `@gsap/react`; Vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-11-09-four-identities-design.md`, sections "Phase 1 · The brand system" and "One venue per guest".

**Branch:** `feat/four-identities`. Never commit to `main`; no amend, no force-push, no branch deletion. Do not stage `.gitignore`, `.claude/` or `.impeccable/`. Never read `.env`. Every stack run uses `LLM_PROVIDER=mock DEMO_MODE=true`. Never weaken or skip a test.

**Stack notes (learned in phase 0):**
- Start: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait`. After `docker compose --profile edge --profile test down -v` (`make reset`) the database is empty: run `docker compose exec -T api alembic upgrade head` and `docker compose exec -T api python scripts/seed.py` before e2e.
- The `api-test` image copies the source at build time: run `docker compose build api-test` before `docker compose run --rm api-test …`.
- After changing guest-web or owner-web code, rebuild that service before e2e: `LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web`.
- Pure Python tests run locally with `POSTGRES_DB=mise_test uv run --project services/api pytest …` (the variable only satisfies a conftest guard).
- `make` may be missing in the shell; run the commands a target contains.
- Known flake: `tests/test_service_calls.py::test_call_resolve_and_cooldown` can fail under full-suite load; rerun that file alone to confirm.

## Decisions taken in this plan (small deviations from the spec, on purpose)

1. **The venue comes from the guest session, not the menu response.** `GuestSessionResponse` (create and status) gains `venue: {slug, name}`. Every guest page sits under `[lang]/layout.tsx`, which reads the session once on the server, so the brand, title and icon are right on first paint for every page, not only the menu. The menu response is unchanged.
2. **Static brand data is shared through `packages/ui`.** Colours, names and font stacks for all venues live in `packages/ui/src/venue-brands.ts` (no `tokens.ts` per brand folder), because the owner app's QR card and sample bill need the same data. The guest brand folders hold fonts, motif, welcome and loader.
3. **Colours are hex, not OKLCH**, so a plain WCAG contrast test checks every pair. Values come from the user's palettes (Wine Red #7F011F / Light Sand #F5EBDD for Angeethi, Forest #064734 / Leaf #E0FFC2 for Kehwa) and the round-1 logos.
4. **Logo files live in `public/venues/<slug>/`** of each app (`mark.svg`, `lockup.svg`), because icons and the manifest need public URLs. A test keeps both apps' copies identical to `docs/brand/round-1/`.
5. **The QR-to-venue lookup has no IP rate limit.** The guest app's server calls it, so every guest would share one address; the token is unguessable and the answer is only a public venue name.

---

## File map

**API**
| File | Change |
|---|---|
| `services/api/src/schemas/guest.py` | `GuestVenue`; `venue` on `GuestSessionResponse` |
| `services/api/src/routers/guest.py` | Fill `venue` in create/status; new `GET /api/guest/venues/{qr_token}` |
| `services/api/tests/test_guest_venue.py` | **New.** Venue lookup, session venue, cross-venue isolation |
| `packages/api-client/openapi.json` + generated types | Regenerated |

**Shared**
| File | Change |
|---|---|
| `packages/ui/src/venue-brands.ts` (+ `.test.ts`) | **New.** `VenueBrand`, `BrandTokens`, `VENUE_BRANDS`, `NEUTRAL_TOKENS`, `venueBrand()`, `contrast()` |
| `packages/ui/src/index.ts` | Export the above |
| `packages/ui/src/theme.css` | `.figure` house class (fixed face for money) |

**Guest app**
| File | Change |
|---|---|
| `apps/guest-web/public/venues/<slug>/{mark,lockup}.svg` | **New.** Copied from `docs/brand/round-1/` |
| `apps/guest-web/src/app/layout.tsx` | Neutral metadata (no Mise, no manifest, no icon) |
| `apps/guest-web/src/app/icon.svg` | **Delete** (it put the Mise icon on every page) |
| `apps/guest-web/src/app/(landing)/{layout,page}.tsx` | Landing moves into a route group with its own Mise metadata |
| `apps/guest-web/src/app/not-found.tsx` | **New.** Neutral |
| `apps/guest-web/src/app/[lang]/layout.tsx` | **New.** Resolves the venue; metadata; `BrandShell` or `ScanAgain` |
| `apps/guest-web/src/app/q/[token]/page.tsx` + `loading.tsx` | Server page: resolve token, metadata, `BrandShell` + `ScanForm` or `ScanAgain` |
| `apps/guest-web/src/app/venues/[slug]/manifest.webmanifest/route.ts` | **New.** Per-venue manifest |
| `apps/guest-web/src/app/[lang]/menu/page.tsx` | 401 → `ScanAgain`; masthead; bar motif; loader; `.figure` |
| `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx` | Loader; `.figure` |
| `apps/guest-web/src/app/globals.css` | `[data-brand]` maps `--brand-*` onto the theme variables |
| `apps/guest-web/src/brands/{types,index,style}.ts` | **New.** `BrandPackage`, lazy `loadBrand()`, `brandStyle()` |
| `apps/guest-web/src/brands/angeethi-house/*`, `…/kehwa-and-crumb/*` | **New.** `fonts.ts`, `Motif.tsx`, `Welcome.tsx`, `Loader.tsx`, `index.ts` |
| `apps/guest-web/src/components/BrandShell.tsx` | **New.** Brand root, `useVenue()`, welcome gate |
| `apps/guest-web/src/components/{ScanAgain,ScanForm,Masthead,NeutralLoader}.tsx` | **New** |
| `apps/guest-web/src/components/chat-panel.tsx` | Title from `useVenue()` |
| `apps/guest-web/src/lib/{venue-server,venue-meta,welcome}.ts` | **New** |
| `apps/guest-web/src/i18n/{en,it,types,index}.ts` | `{venue}` titles, `scanAgain`, `withVenue()` |

**Owner app**
| File | Change |
|---|---|
| `apps/owner-web/public/venues/<slug>/{mark,lockup}.svg` | **New.** Same copies |
| `apps/owner-web/src/lib/venue-fonts.ts` | **New.** The venues' display faces for printouts |
| `apps/owner-web/src/app/(dashboard)/tables/page.tsx` | QR cards in the venue's brand |
| `apps/owner-web/src/app/bills/[id]/print/page.tsx` | Sample bill header in the venue's brand |

**E2E**
| File | Change |
|---|---|
| `e2e/helpers.ts` | `skipWelcome()`; `openTableMenu` calls it |
| `e2e/*.spec.ts` | "Ask Mise Assistant" → the venue's name |
| `e2e/one-venue.spec.ts` | **New.** No other venue and no Mise on any guest page; welcome rules |

---

### Task 1: The API names the venue of a session and of a QR token

**Files:**
- Modify: `services/api/src/schemas/guest.py` (~line 44)
- Modify: `services/api/src/routers/guest.py` (create ~82-131, status ~134-218, new route after them)
- Create: `services/api/tests/test_guest_venue.py`
- Regenerate: `packages/api-client`

- [ ] **Step 1: Write the failing tests**

`services/api/tests/test_guest_venue.py`. Read `tests/test_table_ordering.py` first (its `tv` fixture and `post_order`); this file builds two venues the same way:

```python
"""The guest API names only the scanned venue and never serves another venue's data."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import approve_order, open_table

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


def _item(rid: uuid.UUID, name: str) -> MenuItem:
    item = MenuItem(
        restaurant_id=rid, category="mains", price=Decimal("100.00"), unit_cost=Decimal("1.00"),
        ingredients=[], allergens=[], allergen_verified=True, dietary_verified=True,
    )
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


async def _venue(db: AsyncSession, name: str, dish: str):
    r = Restaurant(
        name=name, slug=f"v-{uuid.uuid4().hex[:8]}", city="Lahore", currency="PKR",
        timezone="Asia/Karachi", languages=["en"], default_language="en", tax_jurisdiction="PB",
    )
    db.add(r)
    await db.flush()
    t = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    item = _item(r.id, dish)
    db.add_all([t, item])
    await db.flush()
    s = GuestSession(
        restaurant_id=r.id, table_id=t.id, language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    return r, t, item, s


def _as_guest(client: AsyncClient, s: GuestSession) -> None:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(s.id)))


@pytest.mark.asyncio
async def test_qr_token_names_its_venue_and_nothing_else(client, db_session):
    r, t, _, _ = await _venue(db_session, "Venue A", "Dish A")
    res = await client.get(f"/api/guest/venues/{t.qr_token}")
    assert res.status_code == 200
    assert res.json() == {"slug": r.slug, "name": "Venue A"}


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["not-a-token", "x" * 300, "%00", "' OR 1=1 --"])
async def test_unknown_qr_token_is_404(client, token):
    res = await client.get(f"/api/guest/venues/{token}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_session_create_and_status_carry_the_venue(client, db_session):
    r, t, _, _ = await _venue(db_session, "Venue A", "Dish A")
    created = await client.post(
        "/api/guest/sessions",
        json={"qr_token": t.qr_token, "language": "en", "dietary_preferences": [], "allergens_to_avoid": []},
    )
    assert created.status_code == 201
    assert created.json()["venue"] == {"slug": r.slug, "name": "Venue A"}
    status = await client.get("/api/guest/session")  # the create call set the cookie
    assert status.status_code == 200
    assert status.json()["venue"] == {"slug": r.slug, "name": "Venue A"}


@pytest.mark.asyncio
async def test_a_guest_never_gets_another_venues_menu_order_bill_or_call(client, db_session):
    _, _, _, sa = await _venue(db_session, "Venue A", "Dish A")
    rb, tb, dish_b, sb = await _venue(db_session, "Venue B", "Dish B")

    # Venue B: a real order and a service call from B's own guest.
    await open_table(db_session, tb.id)
    _as_guest(client, sb)
    order = await client.post(
        "/api/orders",
        json={"idempotency_key": uuid.uuid4().hex, "items": [{"menu_item_id": str(dish_b.id), "quantity": 1}]},
    )
    assert order.status_code in (200, 201, 202), order.text
    b_order = order.json()["id"]
    await approve_order(b_order)
    call = await client.post("/api/guest/service-calls", json={"kind": "water"})
    assert call.status_code in (200, 201), call.text

    # Venue A's guest asks for all of it.
    _as_guest(client, sa)
    menu = (await client.get("/api/guest/menu")).text
    assert "Dish B" not in menu and "Venue B" not in menu and rb.slug not in menu
    assert (await client.get(f"/api/orders/{b_order}")).status_code == 404
    assert (await client.get(f"/api/guest/bill?order_id={b_order}")).status_code == 404
    current = await client.get("/api/guest/service-calls/current")
    assert current.status_code in (200, 204, 404)
    assert "water" not in current.text
```

The service-call request body and the order response's `id` field are assumptions: read the request schemas in `services/api/src/schemas/` and the `POST /api/orders` response model, and adjust the request and field name to what the API really takes. Keep every assertion's intent.

- [ ] **Step 2: Run them to see them fail**

Run: `docker compose build api-test && docker compose run --rm api-test pytest tests/test_guest_venue.py -q`
Expected: the venue lookup is not found for valid tokens; `venue` is missing from the session responses. The isolation test may already pass (the API is already scoped); it stays as a guard.

- [ ] **Step 3: The schema**

In `services/api/src/schemas/guest.py`, above `GuestSessionResponse`:

```python
class GuestVenue(BaseModel):
    """The scanned venue as a guest may see it: its public slug and name, nothing else."""

    slug: str
    name: str
```

and add to `GuestSessionResponse`, after `expires_at`:

```python
    venue: GuestVenue
```

- [ ] **Step 4: The routes**

In `services/api/src/routers/guest.py` (relationships are `lazy="raise"`, so query explicitly):

```python
def _session_fields(s: GuestSession) -> dict:
    return {
        "id": s.id, "restaurant_id": s.restaurant_id, "table_id": s.table_id,
        "language": s.language, "dietary_preferences": s.dietary_preferences,
        "allergens_to_avoid": s.allergens_to_avoid, "expires_at": s.expires_at,
    }


async def venue_of(db: AsyncSession, restaurant_id: uuid.UUID) -> GuestVenue:
    row = (
        await db.execute(select(Restaurant.slug, Restaurant.name).where(Restaurant.id == restaurant_id))
    ).one()
    return GuestVenue(slug=row.slug, name=row.name)
```

In `create_guest_session`, replace `return GuestSessionResponse.model_validate(guest_session)` with:

```python
    return GuestSessionResponse.model_validate(
        {**_session_fields(guest_session), "venue": await venue_of(db, guest_session.restaurant_id)}
    )
```

Read how `get_guest_session` builds `GuestSessionStatusResponse` and build it from `_session_fields(session)` plus its own extra fields plus `"venue": await venue_of(db, session.restaurant_id)`. Import `Restaurant`, `GuestVenue` and `GuestSession` where missing.

Then the new route, after the session routes:

```python
@router.get(
    "/venues/{qr_token}",
    response_model=GuestVenue,
    responses={404: {"description": "Unknown QR token"}},
)
async def venue_for_qr(qr_token: str, db: AsyncSession = Depends(get_db)) -> GuestVenue:
    """The venue a table QR code belongs to, so the scan page can show its brand before a session.

    No IP limit: the guest app's server calls it for every guest from one address. The token is
    unguessable and the answer is only a public venue name.
    """
    row = (
        await db.execute(
            select(Restaurant.slug, Restaurant.name)
            .join(DiningTable, DiningTable.restaurant_id == Restaurant.id)
            .where(DiningTable.qr_token == qr_token)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown QR token")
    return GuestVenue(slug=row.slug, name=row.name)
```

- [ ] **Step 5: Run the new tests and every test that reads session responses**

Run: `docker compose build api-test && docker compose run --rm api-test pytest tests/test_guest_venue.py tests/test_order_path.py tests/test_table_ordering.py tests/test_sitting.py -q`
Expected: all pass. If an older test compares a whole session response, add the `venue` key to its expectation (the response gained a field; this is not a weakening).

- [ ] **Step 6: Lint, full suite, regenerate the client**

Run: `uv run --project services/api ruff check services/ && uv run --project services/api ruff format --check services/`
Run: `docker compose run --rm api-test` — all pass.
Run (stack up): `docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json && pnpm --filter api-client generate`

- [ ] **Step 7: Commit**

```bash
git add services/api/src/schemas/guest.py services/api/src/routers/guest.py services/api/tests/test_guest_venue.py packages/api-client
git commit -m "feat(api): guest sessions and QR tokens name their venue; isolation test"
```

---

### Task 2: Shared venue brand data, contrast-checked, and the logo files

**Files:**
- Create: `packages/ui/src/venue-brands.ts`, `packages/ui/src/venue-brands.test.ts`
- Modify: `packages/ui/src/index.ts`
- Create: `apps/{guest-web,owner-web}/public/venues/{angeethi-house,kehwa-and-crumb}/{mark,lockup}.svg`
- Create: `apps/guest-web/src/brands/assets.test.ts`

- [ ] **Step 1: Write the failing tests**

`packages/ui/src/venue-brands.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { NEUTRAL_TOKENS, VENUE_BRANDS, contrast, venueBrand } from "./venue-brands";

const INK = "#2b2118"; // theme --color-ink, never changed by a brand
const INK_MUTED = "#6b5a48"; // theme --color-ink-muted

describe("contrast", () => {
  it("matches the WCAG formula at the extremes", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 1);
    expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    expect(contrast("#fff", "#000")).toBeCloseTo(21, 1);
  });
  it("rejects a value that is not a hex colour", () => {
    expect(() => contrast("rgb(0 0 0)", "#fff")).toThrow();
  });
});

const all = [
  ...Object.values(VENUE_BRANDS).map((b) => [b.slug, b.tokens] as const),
  ["neutral", NEUTRAL_TOKENS] as const,
];

describe.each(all)("%s tokens", (_slug, t) => {
  it("text on the surfaces is readable (AA 4.5)", () => {
    for (const bg of [t.surface, t.surface2, t.card]) {
      expect(contrast(INK, bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(INK_MUTED, bg)).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("buttons and the masthead are readable (AA 4.5)", () => {
    expect(contrast(t.onAccent, t.accent)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.onAccent, t.accentStrong)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.onDeep, t.deep)).toBeGreaterThanOrEqual(4.5);
  });
  it("the accent stands out from the surface (3:1)", () => {
    expect(contrast(t.accent, t.surface)).toBeGreaterThanOrEqual(3);
  });
});

describe("venueBrand", () => {
  it("finds a known venue and refuses anything else", () => {
    expect(venueBrand("angeethi-house")?.name).toBe("Angeethi House");
    expect(venueBrand("kehwa-and-crumb")?.name).toBe("Kehwa & Crumb");
    for (const bad of [undefined, null, "", "ANGEETHI-HOUSE", "__proto__", "constructor", "../x"]) {
      expect(venueBrand(bad)).toBeNull();
    }
  });
  it("keys every brand by its own slug", () => {
    for (const [key, b] of Object.entries(VENUE_BRANDS)) expect(b.slug).toBe(key);
  });
  it("never uses Fraunces or the Mise terracotta", () => {
    const text = JSON.stringify(VENUE_BRANDS).toLowerCase();
    expect(text).not.toContain("fraunces");
    expect(text).not.toContain("#b5462b");
  });
});
```

`apps/guest-web/src/brands/assets.test.ts` (Vitest runs with the app folder as cwd):

```ts
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { VENUE_BRANDS } from "ui";

const repo = path.resolve(process.cwd(), "../..");
const SOURCE: Record<string, string> = { "angeethi-house": "angeethi", "kehwa-and-crumb": "kehwa" };

describe.each(Object.keys(VENUE_BRANDS))("%s logo files", (slug) => {
  it.each(["mark", "lockup"])("%s.svg is the round-1 vector in both apps", (kind) => {
    const original = readFileSync(path.join(repo, "docs/brand/round-1", `${SOURCE[slug]}-${kind}.svg`));
    for (const app of ["guest-web", "owner-web"]) {
      const copy = readFileSync(path.join(repo, "apps", app, "public/venues", slug, `${kind}.svg`));
      expect(copy.equals(original), `${app} ${slug}/${kind}.svg`).toBe(true);
      expect(copy.toString()).toMatch(/^<svg[\s\S]*<\/svg>\s*$/);
      expect(copy.toString()).not.toMatch(/<image|data:image/);
    }
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `pnpm --filter ui exec vitest run src/venue-brands.test.ts` → FAIL (module missing).
Run: `pnpm --filter guest-web exec vitest run src/brands/assets.test.ts` → FAIL.

- [ ] **Step 3: The data**

`packages/ui/src/venue-brands.ts`:

```ts
/** Static brand data per venue: colours, names and font stacks. Shared by the guest app (every
 *  guest screen) and the owner app (QR cards and the sample bill). Venue code (fonts, motif,
 *  animations) lives in apps/guest-web/src/brands/<slug>/. */

export interface BrandTokens {
  /** Masthead band, behind the light logo lockup. */
  deep: string;
  /** Logo and text on `deep`. */
  onDeep: string;
  surface: string;
  surface2: string;
  card: string;
  /** Hairlines; any CSS colour (not contrast-checked). */
  line: string;
  accent: string;
  accentStrong: string;
  onAccent: string;
  /** Decoration only (motif, animation), never text. */
  spark: string;
  buttonRadius: string;
  cardRadius: string;
}

export interface VenueBrand {
  slug: string;
  /** Must equal the venue's name in data/seed. */
  name: string;
  tokens: BrandTokens;
  /** CSS font stacks; the first entry is the venue face loaded with next/font. */
  displayFont: string;
  textFont: string;
}

export const NEUTRAL_TOKENS: BrandTokens = {
  deep: "#2f2f2f",
  onDeep: "#ffffff",
  surface: "#f7f7f5",
  surface2: "#ededea",
  card: "#ffffff",
  line: "rgb(0 0 0 / 0.12)",
  accent: "#2f2f2f",
  accentStrong: "#1a1a1a",
  onAccent: "#ffffff",
  spark: "#9a9a9a",
  buttonRadius: "10px",
  cardRadius: "12px",
};

export const VENUE_BRANDS: Record<string, VenueBrand> = {
  "angeethi-house": {
    slug: "angeethi-house",
    name: "Angeethi House",
    tokens: {
      deep: "#7f011f",
      onDeep: "#f5ebdd",
      surface: "#f5ebdd",
      surface2: "#ebdcc8",
      card: "#fbf6ee",
      line: "rgb(127 1 31 / 0.16)",
      accent: "#7f011f",
      accentStrong: "#5e0016",
      onAccent: "#f5ebdd",
      spark: "#ff9a3d",
      buttonRadius: "4px",
      cardRadius: "6px",
    },
    displayFont: "var(--brand-display-face, Impact), Impact, 'Arial Narrow', sans-serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
  "kehwa-and-crumb": {
    slug: "kehwa-and-crumb",
    name: "Kehwa & Crumb",
    tokens: {
      deep: "#064734",
      onDeep: "#e0ffc2",
      surface: "#f3f8ea",
      surface2: "#e4efd3",
      card: "#fafdf5",
      line: "rgb(6 71 52 / 0.15)",
      accent: "#064734",
      accentStrong: "#04331f",
      onAccent: "#e0ffc2",
      spark: "#b8e68c",
      buttonRadius: "9999px",
      cardRadius: "20px",
    },
    displayFont: "var(--brand-display-face, 'Futura'), 'Futura', 'Century Gothic', sans-serif",
    textFont: "var(--brand-text-face, system-ui), system-ui, sans-serif",
  },
};

export function venueBrand(slug: string | null | undefined): VenueBrand | null {
  if (!slug || !Object.prototype.hasOwnProperty.call(VENUE_BRANDS, slug)) return null;
  return VENUE_BRANDS[slug];
}

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a hex colour: ${hex}`);
  const h = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2 contrast ratio between two hex colours (1 to 21). */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
```

Add to `packages/ui/src/index.ts`:

```ts
export { NEUTRAL_TOKENS, VENUE_BRANDS, contrast, venueBrand } from "./venue-brands";
export type { BrandTokens, VenueBrand } from "./venue-brands";
```

If a contrast test fails, move the failing colour darker or lighter within its hue until it passes; never lower a threshold.

- [ ] **Step 4: Copy the logos**

```bash
for app in guest-web owner-web; do
  for pair in "angeethi-house angeethi" "kehwa-and-crumb kehwa"; do
    set -- $pair
    mkdir -p "apps/$app/public/venues/$1"
    cp "docs/brand/round-1/$2-mark.svg" "apps/$app/public/venues/$1/mark.svg"
    cp "docs/brand/round-1/$2-lockup.svg" "apps/$app/public/venues/$1/lockup.svg"
  done
done
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `pnpm --filter ui test && pnpm --filter guest-web exec vitest run src/brands/assets.test.ts` → PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/ui/src/venue-brands.ts packages/ui/src/venue-brands.test.ts packages/ui/src/index.ts apps/guest-web/public/venues apps/owner-web/public/venues apps/guest-web/src/brands/assets.test.ts
git commit -m "feat(brand): shared venue brand data with contrast tests; venue logo files"
```

---

### Task 3: Neutral shell — no Mise and no venue list on any guest page

**Files:**
- Modify: `apps/guest-web/src/app/layout.tsx`
- Delete: `apps/guest-web/src/app/icon.svg`
- Move: `apps/guest-web/src/app/page.tsx` → `apps/guest-web/src/app/(landing)/page.tsx`; create `apps/guest-web/src/app/(landing)/layout.tsx`
- Create: `apps/guest-web/src/app/not-found.tsx`, `apps/guest-web/src/components/ScanAgain.tsx` (+ `.test.tsx`), `apps/guest-web/src/brands/style.ts`
- Modify: `apps/guest-web/src/i18n/{types,en,it,index}.ts`, `apps/guest-web/src/i18n/i18n.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `apps/guest-web/src/i18n/i18n.test.ts` (add `withVenue` to its imports):

```ts
describe("venue-named strings", () => {
  it("puts the venue name into the titles in both languages", () => {
    expect(withVenue(en.ui.welcomeTitle, "Angeethi House")).toBe("Welcome to Angeethi House");
    expect(withVenue(en.ui.chatTitle, "Kehwa & Crumb")).toBe("Ask Kehwa & Crumb");
    expect(withVenue(it.ui!.welcomeTitle!, "Angeethi House")).toBe("Benvenuti da Angeethi House");
  });
  it("treats special characters in a name as plain text", () => {
    expect(withVenue("Ask {venue}", "A $& B $1")).toBe("Ask A $& B $1");
  });
  it("never names Mise in any guest string", () => {
    expect(JSON.stringify(en)).not.toMatch(/\bMise\b/);
    expect(JSON.stringify(it)).not.toMatch(/\bMise\b/);
  });
  it("has the neutral scan-again text", () => {
    expect(en.ui.scanAgain).toBe("Scan the QR code on your table again.");
    expect(it.ui!.scanAgain).toBeTruthy();
  });
});
```

`apps/guest-web/src/components/ScanAgain.test.tsx` (follow the setup of `allergen-chip.test.tsx` so `render` works):

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScanAgain } from "./ScanAgain";

describe("ScanAgain", () => {
  it("asks to scan again and names no venue, no Mise and no link", () => {
    const { container } = render(<ScanAgain lang="en" />);
    expect(screen.getByText("Scan the QR code on your table again.")).toBeTruthy();
    expect(container.textContent).not.toMatch(/Mise|Angeethi|Kehwa/);
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
  it("falls back to English for an unknown language", () => {
    render(<ScanAgain lang="xx" />);
    expect(screen.getByText("Scan the QR code on your table again.")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `pnpm --filter guest-web exec vitest run src/i18n src/components/ScanAgain.test.tsx` → FAIL.

- [ ] **Step 3: Strings**

`types.ts`: add `scanAgain: string;` to `ui`. `en.ts`: `welcomeTitle: "Welcome to {venue}"`, `chatTitle: "Ask {venue}"`, `scanAgain: "Scan the QR code on your table again."`. `it.ts`: `welcomeTitle: "Benvenuti da {venue}"`, `chatTitle: "Chiedi a {venue}"`, `scanAgain: "Scansiona di nuovo il codice QR sul tuo tavolo."`. Search both files for any other "Mise" and rewrite it without a name.

`index.ts`:

```ts
/** Puts the venue's name into a "{venue}" string; the name is inserted as plain text. */
export function withVenue(text: string, venue: string): string {
  return text.split("{venue}").join(venue);
}
```

- [ ] **Step 4: `brandStyle` and `ScanAgain`**

`apps/guest-web/src/brands/style.ts`:

```ts
import type { CSSProperties } from "react";
import type { BrandTokens, VenueBrand } from "ui";

const SYSTEM = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";

/** The brand as CSS variables; globals.css maps them onto the theme. Ink and allergen colours stay fixed. */
export function brandStyle(t: BrandTokens, fonts?: Pick<VenueBrand, "displayFont" | "textFont">): CSSProperties {
  return {
    "--brand-deep": t.deep,
    "--brand-on-deep": t.onDeep,
    "--brand-surface": t.surface,
    "--brand-surface-2": t.surface2,
    "--brand-card": t.card,
    "--brand-line": t.line,
    "--brand-accent": t.accent,
    "--brand-accent-strong": t.accentStrong,
    "--brand-on-accent": t.onAccent,
    "--brand-spark": t.spark,
    "--brand-button-radius": t.buttonRadius,
    "--brand-card-radius": t.cardRadius,
    "--brand-display": fonts?.displayFont ?? SYSTEM,
    "--brand-text": fonts?.textFont ?? SYSTEM,
  } as CSSProperties;
}
```

`apps/guest-web/src/components/ScanAgain.tsx`:

```tsx
import { NEUTRAL_TOKENS } from "ui";
import { brandStyle } from "../brands/style";
import { getDictionary } from "../i18n";

/** Shown for a bad QR code, an expired visit or a missing page: no venue, no Mise, no links. */
export function ScanAgain({ lang }: { lang: string }) {
  const dict = getDictionary(lang);
  return (
    <main
      data-brand="neutral"
      style={brandStyle(NEUTRAL_TOKENS)}
      className="flex min-h-screen items-center justify-center bg-paper px-6 text-center text-ink"
    >
      <p className="max-w-xs text-lg font-semibold">{dict.ui.scanAgain}</p>
    </main>
  );
}
```

- [ ] **Step 5: Root layout neutral, landing keeps Mise, neutral not-found**

`apps/guest-web/src/app/layout.tsx`: keep `viewport` with `themeColor: "#ffffff"`; set `metadata` to `{ title: "Menu" }` only (no description naming Mise, no manifest, no icons, no openGraph/twitter, no appleWebApp). Delete `src/app/icon.svg` with `git rm`.

Inside `apps/guest-web`: `git mv src/app/page.tsx "src/app/(landing)/page.tsx"` and fix its relative imports one level deeper. Create `src/app/(landing)/layout.tsx`:

```tsx
import type { Metadata } from "next";

// The presenter page lists the demo venues and is Mise-branded. No guest flow links here.
export const metadata: Metadata = {
  title: "Mise: Restaurant Revenue Copilot",
  description: "Restaurant revenue copilot and real-time operations platform",
  manifest: "/manifest.json",
  icons: { icon: "/brand/logo-mark.svg", apple: "/brand/logo-mark.svg" },
};

export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
```

`src/app/not-found.tsx`:

```tsx
import { ScanAgain } from "../components/ScanAgain";

export default function NotFound() {
  return <ScanAgain lang="en" />;
}
```

- [ ] **Step 6: Tests, types, lint**

Run: `pnpm --filter guest-web exec tsc --noEmit && pnpm --filter guest-web lint && pnpm --filter guest-web test` → green. Screens that still print `dict.ui.welcomeTitle`/`chatTitle` show "{venue}" until Task 5 wires the name; that is expected between these two tasks.

- [ ] **Step 7: Commit**

```bash
git add -A apps/guest-web/src/app apps/guest-web/src/components/ScanAgain.tsx apps/guest-web/src/components/ScanAgain.test.tsx apps/guest-web/src/brands/style.ts apps/guest-web/src/i18n
git commit -m "feat(guest): neutral shell, scan-again screen and venue-named strings; landing keeps Mise"
```

---

### Task 4: Brand runtime — CSS variables, fixed money face, registry, BrandShell, welcome rule

**Files:**
- Create: `apps/guest-web/src/brands/{types,index}.ts`, `apps/guest-web/src/brands/{style,index}.test.ts`
- Create: `apps/guest-web/src/lib/welcome.ts` (+ `.test.ts`)
- Create: `apps/guest-web/src/components/BrandShell.tsx` (+ `.test.tsx`), `apps/guest-web/src/components/NeutralLoader.tsx`
- Modify: `apps/guest-web/src/app/globals.css`, `packages/ui/src/theme.css`, every guest element that shows `formatPrice(...)`

- [ ] **Step 1: Write the failing tests**

`src/brands/style.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { NEUTRAL_TOKENS, VENUE_BRANDS } from "ui";
import { brandStyle } from "./style";

describe("brandStyle", () => {
  it("sets every --brand-* variable from the tokens and fonts", () => {
    const b = VENUE_BRANDS["angeethi-house"];
    const s = brandStyle(b.tokens, b) as Record<string, string>;
    expect(s["--brand-surface"]).toBe("#f5ebdd");
    expect(s["--brand-accent"]).toBe("#7f011f");
    expect(s["--brand-on-accent"]).toBe("#f5ebdd");
    expect(s["--brand-button-radius"]).toBe("4px");
    expect(s["--brand-display"]).toBe(b.displayFont);
    expect(s["--brand-text"]).toBe(b.textFont);
  });
  it("falls back to system fonts without a venue", () => {
    const s = brandStyle(NEUTRAL_TOKENS) as Record<string, string>;
    expect(s["--brand-display"]).toMatch(/system-ui/);
    expect(s["--brand-text"]).toMatch(/system-ui/);
  });
  it("never sets ink or the allergen colours", () => {
    const keys = Object.keys(brandStyle(NEUTRAL_TOKENS));
    expect(keys.some((k) => /ink|danger|warn|safe/.test(k))).toBe(false);
  });
});
```

`src/brands/index.test.ts`:

```ts
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { VENUE_BRANDS } from "ui";
import { BRAND_SLUGS, loadBrand } from "./index";

describe("brand registry", () => {
  it("returns null for an unknown or hostile slug", async () => {
    for (const bad of ["", "nope", "__proto__", "constructor", "../angeethi-house"]) {
      await expect(loadBrand(bad)).resolves.toBeNull();
    }
  });
  it("has a package for every venue brand and nothing more", () => {
    expect([...BRAND_SLUGS].sort()).toEqual(Object.keys(VENUE_BRANDS).sort());
  });
  it("no brand package imports another brand", () => {
    const dir = path.join(process.cwd(), "src/brands");
    for (const slug of BRAND_SLUGS) {
      for (const file of readdirSync(path.join(dir, slug))) {
        const src = readFileSync(path.join(dir, slug, file), "utf8");
        for (const other of BRAND_SLUGS.filter((s) => s !== slug)) expect(src, `${slug}/${file}`).not.toContain(other);
      }
    }
  });
});
```

The second test can only pass once both packages exist (end of Task 7). In this task run the file with `-t "unknown"`; Task 7 runs it whole.

`src/lib/welcome.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { claimWelcome } from "./welcome";

function memoryStorage() {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
}

describe("claimWelcome", () => {
  it("plays once per visit", () => {
    const s = memoryStorage();
    expect(claimWelcome("visit-1", s)).toBe(true);
    expect(claimWelcome("visit-1", s)).toBe(false);
    expect(claimWelcome("visit-2", s)).toBe(true);
  });
  it("remembers a visit across page loads through storage", () => {
    const s = memoryStorage();
    s.setItem("welcome:visit-old", "1"); // played before a reload
    expect(claimWelcome("visit-old", s)).toBe(false);
  });
  it("plays once per page load when storage is missing", () => {
    expect(claimWelcome("no-storage", null)).toBe(true);
    expect(claimWelcome("no-storage", null)).toBe(false);
  });
  it("plays once per page load when storage throws (private mode, blocked)", () => {
    const broken = {
      getItem: () => { throw new Error("SecurityError"); },
      setItem: () => { throw new Error("QuotaExceededError"); },
    };
    expect(claimWelcome("broken", broken)).toBe(true);
    expect(claimWelcome("broken", broken)).toBe(false);
  });
  it("still plays when only writing fails", () => {
    const readOnly = { getItem: () => null, setItem: () => { throw new Error("QuotaExceededError"); } };
    expect(claimWelcome("read-only", readOnly)).toBe(true);
    expect(claimWelcome("read-only", readOnly)).toBe(false);
  });
  it("never plays without a visit id", () => {
    expect(claimWelcome("", memoryStorage())).toBe(false);
  });
});
```

`src/components/BrandShell.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../brands", () => ({
  loadBrand: (slug: string) => (slug === "broken" ? Promise.reject(new Error("chunk failed")) : Promise.resolve(null)),
}));

import { BrandShell, useVenue } from "./BrandShell";

function Name() {
  return <p>{useVenue().name}</p>;
}

describe("BrandShell", () => {
  it("gives its children the venue name and the brand's variables", () => {
    const { container } = render(
      <BrandShell venue={{ slug: "angeethi-house", name: "Angeethi House" }}>
        <Name />
      </BrandShell>,
    );
    expect(screen.getByText("Angeethi House")).toBeTruthy();
    const root = container.querySelector("[data-brand]") as HTMLElement;
    expect(root.dataset.brand).toBe("angeethi-house");
    expect(root.style.getPropertyValue("--brand-accent")).toBe("#7f011f");
  });
  it("renders neutrally for a venue without a brand, still naming it", () => {
    const { container } = render(
      <BrandShell venue={{ slug: "new-venue", name: "New Venue" }}>
        <Name />
      </BrandShell>,
    );
    expect(screen.getByText("New Venue")).toBeTruthy();
    expect((container.querySelector("[data-brand]") as HTMLElement).dataset.brand).toBe("neutral");
  });
  it("keeps the page and skips the welcome when the brand package fails to load", async () => {
    render(
      <BrandShell venue={{ slug: "broken", name: "Broken Venue" }} welcomeFor="visit-1">
        <Name />
      </BrandShell>,
    );
    await waitFor(() => expect(document.querySelector('[data-welcome="done"]')).toBeTruthy());
    expect(screen.getByText("Broken Venue")).toBeTruthy();
    expect(screen.queryByTestId("welcome")).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `pnpm --filter guest-web exec vitest run src/brands/style.test.ts src/lib/welcome.test.ts src/components/BrandShell.test.tsx` → FAIL (`style.test` may pass already; it exists from Task 3).

- [ ] **Step 3: CSS mapping and the fixed money face**

Append to `apps/guest-web/src/app/globals.css`:

```css
/* A brand root re-points the theme at its --brand-* variables. Ink, ink-muted and the allergen,
   warning and safe colours are never re-pointed: prices, allergen chips, totals, payment details
   and order status keep their fixed styles. */
[data-brand] {
  --color-paper: var(--brand-surface);
  --color-paper-2: var(--brand-surface-2);
  --color-card: var(--brand-card);
  --color-line: var(--brand-line);
  --color-terracotta: var(--brand-accent);
  --color-terracotta-strong: var(--brand-accent-strong);
  --color-cream: var(--brand-on-accent);
  --font-serif: var(--brand-display);
  --font-sans: var(--brand-text);
  font-family: var(--font-sans);
  background-color: var(--color-paper);
}
[data-brand] :is(.btn-primary, .btn-ghost, .btn-dark, .btn-danger) {
  border-radius: var(--brand-button-radius);
}
[data-brand] .mise-card {
  border-radius: var(--brand-card-radius);
}
```

Append to `packages/ui/src/theme.css`, inside `@layer components`:

```css
  /* Money keeps one fixed face under every venue brand. */
  .figure {
    font-family: "Inter Variable", Inter, system-ui, sans-serif;
    font-variant-numeric: tabular-nums;
  }
```

Run `grep -rn "formatPrice(" apps/guest-web/src --include=*.tsx | grep -v test` and add `figure` to the className of the element that directly renders each amount (replace `tabular-nums` with `figure` where present; add `className="figure"` where there is no class). Do not touch allergen chip markup.

- [ ] **Step 4: Registry, types, welcome rule, neutral loader**

`src/brands/types.ts`:

```ts
import type { ComponentType } from "react";

export interface BrandPackage {
  /** next/font variable classes for the display and text faces. */
  fontClass: string;
  /** Static SVG decoration; no animation library. */
  Motif: ComponentType<{ variant: "masthead" | "bar" }>;
  /** About 2 s; calls onDone when finished. */
  Welcome: ComponentType<{ name: string; onDone: () => void }>;
  Loader: ComponentType<{ label: string; size?: "sm" | "md" }>;
}
```

`src/brands/index.ts`:

```ts
import type { BrandPackage } from "./types";

// Each venue's package is its own chunk: fonts, motif and GSAP load only on that venue's pages.
const PACKAGES: Record<string, () => Promise<BrandPackage>> = {};

export const BRAND_SLUGS = Object.keys(PACKAGES);

export async function loadBrand(slug: string): Promise<BrandPackage | null> {
  if (!Object.prototype.hasOwnProperty.call(PACKAGES, slug)) return null;
  return PACKAGES[slug]();
}
```

`src/lib/welcome.ts`:

```ts
type Store = { getItem(key: string): string | null; setItem(key: string, value: string): void };

const playedThisLoad = new Set<string>();

/** True the first time a visit's welcome may play: once per visit through sessionStorage, or once
 *  per page load when storage is missing or throws. */
export function claimWelcome(visitId: string, storage: Store | null): boolean {
  if (!visitId) return false;
  const key = `welcome:${visitId}`;
  if (playedThisLoad.has(key)) return false;
  playedThisLoad.add(key);
  try {
    if (storage?.getItem(key)) return false;
    storage?.setItem(key, "1");
  } catch {
    // Storage blocked: the in-memory record above still limits it to once per page load.
  }
  return true;
}
```

`src/components/NeutralLoader.tsx`:

```tsx
export function NeutralLoader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-4 w-4 border-2" : "h-8 w-8 border-[3px]";
  return (
    <span role="status" className="inline-flex items-center gap-2 text-ink-muted">
      <span aria-hidden className={`${box} animate-spin rounded-full border-line border-t-ink`} />
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
```

- [ ] **Step 5: `BrandShell`**

`src/components/BrandShell.tsx`:

```tsx
"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { NEUTRAL_TOKENS, venueBrand } from "ui";
import { loadBrand } from "../brands";
import { brandStyle } from "../brands/style";
import type { BrandPackage } from "../brands/types";
import { claimWelcome } from "../lib/welcome";
import { NeutralLoader } from "./NeutralLoader";

export interface Venue {
  slug: string;
  name: string;
}

interface VenueContextValue extends Venue {
  branded: boolean;
  Motif: BrandPackage["Motif"];
  Loader: BrandPackage["Loader"];
}

const NoMotif: BrandPackage["Motif"] = () => null;
const VenueContext = createContext<VenueContextValue>({
  slug: "",
  name: "",
  branded: false,
  Motif: NoMotif,
  Loader: NeutralLoader,
});

export const useVenue = () => useContext(VenueContext);

class SkipOnError extends React.Component<{ onError: () => void; children: React.ReactNode }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const WELCOME_CAP_MS = 3000;

/** The venue's brand around a guest page. `welcomeFor` is the visit (guest session) id: when
 *  given, the welcome plays once for that visit. The page renders underneath, so ordering never
 *  waits for it. */
export function BrandShell({
  venue,
  welcomeFor,
  children,
}: {
  venue: Venue;
  welcomeFor?: string;
  children: React.ReactNode;
}) {
  const brand = venueBrand(venue.slug);
  const [pkg, setPkg] = useState<BrandPackage | null>(null);
  const [welcome, setWelcome] = useState<"pending" | "shown" | "done">(welcomeFor ? "pending" : "done");

  useEffect(() => {
    let live = true;
    loadBrand(venue.slug)
      .then((p) => {
        if (!live) return;
        setPkg(p);
        if (!p) setWelcome("done");
      })
      .catch(() => live && setWelcome("done")); // a failed chunk leaves the neutral fallback
    return () => {
      live = false;
    };
  }, [venue.slug]);

  useEffect(() => {
    if (welcome !== "pending" || !pkg || !welcomeFor) return;
    let storage: Storage | null = null;
    try {
      storage = window.sessionStorage;
    } catch {
      storage = null;
    }
    setWelcome(claimWelcome(welcomeFor, storage) ? "shown" : "done");
  }, [welcome, pkg, welcomeFor]);

  useEffect(() => {
    if (welcome !== "shown") return;
    const t = setTimeout(() => setWelcome("done"), WELCOME_CAP_MS);
    return () => clearTimeout(t);
  }, [welcome]);

  const value: VenueContextValue = {
    ...venue,
    branded: Boolean(brand),
    Motif: pkg?.Motif ?? NoMotif,
    Loader: pkg?.Loader ?? NeutralLoader,
  };
  const Welcome = pkg?.Welcome;

  return (
    <VenueContext.Provider value={value}>
      <div
        data-brand={brand ? venue.slug : "neutral"}
        data-welcome={welcome}
        style={brandStyle(brand?.tokens ?? NEUTRAL_TOKENS, brand ?? undefined)}
        className={`min-h-screen ${pkg?.fontClass ?? ""}`}
      >
        {children}
        {welcome === "shown" && Welcome && (
          <div
            data-testid="welcome"
            onClick={() => setWelcome("done")}
            className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--brand-deep)]"
          >
            <SkipOnError onError={() => setWelcome("done")}>
              <Welcome name={venue.name} onDone={() => setWelcome("done")} />
            </SkipOnError>
          </div>
        )}
      </div>
    </VenueContext.Provider>
  );
}
```

- [ ] **Step 6: Run the tests**

Run: `pnpm --filter guest-web exec vitest run src/brands/style.test.ts src/lib/welcome.test.ts src/components/BrandShell.test.tsx && pnpm --filter guest-web exec vitest run src/brands/index.test.ts -t "unknown"` → PASS.
Then: `pnpm --filter guest-web exec tsc --noEmit && pnpm --filter guest-web lint && pnpm --filter ui test`.

- [ ] **Step 7: Commit**

```bash
git add apps/guest-web/src packages/ui/src/theme.css
git commit -m "feat(guest): brand runtime — CSS variables, fixed money face, registry, BrandShell, welcome rule"
```

---

### Task 5: Every guest page resolves its venue on the server

**Files:**
- Create: `apps/guest-web/src/lib/venue-server.ts`, `apps/guest-web/src/lib/venue-meta.ts` (+ `.test.ts`)
- Create: `apps/guest-web/src/app/[lang]/layout.tsx`
- Move: `apps/guest-web/src/app/q/[token]/page.tsx` → `apps/guest-web/src/components/ScanForm.tsx`; new server `q/[token]/page.tsx` and `q/[token]/loading.tsx`
- Create: `apps/guest-web/src/app/venues/[slug]/manifest.webmanifest/route.ts` (+ `route.test.ts`)
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx` (~line 138), `apps/guest-web/src/components/chat-panel.tsx`
- Modify: `e2e/helpers.ts`, every `e2e/*.spec.ts` naming "Ask Mise Assistant"

- [ ] **Step 1: Write the failing tests**

`src/lib/venue-meta.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { venueMetadata, venueViewport } from "./venue-meta";

describe("venueMetadata", () => {
  it("uses the venue's name, icon and manifest", () => {
    const m = venueMetadata({ slug: "angeethi-house", name: "Angeethi House" });
    expect(m.title).toBe("Angeethi House");
    expect(m.manifest).toBe("/venues/angeethi-house/manifest.webmanifest");
    expect(JSON.stringify(m.icons)).toContain("/venues/angeethi-house/mark.svg");
    expect(JSON.stringify(m)).not.toContain("Mise");
  });
  it("names an unbranded venue without inventing an icon or manifest", () => {
    const m = venueMetadata({ slug: "new-venue", name: "New Venue" });
    expect(m.title).toBe("New Venue");
    expect(m.manifest).toBeUndefined();
    expect(m.icons).toBeUndefined();
  });
  it("colours the browser bar with the venue's deep colour", () => {
    expect(venueViewport({ slug: "kehwa-and-crumb", name: "Kehwa & Crumb" }).themeColor).toBe("#064734");
    expect(venueViewport(null).themeColor).toBe("#ffffff");
  });
});
```

`src/app/venues/[slug]/manifest.webmanifest/route.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { GET } from "./route";

const call = (slug: string) => GET(new Request("http://x"), { params: Promise.resolve({ slug }) });

describe("venue manifest", () => {
  it("names and colours the installed app as the venue", async () => {
    const res = await call("angeethi-house");
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("manifest+json");
    const m = await res.json();
    expect(m.name).toBe("Angeethi House");
    expect(m.theme_color).toBe("#7f011f");
    expect(m.icons[0].src).toBe("/venues/angeethi-house/mark.svg");
    expect(JSON.stringify(m)).not.toContain("Mise");
  });
  it("is 404 for an unknown or hostile slug", async () => {
    for (const slug of ["nope", "__proto__", "..%2F", ""]) expect((await call(slug)).status).toBe(404);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `pnpm --filter guest-web exec vitest run src/lib/venue-meta.test.ts src/app/venues` → FAIL.

- [ ] **Step 3: Server helpers, metadata, manifest**

`src/lib/venue-server.ts`:

```ts
import { cache } from "react";
import { cookies } from "next/headers";

const API_URL = process.env.API_URL ?? "http://api:8000";
const GUEST_COOKIE = "mise_guest";

export interface ServerVenue {
  slug: string;
  name: string;
  /** The visit (guest session) id; only on session-resolved pages. */
  visitId?: string;
}

/** The venue of this browser's guest session, or null when there is none or it has expired. */
export const venueFromSession = cache(async (): Promise<ServerVenue | null> => {
  const cookie = (await cookies()).get(GUEST_COOKIE);
  if (!cookie) return null;
  try {
    const res = await fetch(`${API_URL}/api/guest/session`, {
      headers: { cookie: `${GUEST_COOKIE}=${cookie.value}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const s = await res.json();
    return s?.venue?.slug ? { slug: s.venue.slug, name: s.venue.name, visitId: s.id } : null;
  } catch {
    return null;
  }
});

/** The venue a table QR token belongs to, or null for a bad token. */
export const venueFromQr = cache(async (token: string): Promise<ServerVenue | null> => {
  try {
    const res = await fetch(`${API_URL}/api/guest/venues/${encodeURIComponent(token)}`, { cache: "no-store" });
    if (!res.ok) return null;
    const v = await res.json();
    return v?.slug ? { slug: v.slug, name: v.name } : null;
  } catch {
    return null;
  }
});
```

`src/lib/venue-meta.ts`:

```ts
import type { Metadata, Viewport } from "next";
import { venueBrand } from "ui";

export function venueMetadata(v: { slug: string; name: string }): Metadata {
  const icon = `/venues/${v.slug}/mark.svg`;
  return {
    title: v.name,
    ...(venueBrand(v.slug) && {
      manifest: `/venues/${v.slug}/manifest.webmanifest`,
      icons: { icon, apple: icon },
    }),
    appleWebApp: { capable: true, title: v.name },
  };
}

export function venueViewport(v: { slug: string; name: string } | null): Viewport {
  return { themeColor: venueBrand(v?.slug)?.tokens.deep ?? "#ffffff" };
}
```

`src/app/venues/[slug]/manifest.webmanifest/route.ts`:

```ts
import { venueBrand } from "ui";

export async function GET(_req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const brand = venueBrand(slug);
  if (!brand) return new Response("Not found", { status: 404 });
  return Response.json(
    {
      name: brand.name,
      short_name: brand.name,
      start_url: "/en/menu",
      display: "standalone",
      background_color: brand.tokens.surface,
      theme_color: brand.tokens.deep,
      icons: [{ src: `/venues/${slug}/mark.svg`, sizes: "any", type: "image/svg+xml" }],
    },
    { headers: { "content-type": "application/manifest+json" } },
  );
}
```

- [ ] **Step 4: The `[lang]` layout**

`src/app/[lang]/layout.tsx`:

```tsx
import type { Metadata, Viewport } from "next";
import { BrandShell } from "../../components/BrandShell";
import { ScanAgain } from "../../components/ScanAgain";
import { venueFromSession } from "../../lib/venue-server";
import { venueMetadata, venueViewport } from "../../lib/venue-meta";

export async function generateMetadata(): Promise<Metadata> {
  const v = await venueFromSession();
  return v ? venueMetadata(v) : { title: "Menu" };
}

export async function generateViewport(): Promise<Viewport> {
  return venueViewport(await venueFromSession());
}

export default async function GuestLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  const v = await venueFromSession();
  if (!v) return <ScanAgain lang={lang} />;
  return (
    <BrandShell venue={{ slug: v.slug, name: v.name }} welcomeFor={v.visitId}>
      {children}
    </BrandShell>
  );
}
```

- [ ] **Step 5: Expired visit in the menu, venue name in the assistant**

In `src/app/[lang]/menu/page.tsx`: add `const [expired, setExpired] = useState(false);`; in the `res.status === 401` branch replace `router.push("/")` with `setExpired(true); return;`; before the `if (loading)` block add `if (expired) return <ScanAgain lang={lang} />;`. Remove the `router` import if now unused. Run `grep -rn 'push("/")\|href="/"' apps/guest-web/src` and remove any other guest-page link or redirect to `/` the same way.

In `src/components/chat-panel.tsx`: `const { name } = useVenue();` and `const title = withVenue(dict.ui.chatTitle, name);`; use `title` in the three places that used `dict.ui.chatTitle`.

- [ ] **Step 6: Scan page on the server**

Inside `apps/guest-web`: `git mv "src/app/q/[token]/page.tsx" src/components/ScanForm.tsx`. In `ScanForm.tsx`: make it `export function ScanForm({ token }: { token: string })` (drop `params`/`use`); add `const { slug, name, branded } = useVenue();`; replace `<Image src="/brand/logo-mark.svg" alt="Mise" …/>` with

```tsx
          {branded && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`/venues/${slug}/mark.svg`} alt="" width={64} height={64} className="mx-auto rounded-2xl" />
          )}
```

and the title with `{withVenue(dict.ui.welcomeTitle, name)}`. Fix imports (`../i18n`, `./BrandShell`; drop `next/image` if unused).

New `src/app/q/[token]/page.tsx`:

```tsx
import type { Metadata, Viewport } from "next";
import { BrandShell } from "../../../components/BrandShell";
import { ScanAgain } from "../../../components/ScanAgain";
import { ScanForm } from "../../../components/ScanForm";
import { venueFromQr } from "../../../lib/venue-server";
import { venueMetadata, venueViewport } from "../../../lib/venue-meta";

type Props = { params: Promise<{ token: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const v = await venueFromQr((await params).token);
  return v ? venueMetadata(v) : { title: "Menu" };
}

export async function generateViewport({ params }: Props): Promise<Viewport> {
  return venueViewport(await venueFromQr((await params).token));
}

export default async function ScanPage({ params }: Props) {
  const { token } = await params;
  const v = await venueFromQr(token);
  if (!v) return <ScanAgain lang="en" />;
  return (
    <BrandShell venue={v}>
      <ScanForm token={token} />
    </BrandShell>
  );
}
```

`src/app/q/[token]/loading.tsx`:

```tsx
import { NeutralLoader } from "../../../components/NeutralLoader";

export default function Loading() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-white">
      <NeutralLoader label="Loading" />
    </main>
  );
}
```

- [ ] **Step 7: E2E helper and the assistant's new name**

In `e2e/helpers.ts`:

```ts
/** Wait until the venue's welcome has decided, then tap it away so tests can use the menu. */
export async function skipWelcome(page: Page) {
  const root = page.locator("[data-welcome]").first();
  await expect(root).not.toHaveAttribute("data-welcome", "pending", { timeout: 10_000 });
  const welcome = page.getByTestId("welcome");
  if (await welcome.isVisible()) await welcome.click();
  await expect(welcome).toBeHidden();
}
```

Call `await skipWelcome(page);` at the end of `openTableMenu`. Then `grep -rn "Mise" e2e/`: replace "Ask Mise Assistant" with the chat name of the venue that test opens (`Ask Angeethi House` / `Ask Kehwa & Crumb`). Any other "Mise" assertion on a guest page is now wrong by design; update it to the venue's name and say so in the commit message.

- [ ] **Step 8: Unit tests, types, lint, browser suite**

Run: `pnpm --filter guest-web exec tsc --noEmit && pnpm --filter guest-web lint && pnpm --filter guest-web test` → green.
Rebuild (`LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait guest-web api`), then `pnpm exec playwright test` → all pass.

- [ ] **Step 9: Commit**

```bash
git add -A apps/guest-web/src e2e
git commit -m "feat(guest): resolve the venue on the server for every guest page; scan-again on expiry; venue manifest"
```

---

### Task 6: GSAP and the Angeethi House package

**Files:**
- Modify: `apps/guest-web/package.json`, `pnpm-lock.yaml`
- Create: `apps/guest-web/src/brands/angeethi-house/{fonts.ts,Motif.tsx,Welcome.tsx,Loader.tsx,index.ts,package.test.tsx}`
- Modify: `apps/guest-web/src/brands/index.ts`

- [ ] **Step 1: Install**

Run: `pnpm --filter guest-web add gsap @gsap/react`

- [ ] **Step 2: Write the failing test**

`src/brands/angeethi-house/package.test.tsx`:

```tsx
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

describe("Angeethi House package", () => {
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
  it("welcome names the venue and finishes under reduced motion", async () => {
    vi.useFakeTimers();
    reducedMotion(true);
    const onDone = vi.fn();
    const { container } = render(<brand.Welcome name="Angeethi House" onDone={onDone} />);
    expect(container.textContent).toContain("Angeethi House");
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    expect(onDone).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
```

Run: `pnpm --filter guest-web exec vitest run src/brands/angeethi-house` → FAIL.

- [ ] **Step 3: Fonts**

`src/brands/angeethi-house/fonts.ts`:

```ts
import { Anton, Work_Sans } from "next/font/google";

// Heavy condensed display (coal-grill signboard) and a plain working text face. Free (OFL).
export const display = Anton({ subsets: ["latin"], weight: "400", variable: "--brand-display-face", display: "swap" });
export const text = Work_Sans({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
```

If the Docker build cannot download Google Fonts, stop and report it; do not add font packages without approval.

- [ ] **Step 4: Motif (static SVG, no GSAP)**

`src/brands/angeethi-house/Motif.tsx`:

```tsx
/** A bed of coals: ember dots under the masthead, a thin glowing strip on the order bar. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-1 w-full">
        <defs>
          <linearGradient id="ah-ember" x1="0" x2="1">
            <stop offset="0" stopColor="var(--brand-deep)" />
            <stop offset="0.5" stopColor="var(--brand-spark)" />
            <stop offset="1" stopColor="var(--brand-deep)" />
          </linearGradient>
        </defs>
        <rect width="100" height="4" fill="url(#ah-ember)" />
      </svg>
    );
  }
  const coals = [8, 19, 31, 44, 56, 69, 81, 92];
  return (
    <svg aria-hidden="true" viewBox="0 0 100 10" className="block h-3 w-full">
      {coals.map((x, i) => (
        <circle key={x} cx={x} cy={i % 2 ? 6 : 4} r={i % 3 ? 1.6 : 2.2} fill="var(--brand-spark)" opacity={i % 3 ? 0.55 : 0.9} />
      ))}
    </svg>
  );
}
```

- [ ] **Step 5: Welcome and Loader (GSAP)**

`src/brands/angeethi-house/Welcome.tsx`:

```tsx
"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** Coals glow under the mark, then the name rises. About 2 s; the still logo under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".ah-coal", { opacity: 0, scale: 0.3, transformOrigin: "50% 50%", stagger: 0.08, duration: 0.35 })
          .to(".ah-coal", { fill: "#ff9a3d", duration: 0.4 }, "<0.2")
          .from(".ah-mark", { opacity: 0, y: 12, duration: 0.45 }, "-=0.2")
          .from(".ah-name", { opacity: 0, y: 24, duration: 0.5 }, "-=0.1")
          .to({}, { duration: 0.4 });
      });
      mm.add("(prefers-reduced-motion: reduce)", () => {
        gsap.delayedCall(1.2, onDone);
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <div ref={root} className="flex flex-col items-center gap-4 text-[var(--brand-on-deep)]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="ah-mark h-28 w-28" src="/venues/angeethi-house/mark.svg" alt="" />
      <svg aria-hidden="true" viewBox="0 0 120 16" className="h-4 w-40">
        {[10, 30, 50, 70, 90, 110].map((x) => (
          <circle key={x} className="ah-coal" cx={x} cy={8} r={6} fill="#5e0016" />
        ))}
      </svg>
      <p className="ah-name font-serif text-4xl uppercase tracking-wide">{name}</p>
    </div>
  );
}
```

`src/brands/angeethi-house/Loader.tsx`:

```tsx
"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** Three embers pulse in turn; still under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(".ah-ember", { opacity: 1, scale: 1.25, transformOrigin: "50% 50%", duration: 0.35, stagger: 0.18, repeat: -1, yoyo: true });
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      <svg aria-hidden="true" viewBox="0 0 30 10" className={size === "sm" ? "w-6" : "w-12"}>
        {[5, 15, 25].map((x) => (
          <circle key={x} className="ah-ember" cx={x} cy={5} r={3} fill="var(--brand-spark)" opacity={0.45} />
        ))}
      </svg>
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
```

`src/brands/angeethi-house/index.ts`:

```ts
import type { BrandPackage } from "../types";
import { display, text } from "./fonts";
import { Loader } from "./Loader";
import { Motif } from "./Motif";
import { Welcome } from "./Welcome";

export const brand: BrandPackage = { fontClass: `${display.variable} ${text.variable}`, Motif, Welcome, Loader };
```

Register in `src/brands/index.ts`:

```ts
const PACKAGES: Record<string, () => Promise<BrandPackage>> = {
  "angeethi-house": () => import("./angeethi-house").then((m) => m.brand),
};
```

- [ ] **Step 6: Run the tests**

Run: `pnpm --filter guest-web exec vitest run src/brands/angeethi-house` → PASS. Then `tsc --noEmit` and `lint`.

- [ ] **Step 7: Commit**

```bash
git add apps/guest-web/package.json pnpm-lock.yaml apps/guest-web/src/brands
git commit -m "feat(brand): Angeethi House package — Anton and Work Sans, coal motif, GSAP welcome and loader"
```

---

### Task 7: The Kehwa & Crumb package

**Files:**
- Create: `apps/guest-web/src/brands/kehwa-and-crumb/{fonts.ts,Motif.tsx,Welcome.tsx,Loader.tsx,index.ts,package.test.tsx}`
- Modify: `apps/guest-web/src/brands/index.ts`, `apps/guest-web/src/app/globals.css`

- [ ] **Step 1: Write the failing test**

`src/brands/kehwa-and-crumb/package.test.tsx`:

```tsx
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

describe("Kehwa & Crumb package", () => {
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
  it("welcome names the venue (ampersand as text) and finishes under reduced motion", async () => {
    vi.useFakeTimers();
    reducedMotion(true);
    const onDone = vi.fn();
    const { container } = render(<brand.Welcome name="Kehwa & Crumb" onDone={onDone} />);
    expect(container.textContent).toContain("Kehwa & Crumb");
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    expect(onDone).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
```

Run: `pnpm --filter guest-web exec vitest run src/brands/kehwa-and-crumb` → FAIL.

- [ ] **Step 2: Fonts and light headings**

`src/brands/kehwa-and-crumb/fonts.ts`:

```ts
import { Jost, Karla } from "next/font/google";

// Light geometric display (calm tea room) and a soft text face. Free (OFL).
export const display = Jost({ subsets: ["latin"], weight: ["300", "400"], variable: "--brand-display-face", display: "swap" });
export const text = Karla({ subsets: ["latin"], variable: "--brand-text-face", display: "swap" });
```

Append to `apps/guest-web/src/app/globals.css`:

```css
[data-brand="kehwa-and-crumb"] :is(h1, h2, h3) {
  font-weight: 300;
  letter-spacing: 0.01em;
}
```

- [ ] **Step 3: Motif, Welcome, Loader**

`src/brands/kehwa-and-crumb/Motif.tsx`:

```tsx
/** Crumbs: a scatter under the masthead, a dotted line on the order bar. */
export function Motif({ variant }: { variant: "masthead" | "bar" }) {
  if (variant === "bar") {
    return (
      <svg aria-hidden="true" viewBox="0 0 100 4" preserveAspectRatio="none" className="block h-1 w-full">
        <line x1="0" y1="2" x2="100" y2="2" stroke="var(--brand-spark)" strokeWidth="1.5" strokeDasharray="1 3" strokeLinecap="round" />
      </svg>
    );
  }
  const crumbs: [number, number, number][] = [
    [7, 4, 1.2], [16, 7, 0.8], [27, 3, 1], [41, 6, 1.4], [55, 4, 0.9], [63, 8, 1.1], [78, 5, 0.8], [90, 3, 1.3],
  ];
  return (
    <svg aria-hidden="true" viewBox="0 0 100 10" className="block h-3 w-full">
      {crumbs.map(([x, y, r]) => (
        <circle key={x} cx={x} cy={y} r={r} fill="var(--brand-spark)" opacity={0.8} />
      ))}
    </svg>
  );
}
```

`src/brands/kehwa-and-crumb/Welcome.tsx`:

```tsx
"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** A cup fills with kehwa, crumbs settle, then the name. About 2 s; still under reduced motion. */
export function Welcome({ name, onDone }: { name: string; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap
          .timeline({ onComplete: onDone })
          .from(".kc-tea", { scaleY: 0, transformOrigin: "50% 100%", duration: 0.7, ease: "power2.out" })
          .from(".kc-crumb", { y: -40, opacity: 0, stagger: 0.07, duration: 0.45, ease: "bounce.out" }, "-=0.2")
          .from(".kc-name", { opacity: 0, y: 16, duration: 0.45 }, "-=0.1")
          .to({}, { duration: 0.35 });
      });
      mm.add("(prefers-reduced-motion: reduce)", () => {
        gsap.delayedCall(1.2, onDone);
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <div ref={root} className="flex flex-col items-center gap-5 text-[var(--brand-on-deep)]">
      <svg aria-hidden="true" viewBox="0 0 80 70" className="h-24 w-28">
        <path d="M10 18h50v22a25 25 0 0 1-50 0z" fill="none" stroke="var(--brand-on-deep)" strokeWidth="3" />
        <path d="M60 24h6a8 8 0 0 1 0 16h-6" fill="none" stroke="var(--brand-on-deep)" strokeWidth="3" />
        <path className="kc-tea" d="M13 24h44v16a22 22 0 0 1-44 0z" fill="var(--brand-spark)" />
        {[22, 33, 44, 51].map((x, i) => (
          <circle key={x} className="kc-crumb" cx={x} cy={i % 2 ? 66 : 64} r={2} fill="var(--brand-on-deep)" />
        ))}
      </svg>
      <p className="kc-name font-serif text-4xl">{name}</p>
    </div>
  );
}
```

`src/brands/kehwa-and-crumb/Loader.tsx`:

```tsx
"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/** Crumbs fall and gather; still under reduced motion. */
export function Loader({ label, size = "md" }: { label: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLSpanElement>(null);
  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          ".kc-bit",
          { y: -6, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.4, stagger: 0.15, repeat: -1, repeatDelay: 0.3, ease: "bounce.out" },
        );
      });
      return () => mm.revert();
    },
    { scope: root },
  );
  return (
    <span ref={root} role="status" className="inline-flex items-center gap-2 text-ink-muted">
      <svg aria-hidden="true" viewBox="0 0 30 12" className={size === "sm" ? "w-6" : "w-12"}>
        {[6, 13, 20, 26].map((x) => (
          <circle key={x} className="kc-bit" cx={x} cy={9} r={2} fill="var(--brand-accent)" />
        ))}
      </svg>
      <span className={size === "sm" ? "sr-only" : "text-xs"}>{label}</span>
    </span>
  );
}
```

`src/brands/kehwa-and-crumb/index.ts`:

```ts
import type { BrandPackage } from "../types";
import { display, text } from "./fonts";
import { Loader } from "./Loader";
import { Motif } from "./Motif";
import { Welcome } from "./Welcome";

export const brand: BrandPackage = { fontClass: `${display.variable} ${text.variable}`, Motif, Welcome, Loader };
```

Register in `src/brands/index.ts`, next to Angeethi:

```ts
  "kehwa-and-crumb": () => import("./kehwa-and-crumb").then((m) => m.brand),
```

- [ ] **Step 4: Run all brand tests (now the whole registry test)**

Run: `pnpm --filter guest-web exec vitest run src/brands` → PASS, including "has a package for every venue brand" and "no brand package imports another brand". Then `tsc --noEmit` and `lint`.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src/brands apps/guest-web/src/app/globals.css
git commit -m "feat(brand): Kehwa & Crumb package — Jost and Karla, crumb motif, GSAP welcome and loader"
```

---

### Task 8: Masthead, order-bar motif and loaders on the guest screens

**Files:**
- Create: `apps/guest-web/src/components/Masthead.tsx` (+ `.test.tsx`)
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx`, `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`

- [ ] **Step 1: Write the failing test**

`src/components/Masthead.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandShell } from "./BrandShell";
import { Masthead } from "./Masthead";

describe("Masthead", () => {
  it("shows the venue's lockup with the venue name as its text alternative", () => {
    const { getByRole } = render(
      <BrandShell venue={{ slug: "angeethi-house", name: "Angeethi House" }}>
        <Masthead />
      </BrandShell>,
    );
    expect(getByRole("img", { name: "Angeethi House" }).getAttribute("src")).toBe("/venues/angeethi-house/lockup.svg");
  });
  it("shows the name as text for a venue without a logo", () => {
    const { getByRole, container } = render(
      <BrandShell venue={{ slug: "new-venue", name: "New Venue" }}>
        <Masthead />
      </BrandShell>,
    );
    expect(getByRole("heading", { name: "New Venue" })).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
```

Run: `pnpm --filter guest-web exec vitest run src/components/Masthead.test.tsx` → FAIL.

- [ ] **Step 2: `Masthead`**

`src/components/Masthead.tsx`:

```tsx
"use client";

import { useVenue } from "./BrandShell";

/** The venue's band at the top of the menu: light logo lockup on the deep colour, then its motif. */
export function Masthead() {
  const { slug, name, branded, Motif } = useVenue();
  return (
    <div className="bg-[var(--brand-deep)] text-[var(--brand-on-deep)]">
      <div className="mx-auto flex max-w-2xl justify-center px-4 py-5">
        {branded ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`/venues/${slug}/lockup.svg`} alt={name} className="h-20 max-w-[70%] object-contain" />
        ) : (
          <h1 className="text-2xl">{name}</h1>
        )}
      </div>
      <Motif variant="masthead" />
    </div>
  );
}
```

- [ ] **Step 3: Use it, the bar motif and the loaders**

In `src/app/[lang]/menu/page.tsx` (`const { Motif, Loader } = useVenue();`):
- render `<Masthead />` as the first child of the page root, above the sticky `<header>` (it scrolls away; the sticky header stays);
- in the fixed bottom stack, inside the `barText` card, put `<Motif variant="bar" />` as its first child;
- replace the contents of the `if (loading)` block's spinner and "Loading menu..." text with `<Loader label="Loading menu..." />` (keep the wrapper);
- in the cart sheet's place-order button, while `submittingOrder`, render `<Loader label={dict.ui.placingOrder} size="sm" />` before the text.

In `src/app/[lang]/orders/[id]/page.tsx`: replace its initial loading spinner/text with `<Loader label=… />`, keeping the label text it shows today.

- [ ] **Step 4: Tests, types, lint, browser suite**

Run: `pnpm --filter guest-web test && pnpm --filter guest-web exec tsc --noEmit && pnpm --filter guest-web lint`
Rebuild guest-web and run `pnpm exec playwright test` → all pass, including "the assistant button never covers the last dish row" at 320 px (the masthead adds height at the top, not the bottom).

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src
git commit -m "feat(guest): venue masthead, order-bar motif and venue loaders on the guest screens"
```

---

### Task 9: QR table cards and the sample bill in the venue's brand

The owner app stays Mise-branded; only these two guest-facing printouts take the venue's brand.

**Files:**
- Create: `apps/owner-web/src/lib/venue-fonts.ts`
- Modify: `apps/owner-web/src/app/(dashboard)/tables/page.tsx` (cards ~305-345)
- Modify: `apps/owner-web/src/app/bills/[id]/print/page.tsx` (~line 57)
- Modify: `e2e/self-service.spec.ts` (the print test)

- [ ] **Step 1: Write the failing browser check**

In `e2e/self-service.spec.ts`, in the test that opens the print page (search `PRINT`), after the page loads add (use that test's own variable for the print page):

```ts
    await expect(printPage.getByRole("img", { name: "Angeethi House" })).toBeVisible();
    await expect(printPage.locator("body")).not.toContainText(/invoice|FBR integrated|compliant/i);
    await expect(printPage.locator('img[src*="/brand/logo-mark"]')).toHaveCount(0);
```

Run it (`pnpm exec playwright test e2e/self-service.spec.ts -g "<that test's title>"`) → FAIL (the Mise mark is there, no venue image).

- [ ] **Step 2: Display faces for printouts**

`apps/owner-web/src/lib/venue-fonts.ts`:

```ts
import { Anton, Jost } from "next/font/google";

// Display faces of the venue brands, for the printed QR cards and sample bill only.
const anton = Anton({ subsets: ["latin"], weight: "400", display: "swap" });
const jost = Jost({ subsets: ["latin"], weight: ["300", "400"], display: "swap" });

export const VENUE_DISPLAY_CLASS: Record<string, string> = {
  "angeethi-house": anton.className,
  "kehwa-and-crumb": jost.className,
};
```

- [ ] **Step 3: QR card**

In the tables page, get the selected venue's slug the way the page already does (read `src/lib/venue.tsx`), then `const brand = venueBrand(slug);` (`import { venueBrand } from "ui";`). At the top of each card, when `brand` exists:

```tsx
            {brand && (
              <div
                className="w-full rounded-xl px-4 py-4 [print-color-adjust:exact]"
                style={{ background: brand.tokens.deep }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/venues/${slug}/lockup.svg`} alt={brand.name} className="mx-auto h-12 w-auto" />
              </div>
            )}
```

Give the table label `<h2>` the class `VENUE_DISPLAY_CLASS[slug] ?? ""` and, when `brand` exists, `style={{ color: brand.tokens.accent }}`. Keep the URL line and the scan hint.

- [ ] **Step 4: Sample bill header**

In `bills/[id]/print/page.tsx`, replace the Mise `<Image src="/brand/logo-mark.svg" …/>` (line ~57) with the venue's mark when `venueBrand(slug)` exists (`/venues/${slug}/mark.svg`, `alt={brand.name}`, 48 × 48) and nothing otherwise; use `VENUE_DISPLAY_CLASS[slug]` on the venue-name heading and `brand.tokens.accent` for its colour, with `[print-color-adjust:exact]`. Keep the existing disclaimer word for word. Then:

Run: `grep -niE "invoice|fbr integrated|compliant|fiscal" "apps/owner-web/src/app/bills/[id]/print/page.tsx"`
Expected: no match outside a comment or test that forbids these words.

- [ ] **Step 5: Types, lint, unit tests, rebuild, browser suite**

Run: `pnpm --filter owner-web exec tsc --noEmit && pnpm --filter owner-web lint && pnpm --filter owner-web test`
Rebuild owner-web (`LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build --wait owner-web`), then `pnpm exec playwright test` → all pass, including the new print checks.

- [ ] **Step 6: Commit**

```bash
git add apps/owner-web/src e2e/self-service.spec.ts
git commit -m "feat(owner): QR table cards and the sample bill in the venue's brand"
```

---

### Task 10: One venue per guest, end to end, and the welcome rules

**Files:**
- Create: `e2e/one-venue.spec.ts`

- [ ] **Step 1: Write the test**

`e2e/one-venue.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { GUEST, demoInfo, skipWelcome } from "./helpers";

// A guest sees only the venue they scanned: no other venue, no venue list, no Mise.
test.describe("one venue per guest", () => {
  test("no other venue and no Mise anywhere a guest can go", async ({ browser, request }) => {
    const { venues } = await demoInfo();
    expect(venues.length).toBeGreaterThanOrEqual(2);

    for (const venue of venues) {
      const forbidden = [...venues.filter((o) => o.slug !== venue.slug).map((o) => o.name), "Mise"];
      const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
      const page = await context.newPage();

      const check = async (where: string, expectName: boolean) => {
        const text = await page.locator("body").innerText();
        const title = await page.title();
        const images = await page.$$eval("img", (els) =>
          els.map((e) => `${e.getAttribute("src")} ${e.getAttribute("alt")}`).join(" "),
        );
        const icons = await page.$$eval("link[rel~='icon'], link[rel='apple-touch-icon']", (els) =>
          els.map((e) => e.getAttribute("href")).join(" "),
        );
        const manifestHref = await page.locator("link[rel='manifest']").getAttribute("href", { timeout: 1000 }).catch(() => null);
        const manifest = manifestHref ? await (await request.get(new URL(manifestHref, GUEST).href)).text() : "";
        for (const word of forbidden) {
          for (const [label, value] of Object.entries({ text, title, images, icons, manifest })) {
            expect(value, `${venue.name} · ${where} · ${label} names "${word}"`).not.toContain(word);
          }
        }
        expect(await page.locator('a[href="/"]').count(), `${where} links to the venue list`).toBe(0);
        expect(icons, `${where} uses the Mise icon`).not.toContain("/brand/logo-mark");
        if (expectName) expect(title, `${where} title`).toContain(venue.name);
      };

      await page.goto(`${GUEST}/q/${venue.qr_token}`);
      await check("scan page", true);

      await page.getByRole("button", { name: "View Menu" }).click();
      await expect(page).toHaveURL(/\/en\/menu$/);
      await skipWelcome(page);
      await check("menu", true);

      await page.getByRole("button", { name: `Ask ${venue.name}` }).click();
      await check("menu with the assistant open", true);
      await page.getByRole("button", { name: "Close", exact: true }).click();

      await page.locator("main li").first().click(); // opens the dish sheet
      await check("dish sheet", true);
      await page.keyboard.press("Escape");

      await page.goto(`${GUEST}/en/orders/00000000-0000-0000-0000-000000000000`);
      await check("unknown order", true);

      await page.goto(`${GUEST}/no-such-page`);
      await check("not-found page", false);

      await page.goto(`${GUEST}/q/not-a-real-token`);
      await check("bad QR code", false);
      await expect(page.getByText("Scan the QR code on your table again.")).toBeVisible();

      await context.clearCookies();
      await page.goto(`${GUEST}/en/menu`);
      await check("expired visit", false);
      await expect(page.getByText("Scan the QR code on your table again.")).toBeVisible();

      await context.close();
    }
  });

  test("the welcome plays once per visit, can be tapped away and never blocks for more than 3 s", async ({ browser }) => {
    const { venues } = await demoInfo();
    const venue = venues[0];

    const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const page = await context.newPage();
    await page.goto(`${GUEST}/q/${venue.qr_token}`);
    await page.getByRole("button", { name: "View Menu" }).click();
    await expect(page).toHaveURL(/\/en\/menu$/);
    const welcome = page.getByTestId("welcome");
    await expect(welcome).toBeVisible({ timeout: 10_000 });
    const shownAt = Date.now();
    await expect(welcome).toBeHidden({ timeout: 3_500 }); // closes by itself
    expect(Date.now() - shownAt).toBeLessThan(3_500);

    await page.reload(); // same visit: not again
    await expect(page.locator("[data-welcome]").first()).toHaveAttribute("data-welcome", "done", { timeout: 10_000 });
    await expect(welcome).toHaveCount(0);
    await context.close();

    // Smallest phone, reduced motion: a tap skips it at once and the menu underneath is ready.
    const small = await browser.newContext({ viewport: { width: 320, height: 568 }, reducedMotion: "reduce" });
    const p2 = await small.newPage();
    await p2.goto(`${GUEST}/q/${venue.qr_token}`);
    await p2.getByRole("button", { name: "View Menu" }).click();
    const w2 = p2.getByTestId("welcome");
    await expect(w2).toBeVisible({ timeout: 10_000 });
    await w2.click();
    await expect(w2).toBeHidden();
    await expect(p2.locator("main li").first()).toBeVisible();
    await small.close();
  });
});
```

If `main li` is not the dish row selector in the current menu, use the selector the existing "assistant button never covers" test uses.

- [ ] **Step 2: Run it**

Rebuild guest-web, then `pnpm exec playwright test e2e/one-venue.spec.ts` → PASS. Every failure names the venue, the page and the leak; fix the leak in the app, never loosen the forbidden list.

- [ ] **Step 3: Whole browser suite**

Run: `pnpm exec playwright test` → all pass.

- [ ] **Step 4: Commit**

```bash
git add e2e/one-venue.spec.ts
git commit -m "test(e2e): a guest sees only the venue they scanned; the welcome plays once and never blocks"
```

---

### Task 11: Docs and the full check

- [ ] **Step 1: Docs**

In `docs/architecture.md`, in the guest app section, add a short paragraph: venue brands (`packages/ui/src/venue-brands.ts` for data, `apps/guest-web/src/brands/<slug>/` for fonts, motif, welcome and loader); how a page gets its venue (`[lang]/layout.tsx` and the scan page ask the API on the server); the neutral scan-again screen; and that the owner app brands only the QR cards and the sample bill. Describe only what exists.

- [ ] **Step 2: Full check**

Run, in order:
- `uv run --project services/api ruff check services/ scripts/ && uv run --project services/api ruff format --check services/ scripts/ && pnpm -r lint`
- `pnpm -r test`
- `bash scripts/check_branding.sh`
- `docker compose build api-test && docker compose run --rm api-test`
- stack rebuilt and seeded: `pnpm exec playwright test`

Expected: all green.

- [ ] **Step 3: Look at it**

Open the demo landing, then each venue's QR link at 375 × 812 and 320 × 568, normal and reduced motion. Confirm: the welcome, the masthead lockup, square buttons at Angeethi and pill buttons at Kehwa, prices in the fixed face, allergen chips unchanged. Note anything that looks off for the user.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: venue brands in the guest app"
```
