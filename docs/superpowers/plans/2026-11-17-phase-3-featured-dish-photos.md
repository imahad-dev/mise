# Phase 3 · Featured Dish Photos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each of the four demo venues shows 6 to 8 featured dishes with real, freely licensed photos in a "House favourites" strip at the top of the guest menu and in the dish sheet. Every other dish stays text-only.

**Architecture:** The data model is already there: `menu_items.featured` (migration 0003), `menu_items.image_url`, and both fields in `GuestMenuItemResponse`. **No migration is needed.** The seed script learns to write `image_url`. The guest menu gets one new component, `FavouritesStrip`, and the list stops showing inline photos. Photos are small WebP files in `apps/guest-web/public/venues/<slug>/dishes/<item key>.webp`. Their credits go in `data/photo_credits.json`, keyed by the same path as `image_url`. A Vitest check ties files, credits and seed `image_url`s together. A pytest check per venue enforces "6–8 featured, each with its photo".

**Tech Stack:** FastAPI seed script (Python), Next.js 15 guest app (React, Tailwind), Vitest, Playwright, `ffmpeg` (already on the machine) for the WebP conversion.

**Spec:** `docs/superpowers/specs/2026-11-09-four-identities-design.md`, phase 3.

**Branch:** `feat/four-identities` (current). Small commits, one logical change each.

---

## Where things stand (checked 2026-11-17)

| Venue | Featured now | `image_url` now |
|---|---|---|
| Angeethi House | 1 (`chicken_karahi`) | none |
| Kehwa & Crumb | 1 (`cappuccino`) | none |
| Noor & Za'atar | 8 | none |
| Tikka Town | 8 | none |

- `scripts/seed.py` sets `featured` (lines 345 and 374) but **never sets `image_url`**.
- `apps/guest-web/src/app/[lang]/menu/page.tsx:521-536` shows an inline 16:9 photo in the list for any dish with `image_url`. With the strip, a featured photo would show twice, so this block is removed ("other dishes stay text-only").
- `apps/guest-web/src/components/DishSheet.tsx:153-156` already shows `image_url` at 4:3. No change.

## Photo rules (apply in every sourcing task)

1. **The photo shows the dish it is attached to**, as the seed's English description says the plate holds it. A guest would recognise their order from it. A generic curry is not "Chicken Karahi". Plain fish and chips is not "Masala Fish and Chips" unless the batter is visibly spiced.
2. **Licence:** only the Unsplash License, the Pexels License or CC0 1.0. These need no on-screen attribution. CC BY / CC BY-SA photos are **not** used.
3. **No AI-generated images.** Reject any photo tagged or described as AI, generated or rendered, and any photo that looks synthetic.
4. **No people's faces and no brand logos or shop signs** in the frame. A photo with another restaurant's name would break the one-venue rule.
5. If no photo for a dish meets 1–4, **that dish is not featured**. Take the next dish from the venue's backup list. A venue ends with 6 to 8 featured dishes.
6. **Downloads:** ask the user once per venue before downloading ("Download about 8 photos from Unsplash/Pexels for <venue>?"). Save the originals to a new, empty scratchpad folder `photos/<slug>/`, never into the repo. Only the converted WebP goes into the repo.
7. **File:** `apps/guest-web/public/venues/<slug>/dishes/<key>.webp`, at most 800 px wide, at most 200 KB. `image_url` is `/venues/<slug>/dishes/<key>.webp`.

Convert one photo (from the repo root):

```bash
ffmpeg -y -i "<scratchpad>/photos/<slug>/<key>.jpg" -vf "scale='min(800,iw)':-2" -c:v libwebp -quality 72 "apps/guest-web/public/venues/<slug>/dishes/<key>.webp"
```

If a file is over 200 KB, rerun with `-quality 60`. Open the WebP with the Read tool and look at it before you use it.

Credit entry format in `data/photo_credits.json`:

```json
"/venues/tikka-town/dishes/lamb_chops.webp": {
  "dish": "Lamb Chops",
  "source_url": "https://unsplash.com/photos/<photo-id>",
  "author": "<photographer name as shown on the page>",
  "licence": "Unsplash License"
}
```

## Featured picks

The picks come first and the backups are tried in order. The keys are the seed `key` values.

| Venue | Picks | Backups |
|---|---|---|
| Angeethi House | `chicken_karahi`, `chicken_tikka`, `seekh_kebab`, `chicken_biryani`, `mutton_pulao`, `daal_mash`, `garlic_naan`, `gulab_jamun` | `palak_paneer`, `malai_boti`, `kheer`, `sweet_lassi`, `doodh_patti_chai` |
| Kehwa & Crumb | `cappuccino`, `karak_chai`, `butter_croissant`, `fudge_brownie`, `buttermilk_pancakes`, `french_toast`, `new_york_cheesecake`, `molten_lava_cake` | `green_kehwa`, `banana_bread`, `almond_croissant`, `iced_latte`, `chicken_club_sandwich` |
| Noor & Za'atar | `chicken_machboos`, `lamb_machboos`, `harees`, `luqaimat`, `karak_chai`, `zaatar_manakish`, `mixed_grill`, `mutton_biryani` (already featured) | `hummus`, `moutabal`, `shish_tawook`, `falafel`, `fattoush`, `tabbouleh`, `cheese_manakish`, `lamb_kofta` |
| Tikka Town | `lamb_chops`, `chicken_tikka_masala`, `masala_fish_and_chips`, `chicken_tikka_pie`, `spiced_lancashire_hotpot`, `sunday_roast`, `manchester_tart` (already featured) | `chicken_tikka`, `seekh_kebab`, `samosa_chaat`, `sticky_toffee_pudding`, `mango_lassi`, `eccles_cake`, `chips_and_curry_sauce`, `gulab_jamun` |

## File map

| File | Change |
|---|---|
| `scripts/seed.py` | Write `image_url` on create and update |
| `services/api/tests/test_seed_image_url.py` | New: the seed writes and clears `image_url` |
| `services/api/tests/test_featured_photos.py` | New: per venue, 6–8 featured, `image_url` exactly on featured dishes |
| `apps/guest-web/src/components/FavouritesStrip.tsx` | New: the "House favourites" strip |
| `apps/guest-web/src/app/[lang]/menu/page.tsx` | `featured` on the item type, strip above categories, inline list photo removed, shared price cell |
| `apps/guest-web/src/i18n/{types,en,ur,ar}.ts` | `menu.favourites` |
| `apps/guest-web/src/lib/photos.test.ts` | New: files ↔ credits ↔ seed `image_url` |
| `data/photo_credits.json` | New, `{}` at first |
| `apps/guest-web/public/venues/<slug>/dishes/*.webp` | New photos |
| `data/seed/*.json` | `featured` and `image_url` per pick |
| `e2e/favourites.spec.ts` | New: strip and dish sheet photo at all four venues |
| `README.md`, spec | One feature line, and a correction to the spec's migration note |

---

### Task 1: The seed writes `image_url`

**Files:**
- Create: `services/api/tests/test_seed_image_url.py`
- Modify: `scripts/seed.py:345` and `scripts/seed.py:374`

- [ ] **Step 1: Write the failing test**

```python
"""The seed writes a dish's image_url and clears it when the seed drops it (phase 3)."""

import copy

from scripts.seed import load_seed_data, seed_data
from sqlalchemy import select

from src.models import MenuItem, Restaurant

PHOTO = "/venues/tikka-town/dishes/lamb_chops.webp"


async def _urls(db_session) -> list[str | None]:
    r = (
        await db_session.execute(select(Restaurant).where(Restaurant.slug == "tikka-town"))
    ).scalar_one()
    rows = await db_session.execute(
        select(MenuItem.image_url).where(
            MenuItem.restaurant_id == r.id, MenuItem.image_url.is_not(None)
        )
    )
    return list(rows.scalars().all())


async def test_seed_sets_then_clears_image_url(db_session):
    base = load_seed_data("data/seed/tikka_town.json")
    for item in base["items"]:
        item.pop("image_url", None)

    with_photo = copy.deepcopy(base)
    with_photo["items"][0]["image_url"] = PHOTO
    await seed_data(with_photo, db_session)  # create path
    assert await _urls(db_session) == [PHOTO]

    await seed_data(copy.deepcopy(base), db_session)  # update path
    assert await _urls(db_session) == []
```

- [ ] **Step 2: Run it and check that it fails**

Run: `make test-py`
Expected: `test_seed_sets_then_clears_image_url` FAILS (`[] == [PHOTO]`).

- [ ] **Step 3: Write `image_url` in both branches of `scripts/seed.py`**

In the `MenuItem(...)` constructor, after `featured=item_data.get("featured", False),`, add:

```python
                image_url=item_data.get("image_url"),
```

In the update branch, after `target_item.featured = item_data.get("featured", False)`, add:

```python
            target_item.image_url = item_data.get("image_url")
```

- [ ] **Step 4: Run the tests and check that they pass**

Run: `make test-py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed.py services/api/tests/test_seed_image_url.py
git commit -m "feat(seed): seed files set each dish's photo (image_url)"
```

---

### Task 2: Files, credits and seed agree (guard before any photo lands)

**Files:**
- Create: `data/photo_credits.json`
- Create: `apps/guest-web/src/lib/photos.test.ts`

- [ ] **Step 1: Create the empty credits file**

`data/photo_credits.json`:

```json
{}
```

- [ ] **Step 2: Write the check**

`apps/guest-web/src/lib/photos.test.ts`:

```ts
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Dish photos (spec 2026-11-09, phase 3): every photo has a free-licence credit, every credit
// and every seed image_url points at a real file, and nothing is left unused.
const ROOT = fileURLToPath(new URL("../../../../", import.meta.url));
const PUBLIC = join(ROOT, "apps/guest-web/public");
const LICENCES = ["Unsplash License", "Pexels License", "CC0 1.0"];
const MAX_BYTES = 200 * 1024;

interface Credit {
  dish: string;
  source_url: string;
  author: string;
  licence: string;
}
const credits: Record<string, Credit> = JSON.parse(
  readFileSync(join(ROOT, "data/photo_credits.json"), "utf8"),
);

const photos = readdirSync(join(PUBLIC, "venues")).flatMap((slug) => {
  const dir = join(PUBLIC, "venues", slug, "dishes");
  return existsSync(dir) ? readdirSync(dir).map((f) => `/venues/${slug}/dishes/${f}`) : [];
});

const seedUrls: string[] = readdirSync(join(ROOT, "data/seed"))
  .filter((f) => f.endsWith(".json"))
  .flatMap((f) => JSON.parse(readFileSync(join(ROOT, "data/seed", f), "utf8")).items ?? [])
  .map((i: { image_url?: string | null }) => i.image_url)
  .filter((u: string | null | undefined): u is string => Boolean(u));

describe("dish photos", () => {
  it.each(photos)("%s is a small WebP with a free-licence credit", (photo) => {
    expect(photo).toMatch(/^\/venues\/[a-z-]+\/dishes\/[a-z0-9_]+\.webp$/);
    expect(statSync(join(PUBLIC, photo)).size).toBeLessThanOrEqual(MAX_BYTES);
    const c = credits[photo];
    expect(c, `no credit for ${photo}`).toBeDefined();
    expect(c.source_url).toMatch(/^https:\/\//);
    expect(c.author.trim()).not.toBe("");
    expect(c.dish.trim()).not.toBe("");
    expect(LICENCES).toContain(c.licence);
  });

  it("every credit names a photo that exists", () => {
    expect(Object.keys(credits).filter((p) => !photos.includes(p))).toEqual([]);
  });

  it("every seed image_url is a photo that exists, and every photo is used", () => {
    expect(seedUrls.filter((u) => !photos.includes(u))).toEqual([]);
    expect(photos.filter((p) => !seedUrls.includes(p))).toEqual([]);
  });
});
```

- [ ] **Step 3: Run it**

Run: `pnpm --dir apps/guest-web exec vitest run src/lib/photos.test.ts`
Expected: PASS. With no photos yet, the `it.each` is empty and the two list checks pass. This guards every sourcing commit that follows.

- [ ] **Step 4: Prove that it catches an uncredited photo**

```bash
mkdir -p apps/guest-web/public/venues/tikka-town/dishes && cp apps/guest-web/public/venues/tikka-town/mark.svg apps/guest-web/public/venues/tikka-town/dishes/x.webp
```

Run: `pnpm --dir apps/guest-web exec vitest run src/lib/photos.test.ts`
Expected: FAIL (`no credit for /venues/tikka-town/dishes/x.webp`, and "every photo is used").

```bash
rm -r apps/guest-web/public/venues/tikka-town/dishes
```

- [ ] **Step 5: Commit**

```bash
git add data/photo_credits.json apps/guest-web/src/lib/photos.test.ts
git commit -m "test(guest): dish photos need a free-licence credit and a seed dish"
```

---

### Task 3: "House favourites" strip

**Files:**
- Create: `apps/guest-web/src/components/FavouritesStrip.tsx`
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx` (item type ~line 73, list ~lines 517–550)
- Modify: `apps/guest-web/src/i18n/types.ts:85-90`, `en.ts`, `ur.ts`, `ar.ts` (`menu` block)

- [ ] **Step 1: Add the dictionary key (the i18n test fails until all three have it)**

`types.ts`, in `menu: { … }`, after `serviceNotice: string;`:

```ts
    /** Heading of the featured-dish photo strip. */
    favourites: string;
```

`en.ts`, in `menu`: `favourites: "House favourites",`
`ur.ts`, in `menu`: `favourites: "ہماری خاص ڈشیں",`
`ar.ts`, in `menu`: `favourites: "أطباقنا المميزة",`

Run: `pnpm --dir apps/guest-web exec vitest run src/i18n`
Expected: PASS. The every-key test covers the new key in `ur` and `ar`.

- [ ] **Step 2: Create the strip**

`apps/guest-web/src/components/FavouritesStrip.tsx`:

```tsx
"use client";

import type { ReactNode } from "react";

interface Favourite {
  id: string;
  name: string;
  featured?: boolean;
  available?: boolean;
  image_url?: string | null;
}

/** Featured dishes with a photo, in menu order; tapping one opens its dish sheet. */
export function FavouritesStrip<T extends Favourite>({
  items,
  title,
  price,
  onOpen,
}: {
  items: T[];
  title: string;
  price: (item: T) => ReactNode;
  onOpen: (item: T) => void;
}) {
  const shown = items.filter((i) => i.featured && i.image_url && i.available !== false);
  if (shown.length === 0) return null;
  return (
    <section aria-labelledby="favourites-title">
      <h2 id="favourites-title" className="border-b border-line pb-1 text-lg font-semibold italic text-terracotta">
        {title}
      </h2>
      <ul className="-mx-4 mt-3 flex snap-x gap-3 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6">
        {shown.map((item) => (
          <li key={item.id} className="w-40 shrink-0 snap-start">
            <button type="button" className="block w-full text-start" onClick={() => onOpen(item)}>
              {/* eslint-disable-next-line @next/next/no-img-element -- small local WebP, lazy */}
              <img
                src={item.image_url!}
                loading="lazy"
                alt=""
                width={800}
                height={600}
                className="aspect-[4/3] w-full rounded-xl object-cover"
              />
              <span className="mt-1.5 block text-sm font-semibold text-ink">{item.name}</span>
              <span className="block text-sm text-ink">{price(item)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

`alt=""` is deliberate because the dish name is the button's text right below the photo.

- [ ] **Step 3: Wire it into the menu page**

In `page.tsx`'s `MenuItem` interface, after `available: boolean;`, add:

```ts
  featured?: boolean;
```

Add the import next to the other component imports, copying the path style of the existing `DishSheet` import (for example `@/components/…`):

```ts
import { FavouritesStrip } from "@/components/FavouritesStrip";
```

Before the `return (` of the menu (next to `lineLabel`), add the shared price cell. It is the same markup the list uses today:

```tsx
  const priceCell = (item: MenuItem) => {
    const options = item.options ?? [];
    return (
      <>
        {options.length > 0 && `${dict.menu.from} `}
        <span className="figure">
          {options.length > 0
            ? formatPrice(Math.min(...options.map((o) => Number(o.price))))
            : formatPrice(Number(item.price))}
        </span>
      </>
    );
  };
```

Inside `<main …>`, before `{categories.map((cat) => (`, add:

```tsx
        <FavouritesStrip items={menu.items} title={dict.menu.favourites} price={priceCell} onOpen={setDishOpen} />
```

In the list, **delete** the whole `{item.image_url && isAvailable && ( <button …> … <img …/> </button> )}` block. Then replace the price span and its children so the list uses the shared cell:

```tsx
                        <span className="whitespace-nowrap font-semibold text-ink">{priceCell(item)}</span>
```

If `const options = item.options ?? [];` in the list `map` is now unused, delete it. The lint step will tell you.

- [ ] **Step 4: Type-check, lint, unit tests**

Run: `pnpm --dir apps/guest-web exec tsc --noEmit && pnpm --dir apps/guest-web lint && pnpm --dir apps/guest-web test`
Expected: no errors, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src/components/FavouritesStrip.tsx "apps/guest-web/src/app/[lang]/menu/page.tsx" apps/guest-web/src/i18n
git commit -m "feat(guest): House favourites strip; menu list stays text-only"
```

---

### Task 4: Tikka Town photos

Tikka Town comes first because its 8 picks are already featured, so only photos are needed.

**Files:**
- Create: `services/api/tests/test_featured_photos.py`
- Create: `apps/guest-web/public/venues/tikka-town/dishes/*.webp`
- Modify: `data/seed/tikka_town.json`, `data/photo_credits.json`

- [ ] **Step 1: Write the failing per-venue rule**

`services/api/tests/test_featured_photos.py`:

```python
"""Phase 3: each venue features 6 to 8 dishes, each with its own photo, and no other dish
has one (spec 2026-11-09, phase 3). Files and credits are checked in
apps/guest-web/src/lib/photos.test.ts."""

import json

import pytest

SEEDS = {
    "tikka-town": "data/seed/tikka_town.json",
}


@pytest.mark.parametrize("slug", SEEDS)
def test_six_to_eight_featured_each_with_its_photo(slug):
    with open(SEEDS[slug], encoding="utf-8") as f:
        items = json.load(f)["items"]
    assert 6 <= sum(i["featured"] for i in items) <= 8
    for i in items:
        expected = f"/venues/{slug}/dishes/{i['key']}.webp" if i["featured"] else None
        assert i.get("image_url") == expected, i["key"]
```

Run: `make test-py`
Expected: FAIL on `lamb_chops` (`None == '/venues/tikka-town/dishes/lamb_chops.webp'`).

- [ ] **Step 2: Ask the user for permission to download** about 8 photos for Tikka Town (photo rule 6).

- [ ] **Step 3: Source each pick** in the Tikka Town row of the featured picks table. For each one, follow photo rules 1–5 in the built-in browser on unsplash.com and pexels.com. Read the dish's English `description` in `tikka_town.json` first. Download each accepted photo to `<scratchpad>/photos/tikka-town/<key>.jpg`.

- [ ] **Step 4: Convert each photo** with the `ffmpeg` command in the photo rules, then open each WebP with Read and confirm it shows the dish.

- [ ] **Step 5: Update the seed.** For each pick that got a photo, add `"image_url": "/venues/tikka-town/dishes/<key>.webp"` after its `"featured": true`. For a pick with no acceptable photo, set `"featured": false`, take the next backup, set its `"featured": true` and add its `image_url`.

- [ ] **Step 6: Add one credit entry per photo** to `data/photo_credits.json` (format above).

- [ ] **Step 7: Run both checks**

Run: `make test-py && pnpm --dir apps/guest-web exec vitest run src/lib/photos.test.ts`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add services/api/tests/test_featured_photos.py data/seed/tikka_town.json data/photo_credits.json apps/guest-web/public/venues/tikka-town/dishes
git commit -m "feat(data): Tikka Town featured dishes get credited photos"
```

---

### Task 5: Noor & Za'atar photos

**Files:**
- Modify: `services/api/tests/test_featured_photos.py`, `data/seed/noor_and_zaatar.json`, `data/photo_credits.json`
- Create: `apps/guest-web/public/venues/noor-and-zaatar/dishes/*.webp`

- [ ] **Step 1: Add the venue to the rule**

In `SEEDS` in `test_featured_photos.py`, add:

```python
    "noor-and-zaatar": "data/seed/noor_and_zaatar.json",
```

Run: `make test-py`
Expected: FAIL on `chicken_machboos`.

- [ ] **Step 2: Ask the user for permission to download** about 8 photos for Noor & Za'atar.

- [ ] **Step 3: Source each pick** in the Noor & Za'atar row of the featured picks table (photo rules 1–5), checking each photo against the dish's English `description` in `noor_and_zaatar.json`. Machboos must show spiced rice with the meat on top. Harees is a smooth wheat-and-meat porridge, and if no accurate free photo exists, swap in a backup (rule 5). Save the downloads to `<scratchpad>/photos/noor-and-zaatar/<key>.jpg`.

- [ ] **Step 4: Convert and look at each photo** (`ffmpeg` command, then Read).

- [ ] **Step 5: Update the seed**: add `"image_url": "/venues/noor-and-zaatar/dishes/<key>.webp"` to each featured dish, and swap any dish without a photo for a backup (as in Task 4 Step 5).

- [ ] **Step 6: Add the credits.**

- [ ] **Step 7: Run both checks**

Run: `make test-py && pnpm --dir apps/guest-web exec vitest run src/lib/photos.test.ts`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add services/api/tests/test_featured_photos.py data/seed/noor_and_zaatar.json data/photo_credits.json apps/guest-web/public/venues/noor-and-zaatar/dishes
git commit -m "feat(data): Noor & Za'atar featured dishes get credited photos"
```

---

### Task 6: Angeethi House photos

**Files:**
- Modify: `services/api/tests/test_featured_photos.py`, `data/seed/angeethi_house.json`, `data/photo_credits.json`
- Create: `apps/guest-web/public/venues/angeethi-house/dishes/*.webp`

- [ ] **Step 1: Add the venue to the rule**

In `SEEDS`, add:

```python
    "angeethi-house": "data/seed/angeethi_house.json",
```

Run: `make test-py`
Expected: FAIL because only 1 dish is featured (`assert 6 <= 1`).

- [ ] **Step 2: Ask the user for permission to download** about 8 photos for Angeethi House.

- [ ] **Step 3: Source each pick** in the Angeethi House row (photo rules 1–5), checking each one against the English `description` in `angeethi_house.json`. Daal Mash is white urad daal, not yellow daal. Save the downloads to `<scratchpad>/photos/angeethi-house/<key>.jpg`.

- [ ] **Step 4: Convert and look at each photo.**

- [ ] **Step 5: Update the seed**: for each dish that got a photo, set `"featured": true` and add `"image_url": "/venues/angeethi-house/dishes/<key>.webp"`. Leave every other dish `"featured": false` with no `image_url`. `chicken_karahi` keeps `featured: true` only if it got a photo.

- [ ] **Step 6: Add the credits.**

- [ ] **Step 7: Run both checks**

Run: `make test-py && pnpm --dir apps/guest-web exec vitest run src/lib/photos.test.ts`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add services/api/tests/test_featured_photos.py data/seed/angeethi_house.json data/photo_credits.json apps/guest-web/public/venues/angeethi-house/dishes
git commit -m "feat(data): Angeethi House features 6-8 dishes with credited photos"
```

---

### Task 7: Kehwa & Crumb photos

**Files:**
- Modify: `services/api/tests/test_featured_photos.py`, `data/seed/kehwa_and_crumb.json`, `data/photo_credits.json`
- Create: `apps/guest-web/public/venues/kehwa-and-crumb/dishes/*.webp`

- [ ] **Step 1: Add the venue to the rule**

In `SEEDS`, add:

```python
    "kehwa-and-crumb": "data/seed/kehwa_and_crumb.json",
```

Run: `make test-py`
Expected: FAIL (`assert 6 <= 1`).

- [ ] **Step 2: Ask the user for permission to download** about 8 photos for Kehwa & Crumb.

- [ ] **Step 3: Source each pick** in the Kehwa & Crumb row (photo rules 1–5), checking each one against the English `description` in `kehwa_and_crumb.json`. Karak chai is milky, deep-brewed tea in a glass or cup, not a latte. Save the downloads to `<scratchpad>/photos/kehwa-and-crumb/<key>.jpg`.

- [ ] **Step 4: Convert and look at each photo.**

- [ ] **Step 5: Update the seed** as in Task 6 Step 5, with slug `kehwa-and-crumb`.

- [ ] **Step 6: Add the credits.**

- [ ] **Step 7: Run both checks**

Run: `make test-py && pnpm --dir apps/guest-web exec vitest run src/lib/photos.test.ts`
Expected: all pass. `SEEDS` now lists all four venues.

- [ ] **Step 8: Commit**

```bash
git add services/api/tests/test_featured_photos.py data/seed/kehwa_and_crumb.json data/photo_credits.json apps/guest-web/public/venues/kehwa-and-crumb/dishes
git commit -m "feat(data): Kehwa & Crumb features 6-8 dishes with credited photos"
```

---

### Task 8: Browser check at all four venues

**Files:**
- Create: `e2e/favourites.spec.ts`

- [ ] **Step 1: Write the test**

```ts
import { expect, test } from "@playwright/test";
import { ANGEETHI, KEHWA, NOOR, TIKKA, clearDemoLimits, openTable, openTableMenu, venueTables } from "./helpers";

// Phase 3: each venue's menu opens with a House favourites strip of its own 6-8 dish photos;
// a photo opens that dish's sheet with the same photo. The list below stays text-only.
test.beforeEach(() => clearDemoLimits());

for (const slug of [ANGEETHI, KEHWA, NOOR, TIKKA]) {
  test(`${slug}: House favourites strip and dish sheet photo`, async ({ page }) => {
    const tables = await venueTables(slug);
    const label = Object.keys(tables).at(-1)!;
    await openTable(slug, label);
    await openTableMenu(page, tables[label].qr_token);

    const strip = page.locator("section", { has: page.getByRole("heading", { name: "House favourites" }) });
    const photos = strip.locator("img");
    const count = await photos.count();
    expect(count).toBeGreaterThanOrEqual(6);
    expect(count).toBeLessThanOrEqual(8);
    for (let i = 0; i < count; i++) {
      await photos.nth(i).scrollIntoViewIfNeeded();
      await expect(photos.nth(i)).toHaveAttribute("src", new RegExp(`^/venues/${slug}/dishes/[a-z0-9_]+\\.webp$`));
      await expect.poll(() => photos.nth(i).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
    }

    // The strip's photos are the only images in the menu: the list below is text-only.
    await expect(page.locator("main li img")).toHaveCount(count);

    const src = await photos.first().getAttribute("src");
    await strip.getByRole("button").first().click();
    await expect(page.getByRole("dialog").locator(`img[src="${src}"]`)).toBeVisible();
  });
}
```

- [ ] **Step 2: Run it against a fresh stack**

```bash
LLM_PROVIDER=mock DEMO_MODE=true make up
```

```bash
make seed && pnpm exec playwright test e2e/favourites.spec.ts
```

Expected: 4 passed. If `openTableMenu` leaves the welcome animation over the page, add `await skipWelcome(page);` after it (import from `./helpers`), as `new-venues.spec.ts` does.

- [ ] **Step 3: Run the one-venue walk too**, since dish photo paths must carry only the venue's own slug:

Run: `pnpm exec playwright test e2e/one-venue.spec.ts`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add e2e/favourites.spec.ts
git commit -m "test(e2e): House favourites photos at all four venues"
```

---

### Task 9: Docs and full verification

**Files:**
- Modify: `README.md` (Features → guest list, after the "Dish choices" bullet)
- Modify: `docs/superpowers/specs/2026-11-09-four-identities-design.md` (phase 3, first bullet)

- [ ] **Step 1: README bullet** after the "Dish choices" bullet:

```markdown
  - **House favourites**: each venue features 6 to 8 signature dishes with a photo, in a strip at the top of the menu and in the dish sheet; every other dish is text-only. Photos are freely licensed (Unsplash, Pexels or CC0, no AI images), stored as small WebP files in `apps/guest-web/public/venues/<slug>/dishes/`, and credited in `data/photo_credits.json`; a test fails for an uncredited or unused photo.
```

- [ ] **Step 2: Spec correction.** In phase 3's first bullet, replace "A new boolean `menu_items.featured` (Alembic migration, default false) is set from the seed files" with "`menu_items.featured` (already in migration 0003, default false) is set from the seed files, and the seed now writes `image_url`".

- [ ] **Step 3: Full checks**

```bash
make ci
```

```bash
make verify-f
```

Expected: both pass, branding check included.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-11-09-four-identities-design.md
git commit -m "docs: House favourites photos and their credits"
```

---

## Spec coverage

| Spec line (phase 3 + Tests) | Task |
|---|---|
| 6–8 featured per venue, set from seeds, in guest response | 4–7 (response field already exists) |
| `featured` migration | Not needed, column exists; spec corrected in 9 |
| "House favourites" strip at top; photo in dish sheet; others text-only | 3, 8 |
| WebP under `public/venues/<slug>/dishes/`, lazy, via `image_url` | 1, 3, 4–7 |
| Photo shows its dish, else not featured | Photo rules 1 and 5, tasks 4–7 |
| Free licence, no AI, credit per photo; test fails without credit | Photo rules 2–3, task 2 |
| Every featured dish has an existing `image_url` and a credit | Tasks 2, 4–7 |
| One venue per guest still holds | Task 8 Step 3 |
| `make ci` and `make verify-f` | Task 9 |
