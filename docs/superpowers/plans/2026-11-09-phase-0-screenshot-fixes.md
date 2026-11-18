# Phase 0 · Screenshot-review fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five small faults found in the screenshot review (spec `docs/superpowers/specs/2026-11-09-four-identities-design.md`, "Phase 0").

**Architecture:** Five independent fixes, one commit each. Pure helpers get a unit test (Vitest for the Next.js apps, pytest for the API); the kitchen count also gets one line in an existing Playwright test. No new dependencies, no schema change.

**Tech Stack:** Next.js 15 + Vitest (`apps/guest-web`, `apps/owner-web`), FastAPI + pytest (`services/api`), the mock LLM (`services/inference/mock`), Playwright (`e2e/`).

**Branch:** `feat/four-identities`. Never commit to `main`. Do not stage `.gitignore`, `.claude/` or `.impeccable/` (unrelated local changes).

**Rules that bite here:** never read `.env`; any manual check runs with `LLM_PROVIDER=mock`; never weaken a test. Task 2 changes one existing assertion because the spec changes the format, and the commit message says so.

---

## File map

| File | Change |
|---|---|
| `apps/owner-web/src/lib/kitchen.ts` | **New.** `activeLabel(n)` and `keepUnits(text)` |
| `apps/owner-web/src/lib/kitchen.test.ts` | **New.** Tests for both |
| `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx` | Use both helpers (lines ~274 and ~386-387) |
| `e2e/self-service.spec.ts` | One line: "1 ORDER ACTIVE" (after line ~233) |
| `services/api/src/services/brief.py` | New `fmt_money()`; `template_summary()` uses it and rounds the margin % |
| `services/api/tests/test_analytics_pure.py` | Update one assertion (~line 480), add two tests |
| `services/inference/mock/src/canned.py` | Venue-neutral `DAILY_BRIEF["summary"]` (line 22) |
| `apps/guest-web/src/lib/ordering.ts` | New `orderRef(id)` |
| `apps/guest-web/src/lib/ordering.test.ts` | Test for it |
| `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx` | Show `orderRef(id)` instead of the UUID (line ~191) |
| `apps/guest-web/src/app/[lang]/menu/page.tsx` | Bottom padding clears the assistant button (line ~455) |

---

### Task 1: Kitchen count in the singular, and "1 kg" never wraps

**Files:**
- Create: `apps/owner-web/src/lib/kitchen.ts`
- Test: `apps/owner-web/src/lib/kitchen.test.ts`
- Modify: `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx` (~274, ~386-387)
- Modify: `e2e/self-service.spec.ts` (~233)

- [ ] **Step 1: Write the failing test**

`apps/owner-web/src/lib/kitchen.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { activeLabel, keepUnits } from "./kitchen";

describe("activeLabel", () => {
  it("uses the singular for one order only", () => {
    expect(activeLabel(0)).toBe("0 ORDERS ACTIVE");
    expect(activeLabel(1)).toBe("1 ORDER ACTIVE");
    expect(activeLabel(2)).toBe("2 ORDERS ACTIVE");
  });
});

describe("keepUnits", () => {
  it("joins a quantity to its unit with a non-breaking space", () => {
    expect(keepUnits("Mutton karahi 1 kg")).toBe("Mutton karahi 1\u00a0kg");
    expect(keepUnits("Half 0.5 kg, 250 g, 330 ml")).toBe("Half 0.5\u00a0kg, 250\u00a0g, 330\u00a0ml");
  });

  it("leaves words that only start with a unit letter alone", () => {
    expect(keepUnits("2 garlic naan")).toBe("2 garlic naan");
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `pnpm --filter owner-web exec vitest run src/lib/kitchen.test.ts`
Expected: FAIL, because `./kitchen` cannot be resolved.

- [ ] **Step 3: Write the helpers**

`apps/owner-web/src/lib/kitchen.ts`:

```ts
/** Header count on the kitchen screen: "1 ORDER ACTIVE", "3 ORDERS ACTIVE". */
export function activeLabel(n: number): string {
  return `${n} ${n === 1 ? "ORDER" : "ORDERS"} ACTIVE`;
}

/** Keeps "1 kg" on one line: a non-breaking space between a number and its unit. */
export function keepUnits(text: string): string {
  return text.replace(/(\d) (kg|g|ml|l|pc|pcs)\b/gi, "$1\u00a0$2");
}
```

- [ ] **Step 4: Run the test to see it pass**

Run: `pnpm --filter owner-web exec vitest run src/lib/kitchen.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Use the helpers in the kitchen page**

In `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx`, add next to the other lib imports (follow the file's existing style, `@/lib/...` or relative):

```ts
import { activeLabel, keepUnits } from "@/lib/kitchen";
```

Replace (~line 274):

```tsx
            {placedOrders.length} ORDERS ACTIVE
```

with:

```tsx
            {activeLabel(placedOrders.length)}
```

Replace (~lines 386-387):

```tsx
                          {item.kitchen_name}
                          {item.option_label && <span className="text-kds-accent"> — {item.option_label}</span>}
```

with:

```tsx
                          {keepUnits(item.kitchen_name)}
                          {item.option_label && <span className="text-kds-accent"> — {keepUnits(item.option_label)}</span>}
```

- [ ] **Step 6: Add the singular check to the e2e test**

In `e2e/self-service.spec.ts`, in the test "nothing reaches the barista until cash is confirmed…", right after:

```ts
    await expect(kitchen.getByRole("heading", { name: `PICKUP ${label}` })).toBeVisible();
```

add:

```ts
    await expect(kitchen.getByText("1 ORDER ACTIVE")).toBeVisible();
```

The existing `"0 ORDERS ACTIVE"` check a few lines above stays as it is.

- [ ] **Step 7: Type-check and run the app's tests**

Run: `pnpm --filter owner-web exec tsc --noEmit && pnpm --filter owner-web test`
Expected: no type errors; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add apps/owner-web/src/lib/kitchen.ts apps/owner-web/src/lib/kitchen.test.ts "apps/owner-web/src/app/(kitchen)/kitchen/page.tsx" e2e/self-service.spec.ts
git commit -m "fix(kitchen): '1 ORDER ACTIVE' in the singular; keep '1 kg' on one line"
```

---

### Task 2: Brief summary amounts in the venue's money format

The summary today reads `PKR 12345.67`, while the rest of the owner app shows `Rs 12,346`. Format every amount in `template_summary()` the way `formatPrice()` in `packages/ui/src/format.ts` does for English, and round the margin % to one decimal.

Leave the what-if text (`Estimated weekly change: …`) alone. `test_pakistan_what_if_text_unchanged` in `services/api/tests/test_global_bills.py` pins it, and the spec only names the summary.

The number-consistency check (`services/api/src/services/narrative.py`) already accepts grouped numbers (`12,346`) and numbers rounded to the text's precision, so formatted amounts still pass it.

**Files:**
- Modify: `services/api/src/services/brief.py` (`template_summary`, ~line 312)
- Test: `services/api/tests/test_analytics_pure.py` (~line 464 onward)

- [ ] **Step 1: Write the failing tests and update the old assertion**

In `services/api/tests/test_analytics_pure.py`, in `test_template_summary_only_uses_fact_numbers`, replace:

```python
    assert "PKR 12345.67" in text and "EUR" not in text
```

with:

```python
    assert "Rs 12,346" in text and "PKR" not in text and "EUR" not in text
```

Add `fmt_money` to the file's existing import from `src.services.brief` (next to `template_summary`), then append:

```python
def test_fmt_money_matches_the_owner_app():
    assert fmt_money("PKR", 12345.67) == "Rs 12,346"
    assert fmt_money("EUR", 12345.6) == "€12,345.60"
    assert fmt_money("GBP", 23.634) == "£23.63"
    assert fmt_money("AED", 105) == "AED 105.00"
    assert fmt_money("USD", 1.5) == "USD 1.50"
    assert fmt_money("GBP", -4.5) == "-£4.50"


def test_template_summary_rounds_margin_and_groups_amounts():
    facts = {
        **FACTS,
        "currency": "GBP",
        "kpis": {
            "orders": 812,
            "revenue": 12345.678,
            "aov": 15.2,
            "contribution_margin": 9000.1,
            "margin_pct": 72.9384,
        },
        "data_sources": {"live": 812, "simulated": 0},
        "actions": [],
    }
    text = template_summary(facts)
    assert "£12,345.68" in text and "£9,000.10" in text
    assert "72.9%" in text and "72.93" not in text
    assert "GBP" not in text
    assert numbers_grounded(text, facts)
```

`FACTS` and `numbers_grounded` are already used by the neighbouring summary tests; reuse the same names.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --project services/api pytest services/api/tests/test_analytics_pure.py -k "template_summary or fmt_money" -q`
Expected: FAIL with `ImportError: cannot import name 'fmt_money'`.

- [ ] **Step 3: Add `fmt_money` and use it**

In `services/api/src/services/brief.py`, just above `def template_summary`:

```python
_SYMBOLS = {"EUR": "€", "GBP": "£"}


def fmt_money(currency: str, amount: float) -> str:
    """Amount as the owner app shows it (formatPrice, en): Rs 12,346 · €12,345.60 · AED 105.00."""
    sign = "-" if amount < 0 else ""
    a = abs(float(amount))
    if currency == "PKR":
        return f"{sign}Rs {round(a):,}"
    if currency in _SYMBOLS:
        return f"{sign}{_SYMBOLS[currency]}{a:,.2f}"
    return f"{sign}{currency} {a:,.2f}"
```

Then in `template_summary`, replace every `{cur} {X}` amount with `{fmt_money(cur, X)}` and round the margin %:

```python
    text = (
        f"In the {w['days']} days to {w['end']}: {k['orders']} orders, revenue "
        f"{fmt_money(cur, k['revenue'])}{net}, average order {fmt_money(cur, k['aov'])}{net}, "
        f"contribution margin {fmt_money(cur, k['contribution_margin'])}{net_sep}"
        f"{round(k['margin_pct'], 1)}%)."
    )
    money = [a for a in facts["actions"] if a["estimated_impact_per_week"] is not None]
    if money:
        text += (
            f" Top action: {money[0]['title']} "
            f"(estimated {fmt_money(cur, money[0]['estimated_impact_per_week'])} per week)."
        )
    pm = facts.get("payment_mix")
    if pm and (pm["bills"]["standard"] or pm["bills"]["digital"]):
        text += (
            f" Digital payments were {pm['digital_revenue_pct']}% of billed revenue and saved "
            f"guests {fmt_money(cur, pm['digital_tax_saving'])} in tax."
        )
```

`float(amount)` inside `fmt_money` covers KPI values that arrive as `Decimal`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run --project services/api pytest services/api/tests/test_analytics_pure.py -q`
Expected: all pass. If `test_template_summary_states_digital_share_and_saving` asserts a raw `PKR …` string, update it to the `Rs …` form the same way and say so in the commit.

- [ ] **Step 5: Find other tests that pin the old text, then run the full suite and lint**

Run: `grep -rn "PKR [0-9]\|EUR [0-9]\|GBP [0-9]" services/api/tests` and update only assertions on the brief summary (not the what-if text or bills).
Then: `make test-py` and `uv run --project services/api ruff check services/ && uv run --project services/api ruff format --check services/`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add services/api/src/services/brief.py services/api/tests/
git commit -m "fix(brief): format summary amounts like the owner app; margin % to one decimal

The old test pinned 'PKR 12345.67'; the spec changes the summary to the
owner app's format ('Rs 12,346'), so the assertion moves with it."
```

---

### Task 3: Venue-neutral mock brief text

The mock returns "Expected busy Saturday. Consider featuring pasta specials." for every daily brief, so a Pakistani venue's Service report talks about pasta. Only `summary` reaches the app (`narrative.py` reads `.get("summary")`), and it must contain no numbers so it passes the number check.

**Files:**
- Modify: `services/inference/mock/src/canned.py:22`

- [ ] **Step 1: Replace the line**

```python
    "summary": "Steady trade expected. Keep prep in line with the forecast and watch the slowest dishes.",
```

- [ ] **Step 2: Check nothing else depends on the old text**

Run: `grep -rn "pasta specials" services/ apps/ e2e/ packages/ --include=*.py --include=*.ts --include=*.tsx`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add services/inference/mock/src/canned.py
git commit -m "fix(mock): venue-neutral daily brief text that names no dish"
```

---

### Task 4: Short order reference for guests

**Files:**
- Modify: `apps/guest-web/src/lib/ordering.ts`
- Test: `apps/guest-web/src/lib/ordering.test.ts`
- Modify: `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx:191`

- [ ] **Step 1: Write the failing test**

Add `orderRef` to the existing import from `./ordering` at the top of `apps/guest-web/src/lib/ordering.test.ts`, then append:

```ts
describe("orderRef", () => {
  it("shows the first six characters, upper case, after #", () => {
    expect(orderRef("3f9a1c2e-7b44-4d1e-9a0b-1234567890ab")).toBe("#3F9A1C");
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `pnpm --filter guest-web exec vitest run src/lib/ordering.test.ts`
Expected: FAIL, because `orderRef` is not exported.

- [ ] **Step 3: Add the helper**

Append to `apps/guest-web/src/lib/ordering.ts`:

```ts
/** Short reference a guest can read out: "#3F9A1C". The full id stays in the URL and API. */
export function orderRef(id: string): string {
  return `#${id.slice(0, 6).toUpperCase()}`;
}
```

- [ ] **Step 4: Run the test to see it pass**

Run: `pnpm --filter guest-web exec vitest run src/lib/ordering.test.ts`
Expected: PASS.

- [ ] **Step 5: Use it on the order page**

In `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`, import `orderRef` from the ordering lib (follow the file's existing import style), and replace:

```tsx
              <p className="text-xs text-ink-muted font-mono mt-0.5 break-all">ID: {id}</p>
```

with:

```tsx
              <p className="text-xs text-ink-muted font-mono mt-0.5">{orderRef(id)}</p>
```

- [ ] **Step 6: Check no e2e test reads the old "ID:" line**

Run: `grep -rn "ID: " e2e/`
Expected: no matches. If one exists, change it to the `#XXXXXX` form.

- [ ] **Step 7: Type-check and run the app's tests**

Run: `pnpm --filter guest-web exec tsc --noEmit && pnpm --filter guest-web test`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add apps/guest-web/src/lib/ordering.ts apps/guest-web/src/lib/ordering.test.ts "apps/guest-web/src/app/[lang]/orders/[id]/page.tsx"
git commit -m "fix(guest): show a short #XXXXXX order reference instead of the full id"
```

---

### Task 5: The assistant button never covers the last price

On phones the assistant button (`apps/guest-web/src/components/chat-panel.tsx`) sits at `bottom-20` (5 rem) and is about 2.5 rem tall, so its top is at about 7.5 rem. When the order bar shows, it is raised to `bottom-64` (16 rem) and its top is at about 18.5 rem. The menu leaves only `pb-28` (7 rem) and `pb-56` (14 rem), so the last dish's price, on the right edge under the button, is covered. Make the padding taller than the button's top in both states.

**Files:**
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx:455`

- [ ] **Step 1: Change the padding**

Put this comment on the line above `return (` in the menu page component:

```tsx
  // Bottom padding clears the assistant button (chat-panel.tsx: bottom-20, or bottom-64 above the order bar).
```

and replace:

```tsx
    <div className={`min-h-screen bg-paper text-ink ${barText ? "pb-56" : "pb-28"}`}>
```

with:

```tsx
    <div className={`min-h-screen bg-paper text-ink ${barText ? "pb-80" : "pb-36"}`}>
```

(`pb-36` = 9 rem > 7.5 rem; `pb-80` = 20 rem > 18.5 rem.)

- [ ] **Step 2: Check it in the browser**

Start the stack with `LLM_PROVIDER=mock DEMO_MODE=true make up`, open a guest menu at 375 × 812, scroll to the bottom with and without a dish in the cart, and confirm the last dish's price is fully visible above the assistant button.

- [ ] **Step 3: Run the existing layout e2e test**

Run: `pnpm exec playwright test e2e/self-service.spec.ts -g "every screen fits"`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add "apps/guest-web/src/app/[lang]/menu/page.tsx"
git commit -m "fix(guest): menu bottom padding clears the assistant button"
```

---

### Task 6: Full check

- [ ] **Step 1:** Run `make ci`. Expected: lint, Python tests, TS tests and the branding check all pass.
- [ ] **Step 2:** With the stack up (`LLM_PROVIDER=mock DEMO_MODE=true make up`), run `pnpm exec playwright test e2e/self-service.spec.ts`. Expected: PASS, including the new "1 ORDER ACTIVE" line.
- [ ] **Step 3:** Open the owner brief for Angeethi House and confirm the summary shows amounts like `Rs 12,346` with a one-decimal margin %, and that the Service report mentions no pasta.

---

## Worst-case tests (added on review; part of each task, same commit)

**Task 1 — kitchen.** In `kitchen.test.ts` also assert:
- `activeLabel(100)` → `"100 ORDERS ACTIVE"`.
- `keepUnits("")` → `""`; `keepUnits("1kg")` unchanged (no space, nothing to join); `keepUnits("1 KG")` → `"1\u00a0KG"`.
- Words that merely start with a unit stay alone: `"10 lemons"`, `"2 grams of saffron"`, `"3 pcsx"` unchanged.
- Idempotent: `keepUnits(keepUnits("1 kg")) === keepUnits("1 kg")`.
- Several in one string: `"1 kg + 2 kg"` → both joined.

**Task 2 — brief money.** In `test_analytics_pure.py` also assert:
- `fmt_money("PKR", 0)` → `"Rs 0"`; `fmt_money("PKR", -0.4)` → `"Rs 0"` (no `-Rs 0`); `fmt_money("EUR", -0.001)` → `"€0.00"`.
- `fmt_money("PKR", Decimal("2527.00"))` → `"Rs 2,527"` (Decimal input).
- `fmt_money("GBP", 1_234_567_890.5)` → `"£1,234,567,890.50"`.
- Half values stay grounded: a PKR summary with `revenue=12344.5`, `aov=0.5`, a negative `contribution_margin=-500.25` and `margin_pct=-12.35` passes `numbers_grounded`, shows `-Rs 500` and `-12.3%` or `-12.4%` as Python's `round` gives, and never prints `-0`.
  Use Python's `round` (not half-up) so the text matches the number check; add the comment
  `# shortcut: Python rounds .5 to even, so a .5 rupee can differ by 1 from the UI; switch both this and narrative.numbers_grounded to half-up if it matters.`
- Unknown currency `"XYZ"` → `"XYZ 1.50"`.
- Summary with `actions` whose `estimated_impact_per_week` is `None` for every action: no "Top action" sentence.

**Task 3 — mock text.** After the change run
`uv run --project services/api python -c "import ast,re,pathlib; t=pathlib.Path('services/inference/mock/src/canned.py').read_text(encoding='utf-8'); s=re.search(r'\"summary\": \"([^\"]*)\"', t).group(1); assert not re.search(r'\d', s), s; assert 'pasta' not in s.lower(); print('ok')"`
Expected: `ok` (no digits, so it always passes the number check; no dish).

**Task 4 — order ref.** In `ordering.test.ts` also assert:
- `orderRef("ab")` → `"#AB"` (short id, no throw); `orderRef("")` → `"#"`.
- An already upper-case id gives the same result as lower-case.
- Two UUIDs differing only after character 6 give the same ref (documents the limit; the full id stays in the URL).

**Task 5 — assistant button.** Add a Playwright test in `e2e/self-service.spec.ts` (or the file that already opens a guest menu; follow its helpers) at viewport 375 × 812:
- Scroll the menu to the bottom; the last dish's price element's bounding box does not intersect the assistant button's bounding box.
- Add a dish so the order bar shows, scroll to the bottom again, assert the same.
- Repeat at 320 × 568 (smallest common phone).
