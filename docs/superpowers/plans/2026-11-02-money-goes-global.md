# Money Goes Global Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bill venues in Pakistan (tax on top), the UK and Dubai (VAT inside the menu price) correctly from data, with an optional, untaxed service charge where the jurisdiction allows it, and VAT-free sales figures in reports.

**Architecture:** Per-jurisdiction rules move into `data/tax_jurisdictions.json` beside the dated rates in `data/tax_rates.json`. One pure function, `charge_for()` in `src/services/tax.py`, returns rate, tax and total for every caller (previews, guest claim, settle, simulator). Bills snapshot `tax_pricing` and the service charge. Analytics divide order-line money by `1 + tax_rate` from the settled bill's own snapshot when that bill was VAT-inclusive.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, Postgres 16, pytest (in Docker), Next.js 15, Vitest, pnpm, `openapi-typescript` client in `packages/api-client`.

Spec: `docs/superpowers/specs/2026-11-02-money-goes-global-design.md`.

---

## Ground rules for every task

- Branch `feat/money-goes-global`. Small commits, one logical change each. End every commit message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never read or print `.env`. Use `LLM_PROVIDER=mock` for any stack run.
- Python tests run in Docker:
  `docker compose build api-test && docker compose run --rm api-test pytest -q <path>`.
  Lint: `docker compose run --rm api-test ruff check src tests && docker compose run --rm api-test ruff format --check src tests`.
- TS tests: `pnpm --filter guest-web exec vitest run`, `pnpm --filter owner-web exec vitest run`,
  `pnpm --filter ui exec vitest run`; types: `pnpm --filter <app> exec tsc --noEmit`.
- Async relationships are `lazy="raise"`: every query is explicit.
- Never weaken a test. If an existing test's expectation must change, say why in the commit.
- Pakistan behaviour must not change: every existing test under `services/api/tests` keeps passing.

## File map

| File | Responsibility |
|---|---|
| `data/tax_jurisdictions.json` (new) | Per-jurisdiction rules: name, currency, pricing, rounding, methods, service charge |
| `data/tax_rates.json` | Dated rates; gains GB and AE-DU (`payment_class: "any"`) |
| `services/api/src/services/tax.py` | Loaders, `Jurisdiction`, `Charge`, `charge_for`, `tax_for`, `service_charge_for`, `check_venue_tax`, helpers |
| `services/api/alembic/versions/0020_money_goes_global.py` (new) | New columns and backfill |
| `services/api/src/models/restaurant.py`, `bill.py` | New columns |
| `services/api/src/services/bills.py` | Previews, method previews, settle with service charge and method check |
| `services/api/src/schemas/bills.py`, `payments.py`, `guest.py`, `owner.py` | API fields |
| `services/api/src/routers/bills.py`, `guest.py`, `owner.py` | Wire the fields |
| `services/api/src/services/simulator.py` | Simulated bills via `charge_for`, venue methods only |
| `services/api/src/services/analytics.py`, `brief.py` | Sales excluding VAT, service-charge figure, flags |
| `scripts/seed.py`, `scripts/admin.py` | Refuse a venue whose jurisdiction and currency disagree |
| `packages/api-client` | Regenerated types |
| `apps/guest-web/src/lib/pay.ts`, `components/PaySheet.tsx`, `app/[lang]/menu/page.tsx`, `i18n/en.ts`, `i18n/it.ts` | Guest screens |
| `apps/owner-web/src/lib/bill.ts`, `app/(dashboard)/bills/page.tsx`, `app/(dashboard)/tables/page.tsx`, `app/(dashboard)/brief/page.tsx`, `lib/analytics.ts` | Staff and owner screens |
| `README.md`, `docs/architecture.md`, `docs/analytics.md` | Describe what is built |

---

### Task 1: Jurisdiction rules data and loader

**Files:**
- Create: `data/tax_jurisdictions.json`
- Modify: `data/tax_rates.json`
- Modify: `services/api/src/services/tax.py`
- Modify: `services/api/src/config.py` (one optional setting)
- Test: `services/api/tests/test_tax.py`

- [ ] **Step 1: Write the data**

`data/tax_jurisdictions.json`:

```json
{
  "PB": {"name": "Punjab, Pakistan", "currency": "PKR", "pricing": "on_top", "rounding": "1",
         "methods": ["cash", "card", "wallet", "raast", "bank_transfer"], "service_charge": null},
  "ICT": {"name": "Islamabad, Pakistan", "currency": "PKR", "pricing": "on_top", "rounding": "1",
          "methods": ["cash", "card", "wallet", "raast", "bank_transfer"], "service_charge": null},
  "GB": {"name": "United Kingdom", "currency": "GBP", "pricing": "included", "rounding": "0.01",
         "methods": ["cash", "card"], "service_charge": "optional_outside_tax"},
  "AE-DU": {"name": "Dubai, UAE", "currency": "AED", "pricing": "included", "rounding": "0.01",
            "methods": ["cash", "card"], "service_charge": null}
}
```

Append to the list in `data/tax_rates.json` (keep the existing six entries unchanged):

```json
  {"jurisdiction": "GB", "payment_class": "any", "rate": "0.20", "effective_from": "2011-01-04",
   "source": "HMRC VAT Notice 709/1 (catering): food and drink for consumption on the premises is standard-rated; standard rate 20% since 4 January 2011"},
  {"jurisdiction": "AE-DU", "payment_class": "any", "rate": "0.05", "effective_from": "2018-01-01",
   "source": "UAE Federal Decree-Law No. 8 of 2017 on VAT, Art. 3 (5% standard rate) and Art. 38 (advertised prices include the tax)"}
```

- [ ] **Step 2: Write the failing tests** (append to `services/api/tests/test_tax.py`)

```python
import json

from src.services.tax import (
    Jurisdiction,
    default_jurisdictions,
    load_jurisdictions,
)


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_shipped_jurisdictions_load_and_match_rates():
    js = default_jurisdictions()
    assert js["GB"] == Jurisdiction(
        code="GB",
        name="United Kingdom",
        currency="GBP",
        pricing="included",
        rounding=Decimal("0.01"),
        methods=("cash", "card"),
        service_charge="optional_outside_tax",
    )
    assert js["PB"].pricing == "on_top" and js["PB"].rounding == Decimal("1")
    assert js["AE-DU"].service_charge is None


GOOD = {"name": "X", "currency": "GBP", "pricing": "included", "rounding": "0.01",
        "methods": ["cash"], "service_charge": None}


@pytest.mark.parametrize(
    "patch",
    [
        {"pricing": "sometimes"},
        {"rounding": "0"},
        {"rounding": "-1"},
        {"methods": []},
        {"methods": ["cash", "cheque"]},
        {"service_charge": "compulsory"},
        {"currency": ""},
    ],
)
def test_bad_jurisdiction_refused(tmp_path, patch):
    with pytest.raises(TaxRateError):
        load_jurisdictions(_write(tmp_path, "j.json", {"XX": {**GOOD, **patch}}))


def test_rate_without_jurisdiction_refused(tmp_path):
    from src.services.tax import check_rates_against

    rates = [TaxRate("ZZ", "any", Decimal("0.1"), JULY, "s")]
    with pytest.raises(TaxRateError, match="ZZ"):
        check_rates_against(rates, {"XX": Jurisdiction("XX", "X", "GBP", "included",
                                                       Decimal("0.01"), ("cash",), None)})


def test_any_and_split_rates_cannot_mix(tmp_path):
    from src.services.tax import check_rates_against

    j = {"XX": Jurisdiction("XX", "X", "GBP", "included", Decimal("0.01"), ("cash",), None)}
    rates = [
        TaxRate("XX", "any", Decimal("0.2"), JULY, "s"),
        TaxRate("XX", "standard", Decimal("0.2"), JULY, "s"),
    ]
    with pytest.raises(TaxRateError, match="mixes"):
        check_rates_against(rates, j)


def test_any_payment_class_accepted_by_rate_loader(tmp_path):
    rates = load_rates(_write(tmp_path, "r.json", [
        {"jurisdiction": "GB", "payment_class": "any", "rate": "0.20",
         "effective_from": "2011-01-04", "source": "s"}]))
    assert rates[0].payment_class == "any"
```

- [ ] **Step 3: Run to confirm failure**

Run: `docker compose build api-test && docker compose run --rm api-test pytest -q tests/test_tax.py`
Expected: FAIL with `ImportError: cannot import name 'Jurisdiction'`.

- [ ] **Step 4: Implement in `services/api/src/services/tax.py`**

Change the payment-class check in `load_rates` to accept `"any"`:

```python
        if r.payment_class not in ("standard", "digital", "any"):
            raise TaxRateError(f"Unknown payment class {r.payment_class!r}")
```

Generalise `_default_path` to take the file name, and add the jurisdiction loader after `default_rates`:

```python
def _data_path(name: str, override: str | None) -> Path:
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    # /app/data in the container (parents[2]), <repo>/data in a checkout (parents[4]);
    # slicing never raises when the path is shorter than expected.
    for base in here.parents[2:5:2]:
        candidate = base / "data" / name
        if candidate.is_file():
            return candidate
    raise TaxRateError(f"data/{name} not found")


def _default_path() -> Path:
    return _data_path("tax_rates.json", settings.tax_rates_path)


Pricing = Literal["on_top", "included"]


@dataclass(frozen=True)
class Jurisdiction:
    code: str
    name: str
    currency: str
    pricing: Pricing
    rounding: Decimal  # every tax, service and total amount rounds half up to this unit
    methods: tuple[str, ...]
    service_charge: Literal["optional_outside_tax"] | None


def load_jurisdictions(path: Path | None = None) -> dict[str, Jurisdiction]:
    try:
        raw = json.loads(
            (path or _data_path("tax_jurisdictions.json", settings.tax_jurisdictions_path))
            .read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as e:
        raise TaxRateError(f"Cannot read tax jurisdictions: {e}") from e
    if not isinstance(raw, dict) or not raw:
        raise TaxRateError("Tax jurisdictions file must be a non-empty object")
    out: dict[str, Jurisdiction] = {}
    for code, e in raw.items():
        try:
            j = Jurisdiction(
                code=str(code),
                name=str(e["name"]),
                currency=str(e["currency"]),
                pricing=e["pricing"],
                rounding=Decimal(str(e["rounding"])),
                methods=tuple(e["methods"]),
                service_charge=e["service_charge"],
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as err:
            raise TaxRateError(f"Bad jurisdiction {code!r}: {err}") from err
        if not j.code.strip() or not j.name.strip() or not j.currency.strip():
            raise TaxRateError(f"Bad jurisdiction {code!r}: code, name and currency required")
        if j.pricing not in ("on_top", "included"):
            raise TaxRateError(f"Bad jurisdiction {code!r}: unknown pricing {j.pricing!r}")
        if not j.rounding.is_finite() or j.rounding <= 0:
            raise TaxRateError(f"Bad jurisdiction {code!r}: rounding must be positive")
        if not j.methods or any(m not in PAYMENT_METHODS for m in j.methods):
            raise TaxRateError(f"Bad jurisdiction {code!r}: methods {j.methods!r}")
        if j.service_charge not in (None, "optional_outside_tax"):
            raise TaxRateError(f"Bad jurisdiction {code!r}: service_charge {j.service_charge!r}")
        out[j.code] = j
    return out


def check_rates_against(
    rates: tuple[TaxRate, ...] | list[TaxRate], jurisdictions: dict[str, Jurisdiction]
) -> None:
    """Every rate names a known jurisdiction; no jurisdiction mixes "any" with a split."""
    classes: dict[str, set[str]] = {}
    for r in rates:
        if r.jurisdiction not in jurisdictions:
            raise TaxRateError(f"Rate for unknown jurisdiction {r.jurisdiction!r}")
        classes.setdefault(r.jurisdiction, set()).add(r.payment_class)
    for code, cls in classes.items():
        if "any" in cls and len(cls) > 1:
            raise TaxRateError(f"Jurisdiction {code!r} mixes 'any' with standard/digital rates")


@lru_cache(maxsize=1)
def default_jurisdictions() -> dict[str, Jurisdiction]:
    js = load_jurisdictions()
    check_rates_against(default_rates(), js)
    return js
```

Add to `services/api/src/config.py` `Settings`, next to `tax_rates_path`:

```python
    tax_jurisdictions_path: str | None = None
```

- [ ] **Step 5: Run the tests**

Run: `docker compose run --rm api-test pytest -q tests/test_tax.py`
Expected: PASS (old and new tests).

- [ ] **Step 6: Commit**

```bash
git add data/tax_jurisdictions.json data/tax_rates.json services/api/src/services/tax.py services/api/src/config.py services/api/tests/test_tax.py
git commit -m "feat(api): per-jurisdiction tax rules as data, with UK and Dubai VAT rates"
```

---

### Task 2: `charge_for`: tax on top or included, rounded per jurisdiction

**Files:**
- Modify: `services/api/src/services/tax.py`
- Test: `services/api/tests/test_tax.py`

- [ ] **Step 1: Write the failing tests**

```python
import random

from src.services.tax import Charge, charge_for

NOV = date(2026, 11, 2)


@pytest.mark.parametrize(
    ("jur", "method", "subtotal", "rate", "tax", "total"),
    [
        ("GB", "card", "24.00", "0.20", "4.00", "24.00"),
        ("GB", "cash", "10.99", "0.20", "1.83", "10.99"),  # 1.8316… -> 1.83
        ("AE-DU", "card", "105.00", "0.05", "5.00", "105.00"),
        ("PB", "cash", "5490.00", "0.16", "878.00", "6368.00"),  # unchanged Pakistan maths
        ("ICT", "wallet", "2310.00", "0.05", "116.00", "2426.00"),
    ],
)
def test_charge_for(jur, method, subtotal, rate, tax, total):
    on = NOV if jur in ("GB", "AE-DU") else JULY
    c = charge_for(jur, method, on, Decimal(subtotal))
    assert c == Charge(Decimal(rate), Decimal(tax), Decimal(total),
                       "included" if jur in ("GB", "AE-DU") else "on_top")


def test_included_vat_always_adds_up():
    rng = random.Random(7)
    for _ in range(2000):
        sub = Decimal(rng.randint(1, 500_000)) / 100
        for jur in ("GB", "AE-DU"):
            c = charge_for(jur, "card", NOV, sub)
            assert c.total == sub  # the guest pays the menu price
            assert (c.total - c.tax) + c.tax == c.total
            assert c.tax == (sub * c.rate / (1 + c.rate)).quantize(Decimal("0.01"), "ROUND_HALF_UP")


def test_method_not_accepted_in_jurisdiction():
    with pytest.raises(TaxRateError, match="not accepted"):
        charge_for("GB", "raast", NOV, Decimal("10"))


def test_unknown_jurisdiction():
    with pytest.raises(TaxRateError):
        charge_for("SD", "cash", NOV, Decimal("10"))


def test_tax_for_keeps_its_shape():
    assert tax_for("GB", "card", NOV, Decimal("24.00")) == (Decimal("0.20"), Decimal("4.00"))
```

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_tax.py`
Expected: FAIL with `ImportError: cannot import name 'Charge'`.

- [ ] **Step 3: Implement** (replace `tax_for` in `tax.py`)

```python
CENTS = Decimal("0.01")


def round_money(amount: Decimal, unit: Decimal) -> Decimal:
    """Half up to the jurisdiction's money unit, stored with two decimals."""
    return ((amount / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit).quantize(CENTS)


@dataclass(frozen=True)
class Charge:
    rate: Decimal
    tax: Decimal  # on_top: added to the subtotal; included: the part of the total that is tax
    total: Decimal  # what the guest pays before any optional service charge
    pricing: Pricing


def jurisdiction_of(code: str | None) -> Jurisdiction | None:
    return default_jurisdictions().get(code or "")


def charge_for(
    jurisdiction: str,
    method: str,
    on_date: date,
    subtotal: Decimal,
    rates: tuple[TaxRate, ...] | list[TaxRate] | None = None,
) -> Charge:
    """Rate, tax and total for a bill of menu-price lines settled on on_date."""
    j = jurisdiction_of(jurisdiction)
    if j is None:
        raise TaxRateError(f"Unknown tax jurisdiction {jurisdiction!r}")
    if method not in j.methods:
        raise TaxRateError(f"Payment method {method!r} is not accepted in {jurisdiction}")
    cls = payment_class(method)
    candidates = [
        r
        for r in (rates if rates is not None else default_rates())
        if r.jurisdiction == jurisdiction
        and r.payment_class in (cls, "any")
        and r.effective_from <= on_date
    ]
    if not candidates:
        raise TaxRateError(f"No tax rate configured for {jurisdiction}/{cls} on {on_date}")
    rate = max(candidates, key=lambda r: r.effective_from).rate
    if j.pricing == "on_top":
        tax = round_money(subtotal * rate, j.rounding)
        return Charge(rate, tax, subtotal + tax, "on_top")
    tax = round_money(subtotal * rate / (1 + rate), j.rounding)
    return Charge(rate, tax, subtotal, "included")


def tax_for(
    jurisdiction: str,
    method: str,
    on_date: date,
    subtotal: Decimal,
    rates: tuple[TaxRate, ...] | list[TaxRate] | None = None,
) -> tuple[Decimal, Decimal]:
    """(rate, tax amount) for a bill settled on on_date; see charge_for for the total."""
    c = charge_for(jurisdiction, method, on_date, subtotal, rates)
    return c.rate, c.tax


def methods_for(jurisdiction: str | None) -> tuple[str, ...]:
    """Methods a venue may settle with; all of them when it has no jurisdiction (no tax)."""
    j = jurisdiction_of(jurisdiction)
    return j.methods if j else PAYMENT_METHODS


def splits_by_method(jurisdiction: str | None) -> bool:
    """True where cash and digital payments carry different rates (Pakistan)."""
    return any(
        r.jurisdiction == jurisdiction and r.payment_class != "any" for r in default_rates()
    )


def price_tax_factor(jurisdiction: str | None, on_date: date) -> Decimal:
    """Menu price / factor = price excluding VAT; 1 where tax sits on top or is unknown."""
    j = jurisdiction_of(jurisdiction)
    if j is None or j.pricing != "included":
        return Decimal(1)
    try:
        return 1 + charge_for(j.code, j.methods[0], on_date, Decimal(0)).rate
    except TaxRateError:
        return Decimal(1)
```

Existing tests that pass their own `rates` list for `PB` still work: `PB` is in the shipped jurisdictions and accepts `card`/`cash`.

- [ ] **Step 4: Run all tax and money tests**

Run: `docker compose run --rm api-test pytest -q tests/test_tax.py tests/test_money_agreement.py tests/test_bills.py tests/test_settle_safeguards.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/services/tax.py services/api/tests/test_tax.py
git commit -m "feat(api): charge_for works out tax on top or VAT included, rounded per jurisdiction"
```

---

### Task 3: Migration 0020 and model columns

**Files:**
- Create: `services/api/alembic/versions/0020_money_goes_global.py`
- Modify: `services/api/src/models/restaurant.py`, `services/api/src/models/bill.py`
- Test: `services/api/tests/test_schema_constraints.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_schema_constraints.py`, reusing that file's `db_session` fixture style)

```python
async def test_service_charge_rate_bounds(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await db_session.execute(text(
            "INSERT INTO restaurant (name, slug, service_charge_rate) "
            "VALUES ('x', 'sc-bound', 0.25)"))
    await db_session.rollback()


async def test_bill_tax_pricing_values(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    rid = (await db_session.execute(text(
        "INSERT INTO restaurant (name, slug) VALUES ('x', 'tp-check') RETURNING id"))).scalar_one()
    with pytest.raises(IntegrityError):
        await db_session.execute(text(
            "INSERT INTO bills (restaurant_id, status, tax_pricing) "
            "VALUES (:r, 'open', 'sometimes')"), {"r": rid})
    await db_session.rollback()
```

(If `bills` has other NOT NULL columns without defaults, copy the insert columns from an existing raw-SQL bill insert in that file.)

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_schema_constraints.py -k "service_charge or tax_pricing"`
Expected: FAIL (`column "service_charge_rate" does not exist`).

- [ ] **Step 3: Write the migration** `services/api/alembic/versions/0020_money_goes_global.py`

```python
"""Per-country tax: bill pricing snapshot, optional service charge.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant",
        sa.Column("service_charge_rate", sa.Numeric(4, 4), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "chk_restaurant_service_charge_rate",
        "restaurant",
        "service_charge_rate >= 0 AND service_charge_rate <= 0.20",
    )
    op.add_column("bills", sa.Column("tax_pricing", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_bills_tax_pricing", "bills", "tax_pricing IN ('on_top', 'included')"
    )
    op.add_column(
        "bills",
        sa.Column("service_charge_rate", sa.Numeric(4, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "bills",
        sa.Column("service_charge_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "bills",
        sa.Column(
            "claimed_service_included", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # Every bill so far was Pakistani: tax on top.
    op.execute("UPDATE bills SET tax_pricing = 'on_top' WHERE tax_rate IS NOT NULL")


def downgrade() -> None:
    op.drop_column("bills", "claimed_service_included")
    op.drop_column("bills", "service_charge_amount")
    op.drop_column("bills", "service_charge_rate")
    op.drop_constraint("chk_bills_tax_pricing", "bills", type_="check")
    op.drop_column("bills", "tax_pricing")
    op.drop_constraint("chk_restaurant_service_charge_rate", "restaurant", type_="check")
    op.drop_column("restaurant", "service_charge_rate")
```

Check `0019_order_void_kind.py` for the exact revision id string and copy its style (`revision = "0019"` or a longer id); set `down_revision` to that value.

- [ ] **Step 4: Model columns**

`src/models/restaurant.py`, after `first_order_cap_multiplier`:

```python
    # Optional service charge on table bills, 0-0.20; only where the jurisdiction allows it.
    service_charge_rate: Mapped[Decimal] = mapped_column(
        Numeric(4, 4), nullable=False, server_default=text("0")
    )
```

and add `CheckConstraint("service_charge_rate >= 0 AND service_charge_rate <= 0.20", name="chk_restaurant_service_charge_rate")` to `__table_args__`.

`src/models/bill.py`, after `tax_rate`:

```python
    tax_pricing: Mapped[str | None] = mapped_column(Text, nullable=True)  # on_top | included
    service_charge_rate: Mapped[Decimal] = mapped_column(
        Numeric(4, 4), nullable=False, server_default=text("0")
    )
    service_charge_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    # The guest's choice on the optional service charge, with their payment claim.
    claimed_service_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
```

and `CheckConstraint("tax_pricing IN ('on_top', 'included')", name="chk_bills_tax_pricing")` in `__table_args__`. Import `Boolean`/`Text` if missing.

- [ ] **Step 5: Run tests and the migration round trip**

Run: `docker compose run --rm api-test pytest -q tests/test_schema_constraints.py`
Then: `docker compose run --rm api-test sh -c "alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check"`
Expected: PASS; `No new upgrade operations detected.`

- [ ] **Step 6: Commit**

```bash
git add services/api/alembic/versions/0020_money_goes_global.py services/api/src/models/restaurant.py services/api/src/models/bill.py services/api/tests/test_schema_constraints.py
git commit -m "feat(api): bills snapshot tax pricing and service charge; venue service-charge rate"
```

---

### Task 4: Venue jurisdiction and currency must agree

**Files:**
- Modify: `services/api/src/services/tax.py`, `scripts/seed.py`, `scripts/admin.py`
- Test: `services/api/tests/test_tax.py`, `services/api/tests/test_admin.py`

- [ ] **Step 1: Failing tests**

`tests/test_tax.py`:

```python
from src.services.tax import check_venue_tax


def test_check_venue_tax():
    check_venue_tax("GB", "GBP")
    check_venue_tax(None, "EUR")  # no tax configured: allowed, as today
    with pytest.raises(TaxRateError, match="currency"):
        check_venue_tax("GB", "PKR")
    with pytest.raises(TaxRateError, match="Unknown"):
        check_venue_tax("XX", "GBP")
```

`tests/test_admin.py`: copy the existing create-venue test there and call the creator with `jurisdiction="GB", currency="PKR"`; assert it raises `TaxRateError` (or `SystemExit`, whichever the admin script uses for refusals; read `scripts/admin.py` around line 64 first).

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_tax.py tests/test_admin.py`
Expected: FAIL (`cannot import name 'check_venue_tax'`).

- [ ] **Step 3: Implement**

`tax.py`:

```python
def check_venue_tax(jurisdiction: str | None, currency: str) -> None:
    """A venue's jurisdiction must exist and use the venue's currency."""
    if jurisdiction is None:
        return
    j = jurisdiction_of(jurisdiction)
    if j is None:
        raise TaxRateError(f"Unknown tax jurisdiction {jurisdiction!r}")
    if j.currency != currency:
        raise TaxRateError(
            f"{jurisdiction} bills in {j.currency}; the venue's currency is {currency}"
        )
```

`scripts/seed.py`: just before each place that assigns `tax_jurisdiction` (lines ~136 and ~153), call
`check_venue_tax(rest_data.get("tax_jurisdiction"), rest_data.get("currency", "EUR"))`.
`scripts/admin.py`: call `check_venue_tax(jurisdiction, currency)` before building the `Restaurant`.

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm api-test pytest -q tests/test_tax.py tests/test_admin.py tests/test_seed.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/services/tax.py scripts/seed.py scripts/admin.py services/api/tests/test_tax.py services/api/tests/test_admin.py
git commit -m "feat(api): refuse a venue whose tax jurisdiction bills in another currency"
```

---

### Task 5: Bills service: previews, service charge, settle

**Files:**
- Modify: `services/api/src/services/bills.py`, `services/api/src/schemas/bills.py`
- Modify: `services/api/src/services/tax.py` (service charge helper)
- Test: create `services/api/tests/test_global_bills.py`

- [ ] **Step 1: Shared fixtures and failing tests** — create `tests/test_global_bills.py`

```python
"""UK and Dubai bills: VAT inside the menu price, venue methods only, optional service charge."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select
from tests.helpers import approve_order, as_member, seat_table, settle
from tests.test_bills import _item, bill_id_of, guest

from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


async def _venue(db, jur, currency, tz, service="0"):
    r = Restaurant(
        name=f"{jur} Venue", slug=f"g-{uuid.uuid4().hex[:8]}", currency=currency, timezone=tz,
        languages=["en"], default_language="en", tax_jurisdiction=jur,
        service_charge_rate=Decimal(service),
    )
    db.add(r)
    await db.flush()
    t = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    dish = _item(r.id, "Pie", "12.00", 1)
    side = _item(r.id, "Chips", "4.50", 2)
    db.add_all([t, dish, side])
    await db.flush()
    s = GuestSession(restaurant_id=r.id, table_id=t.id, language="en",
                     expires_at=datetime.now(UTC) + timedelta(hours=2))
    db.add(s)
    await db.flush()
    return r, t, dish, side, s


@pytest_asyncio.fixture
async def uk(db_session):
    return await _venue(db_session, "GB", "GBP", "Europe/London", service="0.125")


@pytest_asyncio.fixture
async def dubai(db_session):
    return await _venue(db_session, "AE-DU", "AED", "Asia/Dubai")


async def _order(client, s, lines):
    await seat_table(s.table_id)
    guest(client, s)
    resp = await client.post("/api/orders", json={
        "idempotency_key": uuid.uuid4().hex,
        "items": [{"menu_item_id": str(i.id), "quantity": q} for i, q in lines],
        "acknowledge_allergen_risk": True,
    })
    assert resp.status_code == 201, resp.text
    await approve_order(resp.json()["id"])
    return uuid.UUID(resp.json()["id"])


async def test_uk_bill_includes_vat_and_offers_cash_and_card_only(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1), (side, 2)])  # 12 + 9 = 21.00
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{bill_id}")).json()
    assert [m["method"] for m in d["methods"]] == ["cash", "card"]
    card = next(m for m in d["methods"] if m["method"] == "card")
    assert (card["total"], card["tax_amount"], card["tax_included"]) == ("21.00", "3.50", True)
    assert (d["service_charge_rate"], d["service_charge_amount"]) == ("0.1250", "2.63")


async def test_uk_settle_with_and_without_service(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1), (side, 2)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await settle(client, r.slug, bill_id, "card", service_included=True)
    assert resp.status_code == 200, resp.text
    b = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    await db_session.refresh(b)
    assert (b.tax_pricing, b.tax_amount, b.service_charge_amount, b.total) == (
        "included", Decimal("3.50"), Decimal("2.63"), Decimal("23.63"))


async def test_uk_settle_without_service(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await settle(client, r.slug, bill_id, "cash")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == "12.00"
    assert resp.json()["service_charge_amount"] == "0.00"


async def test_uk_settle_refuses_a_mismatched_service_total(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(f"/api/restaurants/{r.slug}/bills/{bill_id}/settle", json={
        "payment_method": "card", "expected_method": "card",
        "expected_total": "12.00", "service_included": True})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Bill changed"


async def test_raast_refused_on_a_uk_bill(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(f"/api/restaurants/{r.slug}/bills/{bill_id}/settle", json={
        "payment_method": "raast", "expected_method": "raast",
        "expected_total": "12.00", "payment_reference": "R1"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Payment method not accepted here"


async def test_dubai_bill_no_service_and_vat_included(client, db_session, dubai):
    r, _, dish, _, s = dubai
    o = await _order(client, s, [(dish, 1)])  # 12.00 AED
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await settle(client, r.slug, bill_id, "card", service_included=True)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert (d["total"], d["tax_amount"], d["service_charge_amount"]) == ("12.00", "0.57", "0.00")
```

(If `as_member`'s signature differs, read `tests/helpers.py:45` and match it.)

Change `tests/helpers.py` `settle` so the expected total follows the service choice, as staff do:

```python
    body = {
        "payment_method": method,
        "expected_method": method,
        "expected_total": preview["total"] if preview else "0",
        **extra,
    }
    if preview and extra.get("service_included"):
        body["expected_total"] = str(
            Decimal(preview["total"]) + Decimal(detail.json()["service_charge_amount"])
        )
```

(add `from decimal import Decimal` to helpers).

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py`
Expected: FAIL (`KeyError: 'tax_included'` or 422 on settle).

- [ ] **Step 3: Service-charge helper in `tax.py`**

```python
def service_charge_for(
    jurisdiction: str | None, rate: Decimal, subtotal: Decimal, is_table: bool
) -> tuple[Decimal, Decimal]:
    """(rate, amount) of the optional service charge; (0, 0) where it does not apply."""
    j = jurisdiction_of(jurisdiction)
    if j is None or j.service_charge is None or not is_table or rate <= 0:
        return Decimal("0.0000"), Decimal("0.00")  # same scale as the stored columns
    return rate, round_money(subtotal * rate, j.rounding)
```

- [ ] **Step 4: Schemas** (`src/schemas/bills.py`)

```python
class TaxPreview(BaseModel):
    payment_class: Literal["standard", "digital"]
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    # True where the menu price already includes the tax (UK, UAE): total == subtotal.
    tax_included: bool = False


class PaymentClaim(BaseModel):
    method: str
    reference: str | None
    total: Decimal
    claimed_at: datetime
    service_included: bool = False
```

In `BillDetail` add:

```python
    tax_pricing: str | None
    # The optional service charge: the rate offered and its amount on this bill (open: live).
    service_charge_rate: Decimal
    service_charge_amount: Decimal
```

In `SettleBillRequest` add `service_included: bool = False`.

- [ ] **Step 5: `src/services/bills.py`**

Replace the `tax_for` import with
`from src.services.tax import CENTS, TaxRateError, charge_for, default_rates, methods_for, payment_class, service_charge_for`
(drop the local `CENTS = Decimal("0.01")` line; keep `PAYMENT_METHODS` import only if still used).

```python
def _preview(
    jurisdiction: str | None, method: str, subtotal: Decimal, on_date: date
) -> TaxPreview | None:
    try:
        c = charge_for(jurisdiction or "", method, on_date, subtotal, default_rates())
    except TaxRateError:
        return None
    return TaxPreview(
        payment_class=payment_class(method),
        tax_rate=c.rate,
        tax_amount=c.tax,
        total=c.total,
        tax_included=c.pricing == "included",
    )


def method_previews(
    jurisdiction: str | None, subtotal: Decimal, on_date: date
) -> list[MethodPreview]:
    """Tax and total for each method the venue accepts; methods without a rate are left out."""
    out = [method_preview(jurisdiction, m, subtotal, on_date) for m in methods_for(jurisdiction)]
    return [p for p in out if p is not None]


def bill_service(restaurant: Restaurant, bill: Bill, subtotal: Decimal) -> tuple[Decimal, Decimal]:
    """The optional service charge this bill would carry: table bills only."""
    return service_charge_for(
        restaurant.tax_jurisdiction,
        restaurant.service_charge_rate,
        subtotal,
        bill.table_id is not None,
    )


METHOD_REFUSED = "Payment method not accepted here"
```

`previews()` keeps calling `_preview(..., "cash", ...)` and `"card"`; both exist in every jurisdiction.

In `claim_of`, pass `service_included=bill.claimed_service_included`.

In `settle_bill`, add a `service_included: bool = False` parameter after `acknowledge_reused`, and replace the tax block:

```python
    if method not in methods_for(restaurant.tax_jurisdiction):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=METHOD_REFUSED
        )
    _, subtotal = bill_lines(orders)
    try:
        c = charge_for(
            restaurant.tax_jurisdiction or "",
            method,
            local_date(restaurant, now),
            subtotal,
            default_rates(),
        )
    except TaxRateError as e:
        logger.error("Bill %s not settled: %s", bill.id, e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No tax rate configured"
        ) from e
    sc_rate, sc_amount = bill_service(restaurant, bill, subtotal)
    if not service_included:
        sc_rate, sc_amount = Decimal(0), Decimal("0.00")
    if c.total + sc_amount != expected_total:
        raise BillChanged
```

Put the method check before `active_orders` so nothing is read for a refused method. Then where the bill is stamped:

```python
    bill.tax_rate = c.rate
    bill.tax_amount = c.tax
    bill.tax_pricing = c.pricing
    bill.service_charge_rate = sc_rate
    bill.service_charge_amount = sc_amount
    bill.total = c.total + sc_amount
```

- [ ] **Step 6: Wire `routers/bills.py`**

In `bill_detail`, after `methods = ...`:

```python
    if bill.status == "settled":
        sc_rate, sc_amount = bill.service_charge_rate, bill.service_charge_amount
    else:
        sc_rate, sc_amount = bill_service(restaurant, bill, subtotal)
```

The claim's amount due must count the service the guest chose:

```python
        current = next((m for m in methods if m.method == claim.method), None)
        due = (
            None
            if current is None
            else current.total + (sc_amount if claim.service_included else 0) - claim.total
        )
```

Pass `tax_pricing=bill.tax_pricing, service_charge_rate=sc_rate, service_charge_amount=sc_amount` to `BillDetail(...)`. In `settle`, pass `payload.service_included` to `settle_bill`. Import `bill_service` from `src.services.bills`. Add `"Payment method not accepted here"` to the 422 description of the settle route.

- [ ] **Step 7: Run tests**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py tests/test_bills.py tests/test_settle_safeguards.py tests/test_payment_claims.py tests/test_counter.py tests/test_money_agreement.py`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/api/src/services/bills.py services/api/src/services/tax.py services/api/src/schemas/bills.py services/api/src/routers/bills.py services/api/tests/test_global_bills.py services/api/tests/helpers.py
git commit -m "feat(api): UK and Dubai bills include VAT, accept the venue's methods, carry the optional service charge"
```

---

### Task 6: Guest bill, payment claim and menu notice

**Files:**
- Modify: `services/api/src/routers/guest.py`, `services/api/src/schemas/payments.py` (holds `GuestBillDetail` and `GuestPaymentRequest`; confirm with `grep -n "class GuestBillDetail\|class GuestPaymentRequest" services/api/src/schemas/*.py`), `services/api/src/schemas/guest.py`
- Test: `services/api/tests/test_global_bills.py`

- [ ] **Step 1: Failing tests** (append)

```python
async def test_guest_sees_vat_and_optional_service(client, db_session, uk):
    r, _, dish, side, s = uk
    await _order(client, s, [(dish, 1), (side, 2)])
    guest(client, s)
    b = (await client.get("/api/guest/bill")).json()
    assert [m["method"] for m in b["methods"]] == ["cash", "card"]
    assert b["methods"][0]["tax_included"] is True
    assert (b["service_charge_rate"], b["service_charge_amount"]) == ("0.1250", "2.63")


async def test_guest_claim_records_service_choice(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    guest(client, s)
    on = await client.post("/api/guest/bill/payment",
                           json={"method": "card", "reference": None, "service_included": True})
    assert on.status_code == 200, on.text
    assert on.json()["claim"]["total"] == "13.50"  # 12.00 + 12.5%
    off = await client.post("/api/guest/bill/payment",
                            json={"method": "card", "reference": None, "service_included": False})
    assert off.json()["claim"]["total"] == "12.00"
    assert off.json()["claim"]["service_included"] is False
    # Staff see the guest's latest choice and nothing still due.
    await as_member(client, db_session, r.id, "staff")
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{await bill_id_of(db_session, o)}")).json()
    assert d["claim"]["service_included"] is False
    assert d["amount_due_after_claim"] == "0.00"


async def test_guest_cannot_claim_raast_in_the_uk(client, db_session, uk):
    _, _, dish, _, s = uk
    await _order(client, s, [(dish, 1)])
    guest(client, s)
    resp = await client.post("/api/guest/bill/payment",
                             json={"method": "raast", "reference": "R1"})
    assert resp.status_code == 422


async def test_menu_shows_the_service_rate(client, db_session, uk, dubai):
    for (r, *_rest, s), rate in ((uk, "0.1250"), (dubai, "0.0000")):
        guest(client, s)
        menu = (await client.get("/api/guest/menu")).json()
        assert menu["restaurant"]["service_charge_rate"] == rate
```

(Confirm the guest menu path with `grep -n "response_model=GuestMenuResponse" -B3 services/api/src/routers/guest.py` and use it.)

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py -k guest or menu`
Expected: FAIL.

- [ ] **Step 3: Implement**

`GuestBillDetail`: add `service_charge_rate: Decimal` and `service_charge_amount: Decimal`.
`GuestPaymentRequest`: add `service_included: bool = False`.
`GuestMenuRestaurant` (`schemas/guest.py`): add `service_charge_rate: Decimal`.

`routers/guest.py`:
- in the menu route, build `GuestMenuRestaurant(id=..., name=..., currency=..., service_charge_rate=service_charge_for(restaurant.tax_jurisdiction, restaurant.service_charge_rate, Decimal(0), True)[0])`. The rate shows only where the jurisdiction allows it; counter phones see it too, so the notice wording says "table bills".
- in `_bill_detail`, compute `sc_rate, sc_amount = bill_service(restaurant, bill, subtotal) if is_open else (bill.service_charge_rate, bill.service_charge_amount)` and pass both.
- in `claim_payment`, refuse a method the venue does not accept before anything else:

```python
    if payload.method not in methods_for(restaurant.tax_jurisdiction):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=METHOD_REFUSED
        )
```

  (fetch `restaurant` before the `is_expired_unpaid` block so it is available), include the service choice in `changed`:

```python
    changed = (bill.claimed_method, bill.claimed_reference, bill.claimed_service_included) != (
        payload.method, payload.reference, payload.service_included
    )
```

  and when changed:

```python
        _, sc_amount = bill_service(restaurant, bill, subtotal)
        include = payload.service_included and sc_amount > 0
        bill.claimed_service_included = include
        bill.claimed_total = preview.total + (sc_amount if include else 0)
```

  Add `"service_included": include` to the audit payload and use `str(bill.claimed_total)` for its `"total"`.

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py tests/test_payment_claims.py tests/test_guest*.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/routers/guest.py services/api/src/schemas services/api/tests/test_global_bills.py
git commit -m "feat(api): guests see VAT included, choose the optional service, claim only venue methods"
```

---

### Task 7: Owner settings: service charge and tax rule

**Files:**
- Modify: `services/api/src/schemas/owner.py`, `services/api/src/routers/owner.py`
- Test: `services/api/tests/test_global_bills.py` (settings section)

- [ ] **Step 1: Failing tests**

```python
async def test_settings_service_charge(client, db_session, uk, dubai):
    r, *_ = uk
    await as_member(client, db_session, r.id, "owner")
    s = (await client.get(f"/api/restaurants/{r.slug}/settings")).json()
    assert s["tax_rule"] == {"name": "United Kingdom", "rate": "0.20", "pricing": "included"}
    assert (s["service_charge_allowed"], s["service_charge_rate"]) == (True, "0.1250")
    ok = await client.patch(f"/api/restaurants/{r.slug}/settings", json={"service_charge_rate": "0.10"})
    assert ok.status_code == 200 and ok.json()["service_charge_rate"] == "0.1000"
    high = await client.patch(f"/api/restaurants/{r.slug}/settings", json={"service_charge_rate": "0.25"})
    assert high.status_code == 422

    d, *_ = dubai
    await as_member(client, db_session, d.id, "owner")
    refused = await client.patch(f"/api/restaurants/{d.slug}/settings", json={"service_charge_rate": "0.10"})
    assert refused.status_code == 422
    assert refused.json()["detail"] == "An optional service charge is not offered in Dubai, UAE"
    assert (await client.get(f"/api/restaurants/{d.slug}/settings")).json()["service_charge_allowed"] is False
```

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py -k settings`
Expected: FAIL.

- [ ] **Step 3: Implement**

`schemas/owner.py`:

```python
class TaxRule(BaseModel):
    name: str
    rate: Decimal
    pricing: Literal["on_top", "included"]
```

`PatchSettingsRequest`: `service_charge_rate: Decimal | None = Field(default=None, ge=0, le=Decimal("0.20"), decimal_places=4)`.
`SettingsResponse`: add `service_charge_rate: Decimal`, `service_charge_allowed: bool`, `tax_rule: TaxRule | None`.

`routers/owner.py`: one helper used by both routes:

```python
def _settings_response(r: Restaurant) -> SettingsResponse:
    j = jurisdiction_of(r.tax_jurisdiction)
    rule = None
    if j is not None:
        try:
            rate = charge_for(j.code, j.methods[0], local_today(r), Decimal(0)).rate
            rule = TaxRule(name=j.name, rate=rate, pricing=j.pricing)
        except TaxRateError:
            rule = None
    return SettingsResponse(
        payment_details=r.payment_details,
        service_extra_label=r.service_extra_label,
        pickup_prefix=r.pickup_prefix,
        sitting_code_required=r.sitting_code_required,
        service_charge_rate=r.service_charge_rate,
        service_charge_allowed=j is not None and j.service_charge is not None,
        tax_rule=rule,
    )
```

(`local_today` is in `src/services/brief.py`; import it, or use `local_date(r, datetime.now(UTC))` from `src/services/bills.py`.) Note: `pricing` and its rate apply to Pakistan too, where `tax_rule.rate` is the cash rate; the Settings screen states that.

In `patch_settings`, before other changes:

```python
    if payload.service_charge_rate is not None:
        j = jurisdiction_of(restaurant.tax_jurisdiction)
        if payload.service_charge_rate > 0 and (j is None or j.service_charge is None):
            where = j.name if j else "this venue"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"An optional service charge is not offered in {where}",
            )
        restaurant.service_charge_rate = payload.service_charge_rate
```

Return `_settings_response(restaurant)` from both routes. Add an audit entry if `patch_settings` already writes one for other fields (follow the existing pattern).

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py tests/test_owner*.py tests/test_settings*.py`
Expected: PASS (skip patterns that match no files).

- [ ] **Step 5: Commit**

```bash
git add services/api/src/schemas/owner.py services/api/src/routers/owner.py services/api/tests/test_global_bills.py
git commit -m "feat(api): owners set the optional service charge where allowed and see the tax rule"
```

---

### Task 8: Simulator bills follow the venue's rules

**Files:**
- Modify: `services/api/src/services/simulator.py`
- Test: `services/api/tests/test_simulator_bills.py`

- [ ] **Step 1: Failing test** (append; copy the venue/run setup of the first test in that file, with `currency="GBP"`, `timezone="Europe/London"`, `tax_jurisdiction="GB"`)

```python
async def test_simulated_uk_bills_include_vat_and_use_cash_or_card(db_session, <same fixtures>):
    # ... run the simulator for the GB venue exactly like the existing PB test ...
    bills = (await db_session.execute(select(Bill).where(Bill.restaurant_id == r.id))).scalars().all()
    assert bills
    for b in bills:
        assert b.payment_method in ("cash", "card")
        assert b.tax_pricing == "included"
        assert b.total == b.subtotal
        assert b.tax_amount == (b.subtotal * b.tax_rate / (1 + b.tax_rate)).quantize(Decimal("0.01"), "ROUND_HALF_UP")
```

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_simulator_bills.py`
Expected: FAIL (`wallet`/`raast` methods, or `tax_pricing` is None).

- [ ] **Step 3: Implement**

Where the simulator picks `methods`/`method_p` (around line 199), keep only methods the venue accepts and renormalise:

```python
    allowed = set(methods_for(restaurant.tax_jurisdiction))
    pairs = [(m, p) for m, p in zip(methods, method_p, strict=True) if m in allowed]
    methods = [m for m, _ in pairs]
    weight = sum(p for _, p in pairs)
    method_p = [p / weight for _, p in pairs]
```

(Read lines 60-120 and 180-200 first; apply this where `methods`/`method_p` are built, before the loop.)

In `_simulated_bill`:

```python
    try:
        c = charge_for(
            restaurant.tax_jurisdiction or "",
            so.payment_method,
            settled_at.astimezone(tz).date(),
            subtotal,
            rates,
        )
    except TaxRateError:
        return None
```

and stamp `tax_rate=c.rate, tax_amount=c.tax, tax_pricing=c.pricing, total=c.total`. Simulated bills have no table, so no service charge.

- [ ] **Step 4: Run tests**

Run: `docker compose run --rm api-test pytest -q tests/test_simulator_bills.py tests/test_simulator*.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/services/simulator.py services/api/tests/test_simulator_bills.py
git commit -m "feat(api): simulated bills follow the venue's tax pricing and payment methods"
```

---

### Task 9: Reports exclude VAT; service-charge figure; brief flags

**Files:**
- Modify: `services/api/src/services/analytics.py`, `services/api/src/services/brief.py`, `services/api/src/schemas/owner.py`
- Test: `services/api/tests/test_analytics_api.py`, `services/api/tests/test_global_bills.py`

- [ ] **Step 1: Failing tests** (append to `tests/test_global_bills.py`)

```python
from src.services import analytics
from src.services.brief import local_today


async def test_uk_revenue_excludes_vat_and_service(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1), (side, 2)])  # 21.00 incl. VAT
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    assert (await settle(client, r.slug, bill_id, "card", service_included=True)).status_code == 200
    today = local_today(r)
    w = analytics.Window(r.id, r.timezone, today, today + timedelta(days=1))
    k = await analytics.kpis(db_session, w)
    assert k["revenue"] == 17.5  # 21.00 / 1.20
    # Unit cost is 1.00 per item in _item: 3 items.
    assert k["contribution_margin"] == 14.5
    assert await analytics.service_charge_collected(db_session, w) == Decimal("2.63")
```

In `tests/test_analytics_api.py`, add one assertion to an existing PB kpis test that the figures are unchanged (they must be: PB bills are `on_top`).

- [ ] **Step 2: Run to confirm failure**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py -k revenue`
Expected: FAIL (`revenue == 21.0`).

- [ ] **Step 3: Implement `analytics.py`**

```python
# Money from order lines excluding VAT: a settled bill that included VAT in its menu prices
# stores its rate; divide by 1 + rate. Bills with tax on top (Pakistan) and simulated orders
# without a bill count as they are.
_BILL = "LEFT JOIN bills b ON b.id = o.bill_id"
_NET = "(CASE WHEN b.tax_pricing = 'included' THEN 1 + b.tax_rate ELSE 1 END)"
```

`kpis`:

```python
                "SELECT count(DISTINCT o.id), "
                f"coalesce(sum(oi.quantity * oi.unit_price / {_NET}), 0), "
                f"coalesce(sum(oi.quantity * (oi.unit_price / {_NET} - oi.unit_cost)), 0) "
                f"FROM orders o JOIN order_item oi ON oi.order_id = o.id {_BILL} WHERE {_SCOPE}"
```

`daily_item_sales`: `sum(oi.quantity * oi.unit_price / {_NET})` and `{_BILL}` after the join.
`peak_hours`: `coalesce(sum(o.total / {_NET}), 0)` with `FROM orders o {_BILL} WHERE ...`.

New function:

```python
async def service_charge_collected(db: AsyncSession, w: Window) -> Decimal:
    """Optional service charge on bills settled in the window: staff money, never revenue."""
    value = await db.scalar(
        text(
            "SELECT coalesce(sum(service_charge_amount), 0) FROM bills "
            "WHERE restaurant_id = :rid AND status = 'settled' "
            "AND settled_at >= :start AND settled_at < :end"
        ),
        w.params(),
    )
    return Decimal(value).quantize(_CENTS)
```

- [ ] **Step 4: Implement `brief.py`**

`current_prices`: divide menu prices by the venue's current factor so what-if and reprice figures exclude VAT too:

```python
    factor = float(price_tax_factor(restaurant.tax_jurisdiction, local_today(restaurant)))
    # ... where each (p, c) is stored:
    prices[...] = (float(p) / factor, float(c))
```

In `compute_brief`, add to the returned dict:

```python
        "prices_include_tax": price_tax_factor(restaurant.tax_jurisdiction, today) != 1,
        "tax_split_by_method": splits_by_method(restaurant.tax_jurisdiction),
        "service_charge_collected": await analytics.service_charge_collected(db, w),
```

Only narrate the payment mix where it means something; replace the `"payment_mix": {...}` facts entry with

```python
        **(
            {"payment_mix": {...the existing dict...}}
            if splits_by_method(restaurant.tax_jurisdiction)
            else {}
        ),
```

`template_summary` already reads it with `facts.get("payment_mix")`. The service-charge figure is not narrated.

`schemas/owner.py` `DailyBriefResponse`: add `prices_include_tax: bool`, `tax_split_by_method: bool`, `service_charge_collected: Decimal`.

Check the cache: if `compute_brief` results are cached in Redis under a key, bump the key's version suffix so cached briefs pick up the new fields (`grep -n "brief:" src/services/brief.py src/routers/owner.py`).

- [ ] **Step 5: Run tests**

Run: `docker compose run --rm api-test pytest -q tests/test_global_bills.py tests/test_analytics_api.py tests/test_analytics_pure.py tests/test_brief*.py tests/test_whatif*.py tests/test_service_report*.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/src/services/analytics.py services/api/src/services/brief.py services/api/src/schemas/owner.py services/api/tests
git commit -m "feat(api): sales figures exclude VAT where prices include it; service charge reported apart"
```

---

### Task 10: Regenerate the API client

**Files:**
- Modify: `packages/api-client/openapi.json`, `packages/api-client/src/generated/schema.d.ts`

- [ ] **Step 1: Regenerate** with the repo's command (read `packages/api-client/package.json` scripts and the `Makefile` target that writes `openapi.json`; run that exact command, with the stack up via `LLM_PROVIDER=mock DEMO_MODE=true make up` if it needs the API).
- [ ] **Step 2: Check** `git diff --stat packages/api-client` shows only the new fields (`tax_included`, `service_charge_rate`, `service_charge_amount`, `service_included`, `tax_pricing`, `tax_rule`, `service_charge_allowed`, `prices_include_tax`, `tax_split_by_method`, `service_charge_collected`).
- [ ] **Step 3: Type-check both apps:** `pnpm --filter guest-web exec tsc --noEmit && pnpm --filter owner-web exec tsc --noEmit`. Expected: clean.
- [ ] **Step 4: Commit**

```bash
git add packages/api-client
git commit -m "chore(api-client): regenerate for per-country tax and the optional service charge"
```

---

### Task 11: Guest screens

**Files:**
- Modify: `apps/guest-web/src/lib/pay.ts`, `apps/guest-web/src/components/PaySheet.tsx`, `apps/guest-web/src/app/[lang]/menu/page.tsx`, `apps/guest-web/src/i18n/en.ts`, `apps/guest-web/src/i18n/it.ts`
- Test: `apps/guest-web/src/lib/pay.test.ts`, create `apps/guest-web/src/components/PaySheet.test.tsx`, `packages/ui/src/format.test.ts`

- [ ] **Step 1: Failing tests**

`packages/ui/src/format.test.ts`:

```ts
  it("formats pounds and dirhams", () => {
    expect(formatPrice(23.63, "GBP", "en")).toBe("£23.63");
    expect(formatPrice(105, "AED", "en").replace(/\s/g, " ")).toBe("AED 105.00");
    expect(formatPrice(23.63, "GBP", "it").replace(/\s/g, " ")).toBe("23,63 £");
  });
```

(If the actual `Intl` output differs, check it in Node first and assert the real string; the point is that both currencies keep two decimals.)

`apps/guest-web/src/lib/pay.test.ts`:

```ts
import { payTotal, serviceLine } from "./pay";

describe("payTotal", () => {
  const m = { method: "card", label: "Card", payment_class: "standard", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true } as const;
  it("adds the optional service only when chosen", () => {
    expect(payTotal(m, "2.63", true)).toBe(23.63);
    expect(payTotal(m, "2.63", false)).toBe(21);
  });
  it("names the service line with its rate", () => {
    expect(serviceLine("0.1250", "Add optional service ({rate}%)")).toBe("Add optional service (12.5%)");
  });
});
```

`apps/guest-web/src/components/PaySheet.test.tsx` (jsdom; follow the render pattern in `CallWaiter.test.tsx`):

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PaySheet } from "./PaySheet";
import type { GuestBill } from "../lib/pay";

const ukBill: GuestBill = {
  bill_no: 1, status: "open", bill_requested_at: null,
  lines: [{ name: "Pie", option_label: null, quantity: 1, unit_price: "21.00", line_total: "21.00" }],
  subtotal: "21.00", currency: "GBP",
  methods: [
    { method: "cash", label: "Cash", payment_class: "standard", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true },
    { method: "card", label: "Card", payment_class: "digital", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true },
  ],
  payment_details: { raast_id: null, jazzcash: null, easypaisa: null, iban: null, account_title: null, sample: false },
  claim: null, voided: [], order_status: null, payment_method: null, tax_rate: null, total: null,
  service_charge_rate: "0.1250", service_charge_amount: "2.63",
};

describe("PaySheet in a VAT-inclusive venue", () => {
  it("shows one total with VAT included and the optional service switch", () => {
    render(<PaySheet lang="en" bill={ukBill} open onClose={() => {}} onUpdated={() => {}} onConflict={() => {}} />);
    expect(screen.getByText("Includes VAT 20%: £3.50")).toBeTruthy();
    const sw = screen.getByRole("switch", { name: "Add optional service (12.5%): £2.63" });
    expect(sw.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByTestId("pay-total").textContent).toBe("£23.63");
    fireEvent.click(sw);
    expect(screen.getByTestId("pay-total").textContent).toBe("£21.00");
    expect(screen.queryByText(/Raast|JazzCash/)).toBeNull();
  });

  it("sends the service choice with the claim", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ukBill });
    vi.stubGlobal("fetch", fetchMock);
    render(<PaySheet lang="en" bill={ukBill} open onClose={() => {}} onUpdated={() => {}} onConflict={() => {}} />);
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(screen.getByRole("button", { name: /Card/ }));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ method: "card", reference: null, service_included: false });
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

Run: `pnpm --filter guest-web exec vitest run && pnpm --filter ui exec vitest run`
Expected: FAIL (missing exports, missing text).

- [ ] **Step 3: Implement**

`lib/pay.ts`: add to `MethodPreview` `tax_included: boolean;`, to `PaymentClaim` `service_included: boolean;`, to `GuestBill` `service_charge_rate: string; service_charge_amount: string;`, and:

```ts
/** What the guest pays for a method: the method total plus the optional service when chosen. */
export const payTotal = (m: MethodPreview, serviceAmount: string, withService: boolean) =>
  Number(m.total) + (withService ? Number(serviceAmount) : 0);

/** "Add optional service (12.5%)" from the template and the rate as a fraction. */
export const serviceLine = (rate: string, template: string) =>
  template.replace("{rate}", String(Number((Number(rate) * 100).toFixed(2))));
```

`i18n/en.ts` `pay`:

```ts
    total: "Total",
    vatIncluded: "Includes VAT {rate}%: {amount}",
    service: "Add optional service ({rate}%): {amount}",
```

`i18n/it.ts` `pay`:

```ts
    total: "Totale",
    vatIncluded: "IVA {rate}% inclusa: {amount}",
    service: "Aggiungi servizio facoltativo ({rate}%): {amount}",
```

and for the menu (both files, `menu` section; add the section key where the menu strings live):

```ts
    serviceNotice: "An optional {rate}% service charge is added to table bills.",
```

```ts
    serviceNotice: "Ai conti al tavolo si aggiunge un servizio facoltativo del {rate}%.",
```

`PaySheet.tsx`:
- state: `const [withService, setWithService] = useState(bill.claim?.service_included ?? true);`, reset it in the open effect with the same expression.
- `const hasService = Number(bill.service_charge_amount) > 0; const included = bill.methods[0]?.tax_included ?? false;`
- claim body: `JSON.stringify({ method, reference: ref, service_included: hasService && withService })`.
- After the Subtotal line, when `isOpen && hasService`:

```tsx
        <button
          type="button"
          role="switch"
          aria-checked={withService}
          onClick={() => setWithService(!withService)}
          className="flex w-full items-center justify-between gap-3 rounded-xl border border-line bg-card px-4 py-3 text-left text-sm text-ink"
        >
          <span>
            {serviceLine(bill.service_charge_rate, dict.pay.service).replace("{amount}", money(bill.service_charge_amount))}
          </span>
          <span aria-hidden className={`h-5 w-9 rounded-full ${withService ? "bg-terracotta" : "bg-line"}`} />
        </button>
```

- When `isOpen && included` (one total for every method), show the total and VAT line instead of per-method prices:

```tsx
        <div className="space-y-1">
          <p className="flex justify-between text-base font-semibold text-ink">
            <span>{dict.pay.total}</span>
            <span data-testid="pay-total">{money(String(payTotal(bill.methods[0], bill.service_charge_amount, hasService && withService)))}</span>
          </p>
          <p className="text-xs text-ink-muted">
            {dict.pay.vatIncluded.replace("{rate}", percent(bill.methods[0].tax_rate)).replace("{amount}", money(bill.methods[0].tax_amount))}
          </p>
        </div>
```

  and in the method buttons render the price span and the `taxRate` sub-line only when `!included`. Where per-method prices do show (Pakistan), use `money(String(payTotal(m, bill.service_charge_amount, hasService && withService)))`. Pakistan has no service charge, so its numbers are unchanged. The "pay to" line (`payTo`) uses the same `payTotal` value.

`app/[lang]/menu/page.tsx`: under the `<h1>` with the venue name:

```tsx
              {Number(menu.restaurant.service_charge_rate) > 0 && (
                <p className="text-xs text-ink-muted">
                  {serviceLine(menu.restaurant.service_charge_rate, dict.menu.serviceNotice)}
                </p>
              )}
```

(Add `service_charge_rate: string` to the menu's restaurant type in the guest menu types; find it with `grep -rn "currency: string" apps/guest-web/src/lib`.)

- [ ] **Step 4: Run tests and types**

Run: `pnpm --filter guest-web exec vitest run && pnpm --filter ui exec vitest run && pnpm --filter guest-web exec tsc --noEmit && pnpm --filter guest-web lint`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web packages/ui/src/format.test.ts
git commit -m "feat(guest-web): VAT-inclusive total, optional service switch and menu notice"
```

---

### Task 12: Staff and owner screens

**Files:**
- Modify: `apps/owner-web/src/lib/bill.ts`, `apps/owner-web/src/app/(dashboard)/bills/page.tsx`, `apps/owner-web/src/app/(dashboard)/tables/page.tsx`, `apps/owner-web/src/app/(dashboard)/brief/page.tsx`, `apps/owner-web/src/lib/analytics.ts`
- Test: `apps/owner-web/src/lib/bill.test.ts`

- [ ] **Step 1: Failing tests** (`lib/bill.test.ts`)

```ts
import { billFooter, settlePayload, taxLabel } from "./bill";

const ukBill = {
  methods: [{ method: "card", label: "Card", payment_class: "digital", tax_rate: "0.20", tax_amount: "3.50", total: "21.00", tax_included: true }],
  service_charge_amount: "2.63",
} as const;

describe("settlePayload with the optional service", () => {
  it("adds the service to the expected total only when included", () => {
    expect(settlePayload(ukBill as never, "card", "", false, true)?.expected_total).toBe("23.63");
    expect(settlePayload(ukBill as never, "card", "", false, true)?.service_included).toBe(true);
    expect(settlePayload(ukBill as never, "card", "", false, false)?.expected_total).toBe("21.00");
  });
});

describe("taxLabel", () => {
  it("says VAT is included where it is", () => {
    expect(taxLabel("0.20", "card", true)).toBe("VAT 20% included");
    expect(taxLabel("0.16", "cash", false)).toBe("Sales tax (illustrative) 16% — cash");
  });
});

describe("billFooter", () => {
  it("mentions Pakistani authorities only for Pakistani bills", () => {
    expect(billFooter("PB")).toContain("FBR");
    expect(billFooter("GB")).toBe("Sample bill — not a tax invoice.");
  });
});
```

- [ ] **Step 2: Run to confirm failure**

Run: `pnpm --filter owner-web exec vitest run src/lib/bill.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement `lib/bill.ts`**

- `TaxPreview`: add `tax_included: boolean;`. `PaymentClaim`: add `service_included: boolean;`. `BillDetail`: add `tax_pricing: string | null; service_charge_rate: string; service_charge_amount: string;`.
- `settlePayload`:

```ts
export function settlePayload(
  bill: Pick<BillDetail, "methods" | "service_charge_amount">,
  method: PaymentMethod,
  reference: string,
  acknowledgeReused: boolean,
  serviceIncluded = false,
) {
  const preview = previewFor(bill, method);
  if (!preview) return null;
  const ref = method === "cash" ? "" : reference.trim();
  const service = serviceIncluded ? Number(bill.service_charge_amount) : 0;
  return {
    payment_method: method,
    payment_reference: ref || null,
    expected_total: (Number(preview.total) + service).toFixed(2),
    expected_method: method,
    acknowledge_reused_reference: acknowledgeReused,
    service_included: serviceIncluded && service > 0,
  };
}
```

  Check the existing `settlePayload` tests: if one asserts `expected_total` equals the raw string, `toFixed(2)` keeps the same "2657.00" form for Pakistan; if any assertion compares an object without `service_included`, add `service_included: false` to the expected object and say so in the commit.
- `taxLabel(rate, method, included = false)`: return `` `VAT ${pct}% included` `` when `included`, else the current text.
- Replace the constant footer with:

```ts
export const billFooter = (jurisdiction: string | null) =>
  jurisdiction === "PB" || jurisdiction === "ICT"
    ? "Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority."
    : "Sample bill — not a tax invoice.";
```

  Keep `SAMPLE_BILL_FOOTER` as `billFooter("PB")` if other code imports it; update callers to `billFooter(detail.tax_jurisdiction)`.

- [ ] **Step 4: Bills page (`bills/page.tsx`)**

- Method buttons: render `PAYMENT_METHODS.filter((m) => detail.methods.some((p) => p.method === m.value))` (line ~709) so UK and Dubai bills show only Cash and Card.
- Service toggle in the settle panel, shown when `Number(detail.service_charge_amount) > 0`: a `role="switch"` button "Optional service ({rate}%): {amount}", state `serviceIncluded`, initialised on load to `detail.claim ? detail.claim.service_included : true`.
- Pass `serviceIncluded` as the fifth argument of `settlePayload` (line ~222).
- Totals block (around line 684): for `tax_included`, show "Subtotal", then `taxLabel(rate, method, true)` with the amount, then, when on, "Optional service" with its amount, then "Total". On a settled bill, read `detail.service_charge_amount` and `detail.total`.
- Use `billFooter(detail.tax_jurisdiction)` for the footer.
- The `totals` change signature (line ~168) must include `detail.service_charge_amount`, so a server-side change in service amount counts as "bill changed".

- [ ] **Step 5: Settings (`tables/page.tsx`)**

- Read `tax_rule`, `service_charge_allowed` and `service_charge_rate` from `GET .../settings`.
- Show one read-only line:
  - "Prices include VAT 20% (United Kingdom)" for `included`;
  - "Sales tax added to bills (Punjab, Pakistan)" for `on_top`;
  - nothing when `tax_rule` is null.
- When `service_charge_allowed`, a percentage input "Optional service charge (%)", 0–20 in 0.5 steps, sent as a fraction (`(Number(v) / 100).toFixed(4)`) in the same PATCH body as the other settings. Show the API's 422 detail under the field.
- Helper text: "Shown to guests before they order and on the bill as optional. By law, staff must receive all of it."

- [ ] **Step 6: Brief (`brief/page.tsx`, `lib/analytics.ts`)**

- Add `prices_include_tax`, `tax_split_by_method` and `service_charge_collected` to the brief type in `lib/analytics.ts`.
- Labels: "Revenue", "Average order value" and "Contribution margin" get the suffix " (excl. VAT)" when `prices_include_tax`.
- Wrap the "Payments and tax" card (line ~285) in `brief.tax_split_by_method && (...)`.
- When `Number(brief.service_charge_collected) > 0`, add a `StatTile` labelled "Service charge collected (for staff)" with the value `money(Number(brief.service_charge_collected), brief.currency)` and the sub-text "Not revenue. UK law: staff receive all of it."

- [ ] **Step 7: Run tests, types and lint**

Run: `pnpm --filter owner-web exec vitest run && pnpm --filter owner-web exec tsc --noEmit && pnpm --filter owner-web lint`
Expected: PASS, clean.

- [ ] **Step 8: Commit**

```bash
git add apps/owner-web
git commit -m "feat(owner-web): VAT-included bills, optional service at settle, settings and report labels"
```

---

### Task 13: Docs and full verification

**Files:**
- Modify: `README.md`, `docs/architecture.md`, `docs/analytics.md`, `CLAUDE.md`

- [ ] **Step 1: Docs.** Describe only what is built:
  - `docs/architecture.md`: tax data (two files), `charge_for`, the bill snapshot fields, the service-charge rule;
  - `docs/analytics.md`: sales exclude VAT via the bill's snapshot rate, and the service-charge figure is not revenue;
  - README: a "Tax and currency" paragraph listing PB, ICT, GB and AE-DU.
  - Add to `CLAUDE.md` under Architecture: "- Tax rules are data (`data/tax_rates.json`, `data/tax_jurisdictions.json`) with a source per rate; code never hard-codes a rate, and a venue only settles with its jurisdiction's methods."
- [ ] **Step 2: Branding check:** `bash scripts/check_branding.sh`. Expected: passes.
- [ ] **Step 3: Full CI:** `make ci` (or the scratchpad make shim). Expected: lint, all Python tests, all Vitest suites and the branding check pass.
- [ ] **Step 4: Fresh-stack verification:** `LLM_PROVIDER=mock DEMO_MODE=true make verify-f`. Expected: all steps PASS (Pakistan flows unchanged).
- [ ] **Step 5: Commit**

```bash
git add README.md docs/architecture.md docs/analytics.md CLAUDE.md
git commit -m "docs: per-country tax, VAT-inclusive prices and the optional service charge"
```

---

## Self-review notes

- **Spec coverage:**

  | Spec item | Task |
  |---|---|
  | Data and loader | 1 |
  | Sums and rounding | 2 |
  | Snapshot | 3, 5 |
  | Venue currency check | 4 |
  | Methods per jurisdiction | 2, 5, 6, 8, 12 |
  | Previews `tax_included` | 5 |
  | Settle | 5 |
  | Service charge: setting | 7 |
  | Service charge: bill | 5 |
  | Service charge: guest | 6, 11 |
  | Service charge: staff | 12 |
  | Service charge: report | 9 |
  | Reports excl. VAT, Pakistan-only card | 9, 12 |
  | Menu notice | 6, 11 |
  | Tax-invoice look | 12 |
  | Docs | 13 |

- **Deviation from the spec:**
  - The spec says analytics divide by the rate "in force that day". The plan uses each settled bill's own snapshot `tax_rate`, which is the same number and needs no date logic.
  - `tax_for` keeps its `(rate, tax)` shape for existing callers; the new `charge_for` returns the total. The spec text is updated to match.
- **Names used across tasks:** `charge_for`, `Charge(rate, tax, total, pricing)`, `methods_for`, `splits_by_method`, `price_tax_factor`, `service_charge_for`, `bill_service`, `METHOD_REFUSED`, `check_venue_tax`, `jurisdiction_of`, `round_money`, `CENTS`.
