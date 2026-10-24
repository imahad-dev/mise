# Pakistan Demo Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-restaurant account isolation, two fictional PKR venues (Angeethi House, Lahore; Kehwa & Crumb, Islamabad) with portion options, table bills with payment recording and payment-dependent sales tax, and a sample bill — as specified in `docs/superpowers/specs/2026-10-22-pakistan-demo-foundation-design.md`.

**Architecture:** Users and memberships replace the shared owner key and staff PIN; one FastAPI dependency (`restaurant_access`) guards every `/api/restaurants/{slug}` route and answers 404 to non-members. Menu items gain options; orders snapshot the option. A `bills` table groups a table's orders; tax comes from a pure function over `data/tax_rates.json`. The simulator writes bills too, and the brief reports payment mix. The owner app gains a venue switcher and a Bills page; the guest app gains a size picker and "Request bill".

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, Postgres 16, Redis 7, Next.js 15, Tailwind v4, Vitest, Playwright. Python stdlib `hashlib.scrypt` for passwords (no new dependency).

---

## Conventions for every task

- Real table names are singular: `restaurant`, `menu_item`, `menu_translation`, `dining_table`, `guest_session`, `order_item`, `audit_log` (but `orders`). New tables in this plan: `users`, `memberships`, `menu_item_option`, `bills`. Foreign keys must target the real names.

- Branch: `feat/pakistan-foundation` (already created). Never commit to `main`.
- Shell: Git Bash on Windows. `make` and `python3` need the scratchpad wrappers:
  `export PATH="/c/Users/MSI/AppData/Local/Temp/claude/C--Users-MSI-Source-Code-Mise/e8eee3b8-2d67-4900-b83b-437f0a538543/scratchpad/bin:$PATH"`.
  `gh` is at `"/c/Program Files/GitHub CLI/gh.exe"`.
- Never read or print `.env`; never run `printenv`, `env` or `docker compose config`. Use `LLM_PROVIDER=mock` for every stack run.
- Python tests run in Docker:
  `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/<file>.py -v`
  (whole suite: `make test-py`). TS tests: `pnpm --filter <app> test`. Lint: `make lint`.
- Architecture rules (CLAUDE.md): relationships `lazy="raise"`, explicit queries, no `db.refresh()` on objects whose relationships are used later, every route has `response_model`, the model never produces numbers.
- Models must match migrations exactly: `alembic check` runs in `make verify-f`. Every index/constraint created in a migration is also declared in the model's `__table_args__`.
- Never weaken, skip or xfail a test. When an existing test changes because behaviour changed (auth, venues), say why in the commit message.
- Commit after each task with the message shown, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

**API — new**
- `services/api/src/passwords.py` — scrypt hash/verify.
- `services/api/src/models/user.py` — `User`, `Membership`.
- `services/api/src/models/bill.py` — `Bill`.
- `services/api/src/access.py` — `CurrentUser`, `get_current_user`, `RestaurantAccess`, `restaurant_access(*roles)`.
- `services/api/src/routers/restaurants.py` — `GET /api/restaurants`.
- `services/api/src/routers/bills.py` — staff bills routes; guest bill routes live in `guest.py`.
- `services/api/src/services/tax.py` — load/validate `data/tax_rates.json`, `payment_class`, `tax_for`.
- `services/api/src/services/bills.py` — `open_bill_for_table`, `bill_lines`, `bill_previews`, `settle_bill`.
- `services/api/src/schemas/bills.py`, `services/api/src/schemas/restaurants.py`.
- `services/api/alembic/versions/0008_users_memberships.py`, `0009_venues_options.py`, `0010_bills.py`.
- `data/tax_rates.json`, `data/seed/angeethi_house.json`, `data/seed/kehwa_and_crumb.json`, `data/seed/demo_users.json`.
- `scripts/admin.py`.
- Tests: `tests/test_passwords.py`, `tests/test_auth_users.py`, `tests/test_restaurant_isolation.py`, `tests/test_tax.py`, `tests/test_options.py`, `tests/test_bills.py`, `tests/test_admin.py`, `tests/test_simulator_bills.py`, `tests/helpers.py`.

**API — modified**
- `src/auth.py` (cookie carries user id), `src/routers/auth.py`, `src/schemas/auth.py`, `src/config.py`, `src/main.py`
- `src/routers/owner.py`, `src/routers/kitchen.py`, `src/routers/orders.py`, `src/routers/guest.py`, `src/routers/demo.py`
- `src/models/restaurant.py`, `src/models/menu.py`, `src/models/order.py`, `src/models/__init__.py`
- `src/schemas/orders.py`, `src/schemas/guest.py`, `src/schemas/kitchen.py`, `src/schemas/owner.py`
- `src/services/order_snapshot.py`, `src/services/simulator.py`, `src/services/analytics.py`, `src/services/brief.py`, `src/services/whatif.py`
- `scripts/seed.py`, `scripts/simulate.py`, `scripts/verify_phase1.sh`, `scripts/verify_d.sh`, `scripts/verify_c.sh`, `scripts/e2e_smoke.sh`
- `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`, `README.md`, `docs/architecture.md`, `docs/analytics.md`, `CLAUDE.md`
- Existing tests that forge `owner:`/`staff:` cookies or use `trattoria-da-mario`.

**Web — new / modified**
- `packages/ui/src/format.ts` (PKR), `packages/ui/src/format.test.ts`
- `apps/owner-web/src/lib/venue.tsx` (+ `venue.test.tsx`), `apps/owner-web/src/lib/bill.ts` (+ `bill.test.ts`)
- `apps/owner-web/src/app/login/page.tsx`, `(dashboard)/layout.tsx`, every page with `DEFAULT_SLUG`, `(kitchen)/kitchen/page.tsx`, `(kitchen)/layout.tsx`
- `apps/owner-web/src/app/(dashboard)/bills/page.tsx`, `apps/owner-web/src/app/bills/[id]/print/page.tsx`
- `apps/owner-web/src/lib/analytics.ts` and the brief/what-if pages (currency rename)
- `apps/guest-web/src/app/[lang]/menu/page.tsx`, `apps/guest-web/src/lib/cart.ts` (+ test), `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`, guest i18n strings
- `e2e/flows.spec.ts`

---

# Phase A — Accounts and isolation

### Task 1: Password hashing

**Files:**
- Create: `services/api/src/passwords.py`
- Test: `services/api/tests/test_passwords.py`

- [ ] **Step 1: Write the failing test**

```python
"""scrypt password hashing."""

from src.passwords import hash_password, verify_password


def test_hash_then_verify():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)


def test_salt_differs_per_hash():
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_is_rejected():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "scrypt$1$2$3$bad$bad")
```

- [ ] **Step 2: Run it and see it fail**

Run: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/test_passwords.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'src.passwords'`.

- [ ] **Step 3: Implement**

```python
"""Password hashing with stdlib scrypt. Format: scrypt$n$r$p$salt_b64$hash_b64."""

import base64
import hashlib
import secrets

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        digest = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(digest, expected)
```

- [ ] **Step 4: Run the test and see it pass** (same command). Expected: 3 passed.

- [ ] **Step 5: Commit** — `feat(api): scrypt password hashing`

---

### Task 2: Users and memberships tables

**Files:**
- Create: `services/api/src/models/user.py`, `services/api/alembic/versions/0008_users_memberships.py`
- Modify: `services/api/src/models/__init__.py`
- Test: `services/api/tests/test_schema_constraints.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_schema_constraints.py`; reuse its `_create_test_restaurant` helper)

```python
async def test_user_email_unique(db_session):
    from sqlalchemy.exc import IntegrityError
    from src.models.user import User

    db_session.add(User(email="a@example.com", name="A", password_hash="x"))
    await db_session.flush()
    db_session.add(User(email="a@example.com", name="B", password_hash="y"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_membership_role_and_uniqueness(db_session):
    import uuid
    from sqlalchemy.exc import IntegrityError
    from src.models.user import Membership, User

    rid = await _create_test_restaurant(db_session)
    user = User(email="m@example.com", name="M", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, restaurant_id=uuid.UUID(rid), role="owner"))
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, restaurant_id=uuid.UUID(rid), role="staff"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

If `_create_test_restaurant` returns a `str`, keep the `uuid.UUID(rid)` conversion; if it returns a UUID, drop it.

- [ ] **Step 2: Run and see it fail** — `pytest tests/test_schema_constraints.py -k "user or membership" -v`. Expected: `ModuleNotFoundError: src.models.user`.

- [ ] **Step 3: Model**

```python
"""Owner and staff accounts, and which restaurants they may open."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="chk_users_email_lower"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'staff')", name="chk_memberships_role"),
        UniqueConstraint("user_id", "restaurant_id", name="uq_memberships_user_restaurant"),
        Index("idx_memberships_restaurant_id", "restaurant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

Match the column styles (`server_default`, `UUID` import, timestamp `onupdate`) used in `src/models/restaurant.py`; if that file differs (e.g. `default=uuid.uuid4`), copy its style exactly so `alembic check` stays clean. Export `User` and `Membership` from `src/models/__init__.py` (`__all__` too).

- [ ] **Step 4: Migration** `0008_users_memberships.py` (`down_revision = "0007_order_source_forecast_run"`): `op.create_table("users", ...)` and `op.create_table("memberships", ...)` with exactly the columns, defaults, constraints and index above; `downgrade()` drops `memberships` then `users`.

- [ ] **Step 5: Run the tests and see them pass**, then `make test-py` stays green.

- [ ] **Step 6: Commit** — `feat(api): users and memberships tables`

---

### Task 3: User sessions, login and the access dependency

**Files:**
- Create: `services/api/src/access.py`, `services/api/tests/helpers.py`, `services/api/tests/test_auth_users.py`
- Modify: `src/auth.py`, `src/routers/auth.py`, `src/schemas/auth.py`, `src/config.py`

- [ ] **Step 1: Test helper** `tests/helpers.py` (used by every later test):

```python
"""Test helpers: create users with memberships and sign them in."""

import time
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.models.user import Membership, User
from src.passwords import hash_password


async def make_user(
    db: AsyncSession,
    memberships: list[tuple[uuid.UUID, str]],
    email: str | None = None,
    password: str = "pw-for-tests",
) -> User:
    user = User(
        email=email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        name="Test user",
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    for restaurant_id, role in memberships:
        db.add(Membership(user_id=user.id, restaurant_id=restaurant_id, role=role))
    await db.flush()
    return user


def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set(AUTH_COOKIE_NAME, sign_value(f"{user.id}:{int(time.time()) + 3600}"))


async def as_member(client: AsyncClient, db: AsyncSession, restaurant_id: uuid.UUID, role: str) -> User:
    user = await make_user(db, [(restaurant_id, role)])
    sign_in(client, user)
    return user
```

- [ ] **Step 2: Failing tests** `tests/test_auth_users.py`:

```python
"""Per-user login, sessions and restaurant access."""

import time

import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.models.restaurant import Restaurant
from tests.helpers import as_member, make_user


@pytest.fixture
async def two_restaurants(db_session: AsyncSession) -> tuple[Restaurant, Restaurant]:
    a = Restaurant(name="A", slug="venue-a", currency="PKR", timezone="Asia/Karachi",
                   languages=["en"], default_language="en")
    b = Restaurant(name="B", slug="venue-b", currency="PKR", timezone="Asia/Karachi",
                   languages=["en"], default_language="en")
    db_session.add_all([a, b])
    await db_session.flush()
    return a, b


async def test_login_with_email_and_password(client, db_session, two_restaurants):
    a, _ = two_restaurants
    await make_user(db_session, [(a.id, "owner")], email="owner@example.com", password="s3cret-pass")
    resp = await client.post("/api/auth/login", json={"email": "Owner@Example.com", "password": "s3cret-pass"})
    assert resp.status_code == 200
    assert AUTH_COOKIE_NAME in resp.cookies
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


async def test_wrong_password_and_unknown_email_look_the_same(client, db_session, two_restaurants):
    a, _ = two_restaurants
    await make_user(db_session, [(a.id, "owner")], email="o2@example.com", password="right-pass")
    wrong = await client.post("/api/auth/login", json={"email": "o2@example.com", "password": "nope"})
    unknown = await client.post("/api/auth/login", json={"email": "who@example.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_old_role_cookie_is_rejected(client):
    client.cookies.set(AUTH_COOKIE_NAME, sign_value(f"owner:{int(time.time()) + 3600}"))
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_non_member_gets_404_and_staff_gets_403(client, db_session, two_restaurants):
    a, b = two_restaurants
    await as_member(client, db_session, a.id, "staff")
    assert (await client.get("/api/restaurants/venue-b/menu-items")).status_code == 404
    assert (await client.get("/api/restaurants/no-such-venue/menu-items")).status_code == 404
    assert (await client.get("/api/restaurants/venue-a/menu-items")).status_code == 403
    assert (await client.get("/api/restaurants/venue-a/kitchen/orders")).status_code == 200
```

The last test passes only after Task 4 applies the dependency; mark nothing as xfail — run only the first three until Task 4 is done, then all four.

- [ ] **Step 3: Run and see it fail** — `pytest tests/test_auth_users.py -v`. Expected: login 422/401, `me` has no `email`.

- [ ] **Step 4: Cookie now carries the user id.** In `src/auth.py`:
  - `set_auth_cookie(response, user_id: uuid.UUID)` signs `f"{user_id}:{exp_ts}"` (same flags and 8 hours).
  - Delete `get_current_role`, `require_staff_or_owner`, `require_owner`. Keep `Role = Literal["owner", "staff"]`, guest helpers and signing helpers unchanged.

- [ ] **Step 5: `src/access.py`**

```python
"""Signed-in user and per-restaurant access. Non-members get 404, never 403."""

import time
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, Role, unsign_value
from src.database import get_db
from src.models.restaurant import Restaurant
from src.models.user import Membership, User

NOT_FOUND = "Restaurant not found"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not cookie:
        raise _unauthorized("Authentication required")
    val = unsign_value(cookie)
    if not val or ":" not in val:
        raise _unauthorized("Invalid authentication cookie")
    uid_str, exp_str = val.split(":", 1)
    try:
        user_id = uuid.UUID(uid_str)
        expired = time.time() > int(exp_str)
    except ValueError:
        raise _unauthorized("Malformed authentication cookie") from None
    if expired:
        raise _unauthorized("Authentication cookie expired")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise _unauthorized("Unknown user")
    return user


@dataclass(frozen=True)
class RestaurantAccess:
    restaurant: Restaurant
    user: User
    role: Role


def restaurant_access(*roles: Role):
    """Dependency factory: the path's {slug} restaurant, if the user is a member with one of roles."""
    allowed = set(roles or ("owner", "staff"))

    async def dependency(
        slug: str,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> RestaurantAccess:
        row = (
            await db.execute(
                select(Restaurant, Membership.role)
                .join(Membership, Membership.restaurant_id == Restaurant.id)
                .where(Restaurant.slug == slug, Membership.user_id == user.id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
        restaurant, role = row
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner privileges required")
        return RestaurantAccess(restaurant=restaurant, user=user, role=role)

    return dependency
```

- [ ] **Step 6: Auth routes and schemas.**
  - `schemas/auth.py`: `LoginRequest(email: EmailStr-free str with min_length=3, max_length=254; password: str min_length=1 max_length=256)`; `LoginResponse(status: Literal["ok"], name: str, email: str)`; `MeResponse(name: str, email: str)`; `DemoLoginRequest(role: Literal["owner","staff"], venue: str | None = None)`. Do not add a new dependency for email validation.
  - `routers/auth.py` `login`: keep the Redis rate-limit block exactly; replace the secret comparison with: look up `User` by `payload.email.strip().lower()`; `is_valid = user is not None and verify_password(payload.password, user.password_hash)`; when the user is missing, still call `verify_password(payload.password, _DUMMY_HASH)` (a module-level `hash_password("dummy")`) so timing does not reveal which emails exist. On success `set_auth_cookie(response, user.id)`.
  - `me` depends on `get_current_user` and returns name and email.
  - `demo_login`: still 404 unless `settings.demo_mode`; keep the IP limit. Find the seeded demo user: owner → email `settings.demo_owner_email`; staff → `demo-staff+{venue}@mise.demo` where `venue` defaults to the first slug in `settings.demo_restaurant_slugs`. 404 "Demo user not found" if absent (seed not run). Set the cookie for that user.
  - `config.py`: delete `owner_api_key` and `staff_pin` (and their entries in `reject_default_secrets_in_non_dev`). Replace `demo_restaurant_slug: str` with `demo_restaurant_slugs: list[str] = ["angeethi-house", "kehwa-and-crumb"]` and add `demo_owner_email: str = "demo-owner@mise.demo"`. Update `demo.py` temporarily to use `settings.demo_restaurant_slugs[0]` (Task 11 rewrites it).

- [ ] **Step 7: Remove the shared secrets everywhere else:** `.env.example` (OWNER_API_KEY, STAFF_PIN lines), `docker-compose.yml` (both services), `.github/workflows/ci.yml`, `scripts/e2e_smoke.sh` and `scripts/verify_c.sh` (switch to demo-login with `DEMO_MODE=true`), `scripts/verify_d.sh` (drop the non-demo branch; demo-login only), README env table rows.

- [ ] **Step 8: Run `pytest tests/test_auth_users.py -k "not non_member" -v`.** Expected: 3 passed. Existing tests still forge `owner:` cookies and will fail until Task 4; that is expected inside this task only — do not commit a red suite: continue directly to Task 4 and commit both together if needed.

- [ ] **Step 9: Commit** (after Task 4 is green) — `feat(api): per-user login replaces shared owner key and staff PIN`

---

### Task 4: Guard every restaurant route; list my venues; isolation test

**Files:**
- Create: `src/routers/restaurants.py`, `src/schemas/restaurants.py`, `tests/test_restaurant_isolation.py`
- Modify: `src/routers/owner.py`, `src/routers/kitchen.py`, `src/main.py`, every test that forges `owner:`/`staff:` cookies (`test_order_path.py`, `test_analytics_api.py`, `test_simulator_concurrency.py`, `test_demo.py`, others found by `grep -rn 'sign_value(f"owner\|sign_value(f"staff\|"secret"' tests`)

- [ ] **Step 1: Failing isolation test** `tests/test_restaurant_isolation.py`:

```python
"""Every /api/restaurants/{slug} route refuses members of another restaurant with 404."""

import re

import pytest
from fastapi.routing import APIRoute

from src.main import app
from src.models.restaurant import Restaurant
from tests.helpers import as_member

PLACEHOLDER = re.compile(r"\{(\w+)\}")
DUMMY = {"id": "00000000-0000-0000-0000-000000000000",
         "order_id": "00000000-0000-0000-0000-000000000000",
         "bill_id": "00000000-0000-0000-0000-000000000000"}


def _slug_routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and "{slug}" in route.path:
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


def test_there_are_slug_routes():
    assert len(list(_slug_routes())) >= 10


@pytest.mark.parametrize(("method", "path"), sorted(_slug_routes()))
async def test_other_venue_member_gets_404(client, db_session, method, path):
    mine = Restaurant(name="Mine", slug="iso-mine", currency="PKR", timezone="Asia/Karachi",
                      languages=["en"], default_language="en")
    theirs = Restaurant(name="Theirs", slug="iso-theirs", currency="PKR", timezone="Asia/Karachi",
                        languages=["en"], default_language="en")
    db_session.add_all([mine, theirs])
    await db_session.flush()
    await as_member(client, db_session, mine.id, "owner")
    url = PLACEHOLDER.sub(lambda m: "iso-theirs" if m[1] == "slug" else DUMMY.get(m[1], "x"), path)
    resp = await client.request(method, url, json={})
    assert resp.status_code == 404, f"{method} {path} -> {resp.status_code}"
    assert resp.json()["detail"] == "Restaurant not found"
```

The body `{}` may fail validation before the dependency runs and return 422 for some routes. FastAPI resolves path/dependency errors and body errors together; if any route returns 422 here, make that route's dependency run first by keeping the access dependency as the first parameter, and if FastAPI still reports 422, send a minimal valid body for that route from a small `BODIES` dict in the test (do not exclude the route).

- [ ] **Step 2: Run and see it fail** — routes currently return 401 for the new cookie or 200.

- [ ] **Step 3: Apply the dependency.** In `owner.py` and `kitchen.py`:
  - Delete `_get_restaurant` in both files.
  - Each route replaces `role: Role = Depends(require_owner)` with `access: RestaurantAccess = Depends(restaurant_access("owner"))`, and `require_staff_or_owner` with `restaurant_access("owner", "staff")`. Put it as the first dependency parameter.
  - Replace `restaurant = await _get_restaurant(slug, db)` with `restaurant = access.restaurant`. Keep the `slug: str` path parameter where it is used in messages; otherwise remove it (the dependency reads it).
  - Kitchen SSE: `access` resolves before `await db.close()`; channel stays `kitchen:{restaurant.id}`.
  - Audit `actor` strings that used the role become `f"user:{access.user.id}"`.

- [ ] **Step 4: `GET /api/restaurants`** — `schemas/restaurants.py`:

```python
from typing import Literal
from pydantic import BaseModel


class MyRestaurant(BaseModel):
    slug: str
    name: str
    city: str | None
    currency: str
    role: Literal["owner", "staff"]


class MyRestaurantsResponse(BaseModel):
    restaurants: list[MyRestaurant]
```

`routers/restaurants.py`: `@router.get("/api/restaurants", response_model=MyRestaurantsResponse)`; query `select(Restaurant, Membership.role).join(Membership).where(Membership.user_id == user.id).order_by(Restaurant.name)`. `city` does not exist until Task 6 — return `None` via `getattr(r, "city", None)` now and switch to `r.city` in Task 6. Register the router in `main.py`. Add a test in `test_auth_users.py`: a user with membership in A only lists exactly `["venue-a"]`.

- [ ] **Step 5: Move existing tests to real users.** Replace each forged cookie with `await as_member(client, db_session, restaurant.id, "owner")` (or `"staff"`). For tests that create their own `AsyncClient` (concurrency tests), create the user in a committed session the same way the test already creates its data, then set the cookie with `sign_in(ac, user)`. Tests that asserted "staff gets 403 on owner route" stay and still expect 403. Tests that asserted "no cookie → 401" stay.

- [ ] **Step 6: Run the full suite** — `make test-py`. Expected: all pass, including every parametrized isolation case.

- [ ] **Step 7: Commit** — `feat(api): restaurant membership guards every venue route` (body: existing tests now sign in as real members because shared role cookies no longer exist).

---

### Task 5: Owner app — email login, venue context and switcher

**Files:**
- Create: `apps/owner-web/src/lib/venue.tsx`, `apps/owner-web/src/lib/venue.test.tsx`
- Modify: `apps/owner-web/src/app/login/page.tsx`, `(dashboard)/layout.tsx`, `(kitchen)/layout.tsx`, `(kitchen)/kitchen/page.tsx`, and every page with `const DEFAULT_SLUG` (`ai`, `brief`, `menu`, `menu/ingest`, dashboard `page.tsx`, `tables`, `kitchen`), `src/middleware.test.ts`

- [ ] **Step 1: Failing test** `venue.test.tsx` (Vitest + Testing Library, already used by `packages/ui`; if `@testing-library/react` is not a dev dependency of owner-web, test the pure helpers only):

```tsx
import { describe, expect, it, vi } from "vitest";
import { pickVenue, readStoredSlug, storeSlug } from "./venue";

const venues = [
  { slug: "angeethi-house", name: "Angeethi House", city: "Lahore", currency: "PKR", role: "owner" as const },
  { slug: "kehwa-and-crumb", name: "Kehwa & Crumb", city: "Islamabad", currency: "PKR", role: "owner" as const },
];

describe("venue selection", () => {
  it("uses the stored slug when it is one of my venues", () => {
    expect(pickVenue(venues, "kehwa-and-crumb")?.slug).toBe("kehwa-and-crumb");
  });
  it("falls back to the first venue for an unknown or missing slug", () => {
    expect(pickVenue(venues, "someone-else")?.slug).toBe("angeethi-house");
    expect(pickVenue(venues, null)?.slug).toBe("angeethi-house");
  });
  it("returns null when I have no venues", () => {
    expect(pickVenue([], "x")).toBeNull();
  });
  it("survives storage that throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readStoredSlug()).toBeNull();
    spy.mockRestore();
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => storeSlug("x")).not.toThrow();
    set.mockRestore();
  });
});
```

If owner-web's Vitest environment is `node`, set `// @vitest-environment jsdom` at the top of the file (jsdom is already used by `packages/ui` tests; add it to owner-web devDependencies only if missing).

- [ ] **Step 2: Run** `pnpm --filter owner-web test` → FAIL (module missing).

- [ ] **Step 3: Implement `venue.tsx`**

```tsx
"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export interface Venue {
  slug: string;
  name: string;
  city: string | null;
  currency: string;
  role: "owner" | "staff";
}

const KEY = "mise.venue";

export function readStoredSlug(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function storeSlug(slug: string): void {
  try {
    window.localStorage.setItem(KEY, slug);
  } catch {
    // Storage blocked: the choice lasts for this page view only.
  }
}

export function pickVenue(venues: Venue[], stored: string | null): Venue | null {
  return venues.find((v) => v.slug === stored) ?? venues[0] ?? null;
}

interface VenueState {
  venues: Venue[];
  venue: Venue | null;
  loading: boolean;
  select: (slug: string) => void;
}

const VenueContext = createContext<VenueState>({ venues: [], venue: null, loading: true, select: () => {} });

export function VenueProvider({ children }: { children: React.ReactNode }) {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venue, setVenue] = useState<Venue | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/restaurants")
      .then((r) => (r.ok ? r.json() : { restaurants: [] }))
      .then((d: { restaurants: Venue[] }) => {
        setVenues(d.restaurants);
        setVenue(pickVenue(d.restaurants, readStoredSlug()));
      })
      .catch(() => setVenues([]))
      .finally(() => setLoading(false));
  }, []);

  const select = (slug: string) => {
    const next = venues.find((v) => v.slug === slug);
    if (next) {
      storeSlug(slug);
      setVenue(next);
    }
  };

  return <VenueContext.Provider value={{ venues, venue, loading, select }}>{children}</VenueContext.Provider>;
}

export const useVenue = () => useContext(VenueContext);
```

- [ ] **Step 4: Wire it in.**
  - Wrap `(dashboard)/layout.tsx` and `(kitchen)/layout.tsx` content in `<VenueProvider>`.
  - Dashboard `brand`: below "Mise", a `VenueSwitcher` (in the same file): when `venues.length > 1` a native `<select aria-label="Venue">` listing `"{name} · {city}"`, `onChange={(e) => select(e.target.value)}`; otherwise a plain `<span>` with the name and city. Use existing house classes (`text-sm text-ink-muted`), no new colours.
  - In every page with `DEFAULT_SLUG`: delete the constant and `const [slug] = useState(DEFAULT_SLUG)`, use `const { venue } = useVenue(); const slug = venue?.slug;`, and guard effects with `if (!slug) return;` plus `[slug]` in their dependency arrays so switching venue reloads data. While `loading` show the page's existing loading state.
  - Kitchen page: delete its inline PIN login form (around line 169) and its state; on a 401 from any kitchen request, `router.push("/login")`.
  - Login page: replace role/secret with `email` and `password` inputs (`type="email"`, `autoComplete="username"`; `type="password"`, `autoComplete="current-password"`), POST `{email, password}`. Demo buttons: "Enter as demo owner" → `{role: "owner"}` → `/`; "Open kitchen display (demo staff)" → `{role: "staff", venue: "angeethi-house"}` → `/kitchen`. Keep both button labels exactly (e2e uses them).
  - `middleware.test.ts`: the fake cookie value becomes `"00000000-0000-0000-0000-000000000000:9999999999.sig"` (the middleware only checks presence).

- [ ] **Step 5: Run** `pnpm --filter owner-web test` and `pnpm --filter owner-web lint` → pass.

- [ ] **Step 6: Commit** — `feat(owner): email login, venue switcher, no hard-coded slug`

---

# Phase B — Venues, options and tax

### Task 6: Venue fields and menu options schema

**Files:**
- Create: `services/api/alembic/versions/0009_venues_options.py`
- Modify: `src/models/restaurant.py`, `src/models/menu.py`, `src/models/order.py`, `src/routers/restaurants.py` (use `r.city`)
- Test: `tests/test_schema_constraints.py` (append)

- [ ] **Step 1: Failing tests**

```python
async def test_option_price_and_cost_non_negative(db_session):
    import uuid
    from decimal import Decimal
    from sqlalchemy.exc import IntegrityError
    from src.models.menu import MenuItemOption

    rid = await _create_test_restaurant(db_session)
    mid = await _create_test_menu_item(db_session, rid)
    db_session.add(MenuItemOption(menu_item_id=uuid.UUID(mid), label="Half", price=Decimal("-1"), unit_cost=Decimal("0")))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_option_label_unique_per_item(db_session):
    import uuid
    from decimal import Decimal
    from sqlalchemy.exc import IntegrityError
    from src.models.menu import MenuItemOption

    rid = await _create_test_restaurant(db_session)
    mid = uuid.UUID(await _create_test_menu_item(db_session, rid))
    db_session.add(MenuItemOption(menu_item_id=mid, label="Full", price=Decimal("10"), unit_cost=Decimal("4")))
    await db_session.flush()
    db_session.add(MenuItemOption(menu_item_id=mid, label="Full", price=Decimal("11"), unit_cost=Decimal("4")))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run → fail** (`MenuItemOption` missing).

- [ ] **Step 3: Models.**
  - `Restaurant`: `city: Mapped[str | None] = mapped_column(Text, nullable=True)`; `tax_jurisdiction: Mapped[str | None] = mapped_column(Text, nullable=True)`.
  - `menu.py`: new `MenuItemOption` (table `menu_item_option`; `id`, `menu_item_id` FK `menu_item.id` ondelete CASCADE, `label` Text, `price` Numeric(10,2), `unit_cost` Numeric(10,2), `sort_order` Integer default 0, timestamps) with
    `CheckConstraint("price >= 0", name="chk_menu_item_options_price")`, `CheckConstraint("unit_cost >= 0", name="chk_menu_item_options_cost")`, `UniqueConstraint("menu_item_id", "label", name="uq_menu_item_options_label")`, `Index("idx_menu_item_options_item", "menu_item_id")`.
    `MenuItem.options: Mapped[list["MenuItemOption"]] = relationship(lazy="raise", cascade="all, delete-orphan", order_by="MenuItemOption.sort_order")`.
  - `OrderItem`: `option_id` (UUID FK `menu_item_option.id` ondelete SET NULL, nullable), `option_label: Mapped[str | None]` (Text, nullable).
  - Export `MenuItemOption` from `models/__init__.py`.

- [ ] **Step 4: Migration `0009_venues_options.py`** (down_revision `0008_users_memberships`) adding exactly the above; downgrade reverses in reverse order.

- [ ] **Step 5:** `routers/restaurants.py` returns `city=r.city`. Run `make test-py` → green.

- [ ] **Step 6: Commit** — `feat(api): venue city and tax jurisdiction, menu item options`

---

### Task 7: Tax rates and `tax_for`

**Files:**
- Create: `data/tax_rates.json`, `services/api/src/services/tax.py`, `services/api/tests/test_tax.py`
- Modify: `src/main.py` (validate at startup), `src/config.py` (`tax_rates_path: str | None = None`)

- [ ] **Step 1: Data file** — exactly the JSON in the spec ("Tax rates" section), four entries, with the `source` strings.

- [ ] **Step 2: Failing tests** `tests/test_tax.py`:

```python
"""Sales tax by jurisdiction, payment method and date."""

from datetime import date
from decimal import Decimal

import pytest

from src.services.tax import TaxRate, TaxRateError, load_rates, payment_class, tax_for

JULY = date(2026, 7, 1)


def test_payment_classes():
    assert payment_class("cash") == "standard"
    assert payment_class("bank_transfer") == "standard"
    for m in ("card", "wallet", "raast"):
        assert payment_class(m) == "digital"


@pytest.mark.parametrize(
    ("jur", "method", "subtotal", "rate", "tax"),
    [
        ("PB", "cash", "5490", "0.16", "878"),   # 878.40 -> 878
        ("PB", "card", "5490", "0.08", "439"),   # 439.20 -> 439
        ("PB", "bank_transfer", "1000", "0.16", "160"),
        ("ICT", "wallet", "2310", "0.05", "116"),  # 115.50 -> 116 (half up)
        ("ICT", "cash", "2310", "0.15", "347"),    # 346.50 -> 347
    ],
)
def test_tax_for(jur, method, subtotal, rate, tax):
    r, t = tax_for(jur, method, JULY, Decimal(subtotal))
    assert r == Decimal(rate)
    assert t == Decimal(tax)


def test_latest_rate_on_or_before_date_wins():
    rates = [
        TaxRate("PB", "digital", Decimal("0.05"), date(2021, 7, 1), "old"),
        TaxRate("PB", "digital", Decimal("0.08"), date(2026, 7, 1), "new"),
    ]
    assert tax_for("PB", "card", date(2026, 6, 30), Decimal("100"), rates)[0] == Decimal("0.05")
    assert tax_for("PB", "card", date(2026, 7, 1), Decimal("100"), rates)[0] == Decimal("0.08")


def test_no_rate_for_date_raises():
    with pytest.raises(TaxRateError):
        tax_for("PB", "cash", date(2020, 1, 1), Decimal("100"))
    with pytest.raises(TaxRateError):
        tax_for("SD", "cash", JULY, Decimal("100"))


@pytest.mark.parametrize(
    "bad",
    [
        '[{"jurisdiction":"PB","payment_class":"cash","rate":"0.16","effective_from":"2026-07-01","source":"x"}]',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"1.5","effective_from":"2026-07-01","source":"x"}]',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"0.08","effective_from":"2026-07-01","source":"x"},'
        ' {"jurisdiction":"PB","payment_class":"digital","rate":"0.09","effective_from":"2026-07-01","source":"y"}]',
        '{"not": "a list"}',
    ],
)
def test_invalid_files_are_rejected(tmp_path, bad):
    p = tmp_path / "rates.json"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(TaxRateError):
        load_rates(p)
```

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement `src/services/tax.py`**

```python
"""Restaurant sales tax: rates are data (data/tax_rates.json), the calculation is pure."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from src.config import settings

PaymentMethod = Literal["cash", "card", "wallet", "raast", "bank_transfer"]
PaymentClass = Literal["standard", "digital"]
PAYMENT_METHODS: tuple[str, ...] = ("cash", "card", "wallet", "raast", "bank_transfer")
# The reduced rate covers only debit/credit card, mobile wallet and QR scanning (Raast QR).
_DIGITAL = {"card", "wallet", "raast"}


class TaxRateError(ValueError):
    pass


@dataclass(frozen=True)
class TaxRate:
    jurisdiction: str
    payment_class: str
    rate: Decimal
    effective_from: date
    source: str


def payment_class(method: str) -> PaymentClass:
    if method not in PAYMENT_METHODS:
        raise TaxRateError(f"Unknown payment method {method!r}")
    return "digital" if method in _DIGITAL else "standard"


def _default_path() -> Path:
    if settings.tax_rates_path:
        return Path(settings.tax_rates_path)
    here = Path(__file__).resolve()
    # /app/data in the container, <repo>/data in a checkout
    for base in (here.parents[2], here.parents[4] if len(here.parents) > 4 else here.parents[2]):
        candidate = base / "data" / "tax_rates.json"
        if candidate.is_file():
            return candidate
    raise TaxRateError("data/tax_rates.json not found")


def load_rates(path: Path | None = None) -> list[TaxRate]:
    try:
        raw = json.loads((path or _default_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TaxRateError(f"Cannot read tax rates: {e}") from e
    if not isinstance(raw, list) or not raw:
        raise TaxRateError("Tax rates file must be a non-empty list")
    rates: list[TaxRate] = []
    seen: set[tuple[str, str, date]] = set()
    for entry in raw:
        try:
            r = TaxRate(
                jurisdiction=str(entry["jurisdiction"]),
                payment_class=str(entry["payment_class"]),
                rate=Decimal(str(entry["rate"])),
                effective_from=date.fromisoformat(entry["effective_from"]),
                source=str(entry["source"]),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as e:
            raise TaxRateError(f"Bad tax rate entry {entry!r}: {e}") from e
        if r.payment_class not in ("standard", "digital"):
            raise TaxRateError(f"Unknown payment class {r.payment_class!r}")
        if not Decimal("0") <= r.rate <= Decimal("1"):
            raise TaxRateError(f"Rate out of range: {r.rate}")
        key = (r.jurisdiction, r.payment_class, r.effective_from)
        if key in seen:
            raise TaxRateError(f"Duplicate tax rate {key}")
        seen.add(key)
        rates.append(r)
    return rates


@lru_cache(maxsize=1)
def default_rates() -> tuple[TaxRate, ...]:
    return tuple(load_rates())


def jurisdictions(rates: tuple[TaxRate, ...] | list[TaxRate] | None = None) -> set[str]:
    return {r.jurisdiction for r in (rates if rates is not None else default_rates())}


def tax_for(
    jurisdiction: str,
    method: str,
    on_date: date,
    subtotal: Decimal,
    rates: tuple[TaxRate, ...] | list[TaxRate] | None = None,
) -> tuple[Decimal, Decimal]:
    """(rate, tax amount rounded half-up to whole rupees) for a bill settled on on_date."""
    cls = payment_class(method)
    candidates = [
        r for r in (rates if rates is not None else default_rates())
        if r.jurisdiction == jurisdiction and r.payment_class == cls and r.effective_from <= on_date
    ]
    if not candidates:
        raise TaxRateError(f"No tax rate configured for {jurisdiction}/{cls} on {on_date}")
    rate = max(candidates, key=lambda r: r.effective_from).rate
    return rate, (subtotal * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
```

- [ ] **Step 5: Startup validation.** In `main.py`'s `lifespan`, call `default_rates()` before yielding, so a bad file stops startup with the `TaxRateError` message.

- [ ] **Step 6: Run** `pytest tests/test_tax.py -v` → all pass.

- [ ] **Step 7: Commit** — `feat(api): sales tax rates as data with a pure tax_for`

---

### Task 8: Admin CLI for onboarding a client

**Files:**
- Create: `scripts/admin.py`, `services/api/tests/test_admin.py`

- [ ] **Step 1: Failing tests** (call the async functions directly, not the CLI):

```python
"""Onboarding commands."""

import pytest
from sqlalchemy import select

from scripts.admin import AdminError, add_user, create_restaurant
from src.models.restaurant import Restaurant
from src.models.user import Membership, User
from src.passwords import verify_password


async def test_create_restaurant_and_add_owner(db_session):
    r = await create_restaurant(db_session, slug="cafe-x", name="Cafe X", city="Lahore",
                                jurisdiction="PB", currency="PKR", timezone="Asia/Karachi")
    u = await add_user(db_session, email="Boss@CafeX.pk", name="Boss", restaurant_slug="cafe-x",
                       role="owner", password="long-enough-pass")
    assert r.tax_jurisdiction == "PB"
    assert u.email == "boss@cafex.pk"
    assert verify_password("long-enough-pass", u.password_hash)
    m = (await db_session.execute(select(Membership).where(Membership.user_id == u.id))).scalar_one()
    assert m.role == "owner"


async def test_unknown_jurisdiction_is_rejected(db_session):
    with pytest.raises(AdminError, match="No tax rates"):
        await create_restaurant(db_session, slug="cafe-y", name="Y", city="Karachi",
                                jurisdiction="SD", currency="PKR", timezone="Asia/Karachi")


async def test_existing_user_gets_second_membership(db_session):
    await create_restaurant(db_session, slug="a1", name="A1", city="Lahore", jurisdiction="PB",
                            currency="PKR", timezone="Asia/Karachi")
    await create_restaurant(db_session, slug="a2", name="A2", city="Islamabad", jurisdiction="ICT",
                            currency="PKR", timezone="Asia/Karachi")
    u1 = await add_user(db_session, email="s@x.pk", name="S", restaurant_slug="a1", role="staff", password="pw-123456")
    u2 = await add_user(db_session, email="s@x.pk", name="S", restaurant_slug="a2", role="owner", password=None)
    assert u1.id == u2.id


async def test_short_password_rejected(db_session):
    await create_restaurant(db_session, slug="a3", name="A3", city="Lahore", jurisdiction="PB",
                            currency="PKR", timezone="Asia/Karachi")
    with pytest.raises(AdminError, match="at least 8"):
        await add_user(db_session, email="n@x.pk", name="N", restaurant_slug="a3", role="owner", password="short")
```

The test image copies `scripts/` to `/app/scripts`; if `scripts` is not importable as a package, add an empty `scripts/__init__.py`.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `scripts/admin.py`**: `AdminError`; `create_restaurant(db, *, slug, name, city, jurisdiction, currency, timezone)` checks `jurisdiction in tax.jurisdictions()` (else `AdminError("No tax rates for jurisdiction ...")`), checks slug is free, adds `Restaurant(languages=["en"], default_language="en", ...)`, flushes, returns it. `add_user(db, *, email, name, restaurant_slug, role, password)` lower-cases the email, finds or creates the `User` (creating requires `password` with `len >= 8`, else `AdminError("Password must be at least 8 characters")`), adds the `Membership` (AdminError if one exists), flushes. `main()` uses `argparse` subcommands `create-restaurant` and `add-user`; `add-user` reads the password with `getpass.getpass()` (never from argv, never printed), runs inside `async_session_factory()`, commits, and prints only the slug/email. Docstring shows `docker compose exec api python scripts/admin.py add-user --email ... --name ... --restaurant ... --role owner`.

- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat: admin CLI to onboard a client restaurant and its users`

---

### Task 9: Orders with options; menu and kitchen show them

**Files:**
- Create: `services/api/tests/test_options.py`
- Modify: `src/schemas/orders.py`, `src/routers/orders.py`, `src/services/order_snapshot.py`, `src/schemas/guest.py`, `src/routers/guest.py`, `src/schemas/kitchen.py`, `src/routers/kitchen.py`

- [ ] **Step 1: Failing tests** `tests/test_options.py` — build a restaurant, a table, a session (copy the fixture pattern in `test_order_path.py`), a "Chicken Karahi" item (`price=1100`, `unit_cost=500`) with options Half (1100/500) and Full (2100/950), and a "Naan" item without options (60/9):

```python
async def test_menu_lists_options(client, karahi_setup):
    menu = (await client.get("/api/guest/menu")).json()
    karahi = next(i for i in menu["items"] if i["name"] == "Chicken Karahi")
    assert [(o["label"], o["price"]) for o in karahi["options"]] == [("Half", "1100.00"), ("Full", "2100.00")]
    assert "unit_cost" not in karahi["options"][0]


async def test_order_snapshots_option_price(client, karahi_setup):
    s = karahi_setup
    resp = await client.post("/api/orders", json={
        "idempotency_key": "k1",
        "items": [{"menu_item_id": str(s.karahi.id), "option_id": str(s.full.id), "quantity": 1},
                  {"menu_item_id": str(s.naan.id), "quantity": 4}],
        "acknowledge_allergen_risk": True,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "2340.00"
    line = next(i for i in body["items"] if i["menu_item_id"] == str(s.karahi.id))
    assert line["option_label"] == "Full" and line["unit_price"] == "2100.00"


@pytest.mark.parametrize("case", ["missing", "foreign", "unknown", "on_plain_item"])
async def test_bad_options_are_422(client, karahi_setup, case):
    s = karahi_setup
    item = {"menu_item_id": str(s.karahi.id), "quantity": 1}
    if case == "foreign":
        item["option_id"] = str(s.other_item_option.id)   # option of a different dish
    elif case == "unknown":
        item["option_id"] = "00000000-0000-0000-0000-000000000000"
    elif case == "on_plain_item":
        item = {"menu_item_id": str(s.naan.id), "option_id": str(s.full.id), "quantity": 1}
    resp = await client.post("/api/orders", json={"idempotency_key": f"bad-{case}", "items": [item],
                                                  "acknowledge_allergen_risk": True})
    assert resp.status_code == 422


async def test_same_dish_two_sizes_is_not_a_replay(client, karahi_setup):
    s = karahi_setup
    def body(opt):
        return {"idempotency_key": "same-key", "acknowledge_allergen_risk": True,
                "items": [{"menu_item_id": str(s.karahi.id), "option_id": str(opt.id), "quantity": 1}]}
    assert (await client.post("/api/orders", json=body(s.half))).status_code == 201
    assert (await client.post("/api/orders", json=body(s.full))).status_code == 409


async def test_kitchen_ticket_shows_option(client, db_session, karahi_setup):
    ...  # place a Full karahi order, sign in as staff with as_member, GET kitchen orders,
         # assert the line has option_label == "Full"
```

Write the `karahi_setup` fixture as a dataclass-returning fixture in this file (`karahi`, `half`, `full`, `naan`, `other_item_option`, and it sets the guest cookie with `sign_value(str(session.id))`). Fill in the last test fully following the shape of the existing kitchen tests in `test_order_path.py`.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement.**
  - `OrderItemRequest.option_id: uuid.UUID | None = None`. `compute_payload_hash` includes `"option_id": str(i.option_id or "")` and sorts by it too.
  - `create_order`: load items with `selectinload(MenuItem.translations), selectinload(MenuItem.options)`. Before allergen checks, resolve each line's option: `opts = {o.id: o for o in item.options}`; if `item.options` and `req.option_id is None` → 422 `"Choose a size for {item.id}"`; if `req.option_id is not None and req.option_id not in opts` → 422 `"Unknown option for {item.id}"` (covers foreign, unknown and plain items). Use `status.HTTP_422_UNPROCESSABLE_ENTITY`.
  - `snapshot_order_item(..., option: MenuItemOption | None = None)`: when `option` is given, `unit_price=option.price`, `unit_cost=option.unit_cost`, `option_id=option.id`, `option_label=option.label`. Callers that do not pass it keep today's behaviour.
  - `OrderItemResponse` gains `option_id: uuid.UUID | None` and `option_label: str | None`.
  - Guest menu: `GuestMenuOption(id, label, price)`; `GuestMenuItemResponse.options: list[GuestMenuOption] = []`; the query adds `selectinload(MenuItem.options)`.
  - Kitchen: `KitchenOrderItemResponse.option_label: str | None`; set it in `_build_kitchen_order_response`.

- [ ] **Step 4: Run** `pytest tests/test_options.py tests/test_order_path.py -v` → pass. **Step 5:** `make gen-client` needs a running stack; skip here, it is regenerated in Task 18. **Step 6: Commit** — `feat(api): portion options on dishes, orders and kitchen tickets`

---

### Task 10: PKR formatting and the guest size picker

**Files:**
- Modify: `packages/ui/src/format.ts`, `packages/ui/src/format.test.ts`, `apps/guest-web/src/lib/cart.ts`, `apps/guest-web/src/lib/cart.test.ts`, `apps/guest-web/src/app/[lang]/menu/page.tsx`, `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`, guest i18n `en.ts`, `it.ts`, `types.ts`

- [ ] **Step 1: Failing tests.** `format.test.ts`:

```ts
it("formats PKR as whole rupees", () => {
  expect(formatPrice(2100, "PKR").replace(/\s/g, " ")).toBe("Rs 2,100");
  expect(formatPrice(59.6, "PKR").replace(/\s/g, " ")).toBe("Rs 60");
});
it("keeps EUR unchanged", () => {
  expect(formatPrice(13, "EUR")).toBe("€13.00");
});
```

`cart.test.ts`: a line key is `menuItemId + ":" + (optionId ?? "")`; adding Half then Full of one dish gives two lines; adding Full twice gives quantity 2; the cart total uses each line's option price. Read `cart.ts` first and express these in its existing API (add an optional `option?: { id: string; label: string; price: number }` to the add function).

- [ ] **Step 2: Run** `pnpm --filter ui test` and `pnpm --filter guest-web test` → fail.

- [ ] **Step 3: Implement.**
  - `formatPrice`: when `currency === "PKR"`, `new Intl.NumberFormat("en-PK", { style: "currency", currency: "PKR", currencyDisplay: "symbol", minimumFractionDigits: 0, maximumFractionDigits: 0 })`. If Node's ICU prints `PKR` instead of `Rs`, replace a leading `PKR` with `Rs` in that branch (comment: `shortcut: ICU data varies; drop when en-PK symbol is stable`).
  - `cart.ts`: line identity includes the option; lines store `optionId`, `optionLabel`, unit price from the option; the order payload sends `option_id`.
  - Menu page: a dish with `options.length > 0` shows "from {formatPrice(min)}" and its "+" opens a `Sheet` (from `ui`) titled with the dish name, listing each option as a row button `"{label}  {price}"` (`aria-label="Add {name} {label}"`); choosing one adds it and closes the sheet. A dish without options keeps the one-tap "+". Under the restaurant header add the line from i18n `menu.taxNote`: "Prices exclude sales tax, which is added to your bill." Cart lines render `"{name} — {optionLabel}"` when an option is set.
  - Order page: line names include `— {option_label}`.
  - i18n: add `menu.taxNote`, `menu.chooseSize`, `menu.from` to `types.ts`, `en.ts`, `it.ts` (Italian: "I prezzi non includono l'imposta, aggiunta al conto.", "Scegli la porzione", "da"); `i18n.test.ts` checks key parity and stays green.

- [ ] **Step 4: Run** the TS tests and lint → pass. **Step 5: Commit** — `feat(guest): size picker, PKR prices and tax note`

---

### Task 11: Two Pakistani demo venues and demo users

**Files:**
- Create: `data/seed/angeethi_house.json`, `data/seed/kehwa_and_crumb.json`, `data/seed/demo_users.json`
- Delete: `data/seed/trattoria_da_mario.json`
- Modify: `scripts/seed.py`, `data/seed/README.md`, `src/routers/demo.py`, `src/schemas/auth.py` (`DemoInfoResponse`), `src/schemas/guest.py` (session language default `"en"`), `tests/test_seed.py`, `tests/test_demo.py`, any test using `trattoria-da-mario` or Italian names (`grep -rn "trattoria\|Tavolo\|it\"\]" services/api/tests`)

- [ ] **Step 1: Seed files.** Same top-level shape as the Italian file plus:
  - `"restaurant"` adds `"city"`, `"tax_jurisdiction"`; `"currency": "PKR"`, `"timezone": "Asia/Karachi"`, `"languages": ["en"]`, `"default_language": "en"`.
  - `"_note": "Fictional venue. Prices and costs are illustrative (2025-26 ranges), not quotes."`
  - Each item: `key`, `category`, `price` (cheapest option when it has options), `unit_cost`, `ingredients`, `allergens`, `"allergen_verified": false`, dietary flags with `"dietary_verified": false`, `sort_order`, `"translations": {"en": {...}}`, optional `"options": [{"label", "price", "unit_cost"}]`, `"sim_weight"` (relative popularity), optional `"option_weights"` (same length as options).
  - A top-level `"simulation"` block (used in Task 16).
  - **Angeethi House** (`angeethi-house`, Lahore, PB): tables `T1`…`T8`, `F1`…`F4`. Items (price PKR / unit cost, options, sim_weight):
    - BBQ: Chicken Tikka (per piece 850/380, w 6), Seekh Kebab (4 pcs 1200/540, w 5), Malai Boti (half plate 950/430, full plate 1800/810, w 5)
    - Karahi: Chicken Karahi (½ kg 1100/500, 1 kg 2100/950, weights 0.55/0.45, w 10), Mutton Karahi (½ kg 2300/1060, 1 kg 4500/2070, w 5), Chicken White Karahi (½ kg 1250/560, 1 kg 2400/1080, w 3)
    - Handi: Boneless Chicken Handi (Half 1050/470, Full 1950/880, w 6), Makhni Handi (Half 1150/500, Full 2150/950, w 4)
    - Daal & Sabzi: Daal Mash (520/110, w 4), Mix Sabzi (480/110, w 2), Palak Paneer (750/260, w 2)
    - Rice: Chicken Biryani (Single 450/170, Double 820/310, w 7), Mutton Pulao (Single 650/290, Double 1200/540, w 3)
    - Tandoor: Roti (40/6, w 14), Naan (60/9, w 16), Garlic Naan (150/28, w 6), Cheese Naan (450/120, w 3)
    - Sides: Raita (150/30, w 8), Fresh Salad (200/45, w 6)
    - Desserts: Kheer (350/90, w 3), Gulab Jamun (2 pcs 300/70, w 3)
    - Drinks: Sweet Lassi (450/90, w 4), Fresh Lime (350/60, w 4), Soft Drink (Regular 150/70, 1.5 L 380/200, w 6), Mineral Water (Small 100/45, Large 180/85, w 7), Doodh Patti Chai (250/45, w 4)
  - **Kehwa & Crumb** (`kehwa-and-crumb`, Islamabad, ICT): tables `T1`…`T8`. Items:
    - Hot Coffee: Americano (Regular 550/120, Large 680/150, w 6), Cappuccino (650/190, 790/240, w 9), Café Latte (690/200, 820/250, w 8), Spanish Latte (790/250, 950/300, w 9)
    - Iced: Iced Latte (750/220, 900/270, w 8), Caramel Frappé (950/300, 1150/360, w 6), Iced Spanish Latte (880/270, 1050/320, w 6)
    - Chai & Kehwa: Karak Chai (350/60, w 7), Kashmiri Chai (450/110, w 4), Green Kehwa (300/40, w 3)
    - Bakery: Butter Croissant (450/140, w 6), Almond Croissant (620/210, w 4), Fudge Brownie (495/150, w 6), Banana Bread (420/120, w 3)
    - Breakfast: Buttermilk Pancakes (650/190, w 3), French Toast (595/170, w 3), Chicken Club Sandwich (950/360, w 5), Chicken Pesto Melt (1100/420, w 4)
    - Desserts: New York Cheesecake (850/300, w 4), Molten Lava Cake (790/250, w 4)
    - Cold: Fresh Orange Juice (650/220, w 2), Mineral Water (Small 100/45, w 3)
  - Allergens per standard recipe: dairy items (`milk`), breads/bakery (`gluten`), croissants/cakes/pancakes (`gluten`, `milk`, `eggs`), almond croissant adds `nuts`, pesto adds `nuts`, kheer adds `nuts`, raita (`milk`). Use the allergen codes the API already accepts (check `EU14Allergen` in `schemas/guest.py`).
  - `demo_users.json`: `{"owner": {"email": "demo-owner@mise.demo", "name": "Demo owner", "venues": ["angeethi-house", "kehwa-and-crumb"]}, "staff": [{"email": "demo-staff+angeethi-house@mise.demo", "name": "Demo staff (Angeethi)", "venue": "angeethi-house"}, {"email": "demo-staff+kehwa-and-crumb@mise.demo", "name": "Demo staff (Kehwa)", "venue": "kehwa-and-crumb"}]}`.

- [ ] **Step 2: Failing tests** in `test_seed.py` (keep its existing structure, replace Italian expectations):
  - seeding both files twice leaves 2 restaurants, item and option counts unchanged, stable UUIDs (`uuid5(ns, "angeethi-house:chicken_karahi")` and `uuid5(ns, "angeethi-house:chicken_karahi:1 kg")`);
  - Angeethi's Chicken Karahi has options `["½ kg", "1 kg"]` and `price == 1100`;
  - `seed_demo_users` creates the owner with memberships in both venues and each staff user in one venue only; running it twice changes nothing;
  - seeding an option no longer in the file deletes that option.
  In `test_demo.py`: `/api/demo/info` lists both venues, each with a `qr_token` and `table_label`; demo-login staff with `venue="kehwa-and-crumb"` can read Kehwa's kitchen and gets 404 on Angeethi's.

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement.**
  - `seed.py`: default `--file` becomes repeatable (`action="append"`), defaulting to both venue files; add `--demo-users data/seed/demo_users.json` (applied only when the flag is given or `settings.demo_mode` is true). Item identity is `item_data["key"]` only (delete the Italian-name fallback). Upsert `city`, `tax_jurisdiction`. Upsert options by `uuid5(ns, f"{slug}:{key}:{label}")`, delete options not in the file, keep `MenuItem.price/unit_cost` equal to the cheapest option. Load items with `selectinload(MenuItem.translations), selectinload(MenuItem.options)`. `seed_demo_users(data, session)` creates users with a random unusable password (`hash_password(secrets.token_urlsafe(32))`) — demo users sign in only through demo-login — and memberships idempotently.
  - `DemoInfoResponse` becomes `{"owner_url", "kitchen_url", "venues": [{"slug", "name", "city", "guest_url", "qr_token", "table_label"}]}`; `/api/demo/info` returns the first table (by label) of each slug in `settings.demo_restaurant_slugs` that exists.
  - `CreateGuestSessionRequest.language` default `"en"`.
  - Delete the Italian seed and update `data/seed/README.md`.

- [ ] **Step 5: Run** `make test-py` → green (other tests that used the Italian seed now use the new files or their own fixtures). **Step 6: Commit** — `feat: Angeethi House and Kehwa & Crumb demo venues replace the Italian demo`

---

# Phase C — Bills

### Task 12: Bills table and orders join a table's open bill

**Files:**
- Create: `src/models/bill.py`, `alembic/versions/0010_bills.py`, `src/services/bills.py`, `tests/test_bills.py`
- Modify: `src/models/order.py`, `src/models/__init__.py`, `src/routers/orders.py`

- [ ] **Step 1: Failing tests** (`tests/test_bills.py`; reuse a venue fixture with `tax_jurisdiction="PB"` and two tables, and a guest session per table):

```python
async def test_first_order_opens_bill_and_second_joins_it(client, venue):
    o1 = await place(client, venue.session_t1, [(venue.naan, 2)])
    o2 = await place(client, venue.session_t1, [(venue.naan, 1)])
    b1, b2 = await bill_id_of(o1), await bill_id_of(o2)
    assert b1 == b2


async def test_tables_get_separate_bills_with_increasing_numbers(client, db_session, venue):
    await place(client, venue.session_t1, [(venue.naan, 1)])
    await place(client, venue.session_t2, [(venue.naan, 1)])
    nos = sorted((await db_session.execute(select(Bill.bill_no).where(Bill.restaurant_id == venue.r.id))).scalars())
    assert nos == [1, 2]


async def test_one_open_bill_per_table_is_enforced(db_session, venue):
    db_session.add(Bill(restaurant_id=venue.r.id, table_id=venue.t1.id, bill_no=90, status="open", source="live"))
    db_session.add(Bill(restaurant_id=venue.r.id, table_id=venue.t1.id, bill_no=91, status="open", source="live"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_live_bill_needs_a_number(db_session, venue):
    db_session.add(Bill(restaurant_id=venue.r.id, table_id=venue.t1.id, bill_no=None, status="open", source="live"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

`place` posts `/api/orders` with the session's cookie and returns the order id; `bill_id_of` reads `Order.bill_id`. Define both helpers in the test file.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Model `Bill`** (`bills`): `id`, `restaurant_id` (FK CASCADE), `table_id` (FK `dining_table.id` SET NULL, nullable), `bill_no` Integer nullable, `status` Text default `'open'`, `source` Text default `'live'`, `bill_requested_at`, `payment_method` Text nullable, `payment_reference` Text nullable, `subtotal`/`tax_rate`/`tax_amount`/`total` Numeric nullable (`tax_rate` Numeric(5,4), others Numeric(10,2)), `tax_jurisdiction` Text nullable, `opened_at` (server now), `settled_at` nullable, `created_at`, `updated_at`. `__table_args__`:
  - `CheckConstraint("status IN ('open', 'settled')", name="chk_bills_status")`
  - `CheckConstraint("source IN ('live', 'simulated')", name="chk_bills_source")`
  - `CheckConstraint("payment_method IS NULL OR payment_method IN ('cash','card','wallet','raast','bank_transfer')", name="chk_bills_payment_method")`
  - `CheckConstraint("source = 'simulated' OR bill_no IS NOT NULL", name="chk_bills_live_number")`
  - `CheckConstraint("status = 'open' OR (payment_method IS NOT NULL AND total IS NOT NULL AND settled_at IS NOT NULL)", name="chk_bills_settled_complete")`
  - `CheckConstraint("payment_reference IS NULL OR length(payment_reference) <= 64", name="chk_bills_reference_len")`
  - `UniqueConstraint("restaurant_id", "bill_no", name="uq_bills_restaurant_bill_no")`
  - `Index("uq_bills_one_open_per_table", "table_id", unique=True, postgresql_where=text("status = 'open'"))`
  - `Index("idx_bills_restaurant_status", "restaurant_id", "status", "opened_at")`
  `Order.bill_id` (FK `bills.id` SET NULL, nullable) + `Index("idx_orders_bill_id", "bill_id")` in `Order.__table_args__`. Migration `0010_bills.py` mirrors all of it (down_revision `0009_venues_options`).

- [ ] **Step 4: `services/bills.py` — opening**

```python
async def open_bill_for_table(db: AsyncSession, restaurant_id: uuid.UUID, table_id: uuid.UUID) -> Bill:
    """The table's open bill, locked FOR UPDATE, or a new one. Caller owns the transaction."""
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bill:{restaurant_id}"))))
    bill = (
        await db.execute(
            select(Bill).where(Bill.table_id == table_id, Bill.status == "open").with_for_update()
        )
    ).scalar_one_or_none()
    if bill is not None:
        return bill
    last = (
        await db.execute(select(func.max(Bill.bill_no)).where(Bill.restaurant_id == restaurant_id))
    ).scalar_one()
    bill = Bill(restaurant_id=restaurant_id, table_id=table_id, bill_no=(last or 0) + 1,
                status="open", source="live")
    db.add(bill)
    await db.flush()
    return bill
```

  In `create_order`, after validation and before building `Order`: `bill = await open_bill_for_table(db, session.restaurant_id, session.table_id) if session.table_id else None`, and `Order(..., bill_id=bill.id if bill else None)`. A new bill publishes `{"event": "bill_opened", "bill_id": ...}` on `kitchen:{restaurant_id}` after commit (remember whether it was new via a flag returned alongside: change the function to return `(bill, created)`).

- [ ] **Step 5: Run → pass;** `make test-py` green. **Step 6: Commit** — `feat(api): table bills; orders join the open bill`

---

### Task 13: Bill list, detail, settle; guest request and status

**Files:**
- Create: `src/schemas/bills.py`, `src/routers/bills.py`
- Modify: `src/services/bills.py`, `src/routers/guest.py`, `src/main.py`, `tests/test_bills.py`

- [ ] **Step 1: Failing tests** (append):

```python
async def test_detail_groups_lines_and_previews_both_rates(client, db_session, venue):
    await place(client, venue.session_t1, [(venue.karahi, 1, venue.full), (venue.naan, 4)])
    await place(client, venue.session_t1, [(venue.naan, 2)])
    await as_member(client, db_session, venue.r.id, "staff")
    bill = (await client.get(f"/api/restaurants/{venue.r.slug}/bills?status=open")).json()["bills"][0]
    d = (await client.get(f"/api/restaurants/{venue.r.slug}/bills/{bill['id']}")).json()
    assert [(l["name"], l["option_label"], l["quantity"]) for l in d["lines"]] == [
        ("Chicken Karahi", "Full", 1), ("Naan", None, 6)]
    assert d["subtotal"] == "2460.00"
    assert d["preview_standard"] == {"payment_class": "standard", "tax_rate": "0.16", "tax_amount": "394.00", "total": "2854.00"}
    assert d["preview_digital"] == {"payment_class": "digital", "tax_rate": "0.08", "tax_amount": "197.00", "total": "2657.00"}


async def test_settle_by_card_snapshots_tax_and_next_order_opens_new_bill(client, db_session, venue):
    ...  # place, sign in staff, POST settle {"payment_method": "card", "payment_reference": "AUTH123"},
         # assert 200, status settled, tax_rate 0.08, total = subtotal + tax, settled_at set;
         # settle again -> 409; place another order on T1 -> different bill_id with bill_no + 1


async def test_settle_validation(client, db_session, venue):
    ...  # reference of 65 chars -> 422; unknown method -> 422;
         # bill whose only order is cancelled -> 422 "No active orders"


async def test_no_tax_rate_keeps_bill_open(client, db_session, venue, monkeypatch):
    ...  # monkeypatch src.services.bills.default_rates to return () ; settle -> 422
         # "No tax rate configured"; bill still open


async def test_guest_request_bill_and_status(client, db_session, venue):
    ...  # GET /api/guest/bill before ordering -> 404; place; POST /api/guest/bill-request -> 200
         # with bill_requested_at; repeat -> 200 same timestamp; GET /api/guest/bill -> status open,
         # bill_no; staff list shows bill_requested_at and requested bills sort first;
         # after settle GET /api/guest/bill -> status settled


async def test_parallel_settle_and_order(...):
    ...  # with two independent AsyncClients on committed data (copy the pattern in
         # test_simulator_concurrency.py): fire settle and a new order together 10 times;
         # every order ends on exactly one bill, no order is attached to a settled bill whose
         # settled_at precedes the order's placed_at, and no IntegrityError surfaces.
```

Fill in every `...` body completely before running — they are summaries of required assertions, not placeholders to ship.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Schemas** (`schemas/bills.py`): `BillLine(name, option_label: str | None, quantity: int, unit_price: Decimal, line_total: Decimal)`; `TaxPreview(payment_class: Literal["standard","digital"], tax_rate: Decimal, tax_amount: Decimal, total: Decimal)`; `BillSummary(id, bill_no: int | None, table_label: str | None, status, opened_at, order_count: int, subtotal: Decimal, bill_requested_at: datetime | None)`; `BillListResponse(bills: list[BillSummary])`; `BillDetail(BillSummary + lines, preview_standard: TaxPreview | None, preview_digital: TaxPreview | None, payment_method, payment_reference, tax_jurisdiction, tax_rate, tax_amount, total, settled_at, restaurant_name, restaurant_city, currency)`; `SettleBillRequest(payment_method: Literal["cash","card","wallet","raast","bank_transfer"], payment_reference: str | None = Field(default=None, max_length=64))`; `GuestBillResponse(bill_no: int | None, status, bill_requested_at)`. Decimal fields serialise as strings like the rest of the API.

- [ ] **Step 4: Service functions** in `services/bills.py`:
  - `active_orders(db, bill_id)` → orders with `status != 'cancelled'`, items eager-loaded.
  - `bill_lines(orders)` → group by `(item_name, option_label, unit_price)`, sum quantities, keep first-seen order; `subtotal = sum(line_total)`.
  - `previews(jurisdiction, subtotal, on_date)` → `(standard, digital)` using `tax_for(jur, "cash", ...)` and `tax_for(jur, "card", ...)`; on `TaxRateError` return `None` for that preview.
  - `settle_bill(db, bill_id, restaurant, method, reference, now)` → lock `select(Bill).where(id, restaurant_id).with_for_update()`; 404 if missing; 409 if settled; 422 if no active orders; `rate, tax = tax_for(restaurant.tax_jurisdiction, method, now.astimezone(ZoneInfo(restaurant.timezone)).date(), subtotal)` → on `TaxRateError` log and raise 422 "No tax rate configured" (the transaction is rolled back, the bill stays open); snapshot fields; `settled_at = now`.
- [ ] **Step 5: Routes** (`routers/bills.py`, prefix `/api/restaurants/{slug}/bills`, staff or owner): `GET ""` (`status: Literal["open","settled"] = "open"`, open bills ordered by `bill_requested_at IS NULL, opened_at`; settled by `settled_at desc` limit 50), `GET "/{bill_id}"`, `POST "/{bill_id}/settle"` (commits, then publishes `bill_settled`). Guest routes in `guest.py`: `POST /api/guest/bill-request` (open bill of `session.table_id`; 404 "No open bill"; set `bill_requested_at` only if null; commit; publish `bill_requested` on `kitchen:{restaurant_id}`) and `GET /api/guest/bill` (bill of the session's latest order with a bill; 404 otherwise). Register the router.

- [ ] **Step 6: Run** `pytest tests/test_bills.py tests/test_restaurant_isolation.py -v` → pass (the isolation test now also covers the bill routes). **Step 7: Commit** — `feat(api): bills list, detail with tax previews, settle and guest bill request`

---

### Task 14: Bills page and sample bill (owner app); Request bill (guest app)

**Files:**
- Create: `apps/owner-web/src/lib/bill.ts`, `apps/owner-web/src/lib/bill.test.ts`, `apps/owner-web/src/app/(dashboard)/bills/page.tsx`, `apps/owner-web/src/app/bills/[id]/print/page.tsx`
- Modify: `apps/owner-web/src/app/(dashboard)/layout.tsx` (nav), `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`, guest i18n files

- [ ] **Step 1: Failing test** `bill.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { PAYMENT_METHODS, SAMPLE_BILL_FOOTER, billNo, sampleBillText } from "./bill";

describe("sample bill", () => {
  const bill = {
    restaurant_name: "Angeethi House", restaurant_city: "Lahore", currency: "PKR", bill_no: 42,
    table_label: "T3", settled_at: "2026-10-24T15:30:00Z", status: "settled",
    lines: [{ name: "Chicken Karahi", option_label: "1 kg", quantity: 1, unit_price: "2100.00", line_total: "2100.00" }],
    subtotal: "2100.00", tax_rate: "0.08", tax_amount: "168.00", total: "2268.00", payment_method: "card",
  };
  it("always carries the not-a-tax-invoice footer", () => {
    expect(SAMPLE_BILL_FOOTER).toBe("Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority.");
    expect(sampleBillText(bill)).toContain(SAMPLE_BILL_FOOTER);
  });
  it("never says invoice outside the footer", () => {
    const withoutFooter = sampleBillText(bill).replace(SAMPLE_BILL_FOOTER, "");
    expect(withoutFooter.toLowerCase()).not.toContain("invoice");
    expect(withoutFooter).not.toMatch(/FBR|compliant|integrated/i);
  });
  it("labels tax as illustrative with rate and class", () => {
    expect(sampleBillText(bill)).toContain("Sales tax (illustrative) 8% — card, wallet or QR");
  });
  it("pads bill numbers", () => {
    expect(billNo(42)).toBe("Bill no. 0042");
  });
  it("offers the five payment methods", () => {
    expect(PAYMENT_METHODS.map((m) => m.value)).toEqual(["cash", "card", "wallet", "raast", "bank_transfer"]);
  });
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: `bill.ts`** exports the `BillDetail` type (mirroring the API), `SAMPLE_BILL_FOOTER`, `PAYMENT_METHODS` (`cash` "Cash", `card` "Card", `wallet` "JazzCash / Easypaisa", `raast` "Raast QR", `bank_transfer` "Bank transfer"), `billNo(n)`, `taxLabel(rate, method)` → `"Sales tax (illustrative) {pct}% — {cash: "cash", bank_transfer: "bank transfer", else: "card, wallet or QR"}"`, and `sampleBillText(bill)` → the bill as plain lines (venue, city, bill no., date/time in `Asia/Karachi`, table, each line `"{qty} × {name}{ — option}  {formatPrice}"`, subtotal, tax label + amount, total, payment method, footer). The print page renders the same pieces as markup; the test guards the wording.

- [ ] **Step 4: Bills page** (`(dashboard)/bills/page.tsx`, nav item "Bills" first in the "Service" group):
  - Loads `GET /api/restaurants/{slug}/bills?status=open`; subscribes to the kitchen SSE stream with the existing `use-sse` hook and reloads on `bill_opened`, `bill_requested`, `bill_settled`, `order_placed`.
  - Each row: table label, `billNo`, opened time, order count, `formatPrice(subtotal, currency)`, and a `StatusChip`/`Badge` "Bill requested" (terracotta) when `bill_requested_at` is set.
  - Selecting a row opens a `Sheet` with the detail: grouped lines, subtotal, two side-by-side `Card`s "Cash or bank transfer" and "Card, wallet or QR" with rate, tax and total (or "No tax rate configured" when a preview is null); a radio group of `PAYMENT_METHODS`; an optional reference input (`maxLength={64}`, hidden for cash); a primary `Button` "Mark paid". On success navigate to `/bills/{id}/print`; on 409 reload; show API errors inline.
- [ ] **Step 5: Print page** (`app/bills/[id]/print/page.tsx`, outside the dashboard layout, inside `VenueProvider`): fetches the bill; unsettled → "Not settled yet"; settled → an 80 mm column (`max-w-[80mm] mx-auto font-mono text-sm`, `@media print` hides the "Print" button) with the `sampleBillText` pieces and the footer in bold; a "Print" button calls `window.print()`. No QR code, no logo other than the Mise mark.
- [ ] **Step 6: Guest order page:** below the status, a "Request bill" `Button` (`POST /api/guest/bill-request`); poll `GET /api/guest/bill` every 10 s while open; show i18n `bill.requested` ("Bill requested — a waiter will bring it to your table.") or `bill.paid` ("Paid · {billNo} · thank you"). Add the keys to `types.ts`, `en.ts`, `it.ts`.
- [ ] **Step 7: Run** owner-web and guest-web tests + lint → pass. **Step 8: Commit** — `feat(web): Bills page, printable sample bill and guest bill request`

---

# Phase D — Simulator, analytics, scripts, docs

### Task 15: Currency-neutral analytics fields

**Files:**
- Modify: `src/services/analytics.py`, `src/services/brief.py`, `src/services/whatif.py`, `src/services/narrative.py` (only if it names `_eur` keys), `src/schemas/owner.py`, `tests/test_analytics_api.py`, `tests/test_analytics_pure.py`, `apps/owner-web/src/lib/analytics.ts`, `analytics.test.ts`, `(dashboard)/brief/page.tsx`, `(dashboard)/ai/page.tsx`

- [ ] **Step 1: Change tests first.** In both Python analytics test files rename keys: `revenue_eur→revenue`, `aov_eur→aov`, `contribution_margin_eur→contribution_margin`, `unit_margin_eur→unit_margin`, `contribution_eur→contribution`, `median_unit_margin_eur→median_unit_margin`, `estimated_impact_eur_per_week→estimated_impact_per_week`, `margin_eur→margin`, `price_eur→price`, `unit_cost_eur→unit_cost`; add an assertion that the brief response has `"currency": "PKR"` for a PKR restaurant and that the template summary contains `"PKR "` and not `"EUR"`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Rename** throughout the services and schemas (`grep -rn "_eur" services/api/src` must return nothing afterwards). Template sentences use `restaurant.currency` (`f"{cur} {k['revenue']}"`); pass `currency` into the template builder. `DailyBriefResponse` and `WhatIfResponse` gain `currency: str`. The number-consistency check is unchanged (it compares numbers, not units).
- [ ] **Step 4: Web.** `analytics.ts`: rename the type fields, delete `eur()`, add `money(v, currency)` → `formatPrice(v, currency)`; pages pass `brief.currency`. `analytics.test.ts` updated accordingly.
- [ ] **Step 5: Run** `make test-py`, `pnpm -r test` → green. **Step 6: Commit** — `refactor: currency-neutral analytics fields (PKR venues)`

---

### Task 16: Simulator — venue profiles, weights, options and bills

**Files:**
- Create: `tests/test_simulator_bills.py`
- Modify: `src/services/simulator.py`, `src/routers/owner.py` (simulate endpoints pass the profile), `scripts/simulate.py`, `src/models/restaurant.py` (no change expected — profile lives in `onboarding`, see below), `docs/analytics.md`

- [ ] **Step 1: Where the profile lives.** `scripts/seed.py` stores the seed file's `"simulation"` block into `restaurant.onboarding["simulation"]` (the JSONB column exists). `SimAssumptions` gains `payment_mix: tuple[tuple[str, float], ...] = (("cash", 0.6), ("card", 0.2), ("wallet", 0.15), ("raast", 0.05))` and `settle_minutes: tuple[int, int] = (45, 75)`. `SimAssumptions.from_profile(profile: dict) -> SimAssumptions` builds it (lists → tuples, unknown keys rejected with `ValueError`).
  Angeethi `simulation`: `{"lunch_rate": [9,9,10,10,13,18,16], "dinner_rate": [14,15,15,17,26,30,22], "lunch_hours": [13,16], "dinner_hours": [20,23], "party_size_weights": [0.05,0.20,0.15,0.30,0.15,0.15], "dishes_per_guest": 1.6, "payment_mix": [["cash",0.6],["card",0.2],["wallet",0.15],["raast",0.05]]}`.
  Kehwa `simulation`: `{"lunch_rate": [12,12,13,14,16,22,20], "dinner_rate": [16,16,18,20,26,30,24], "lunch_hours": [15,18], "dinner_hours": [20,23], "party_size_weights": [0.35,0.40,0.15,0.10,0,0], "dishes_per_guest": 1.5, "payment_mix": [["cash",0.35],["card",0.4],["wallet",0.15],["raast",0.1]]}`.
- [ ] **Step 2: Failing tests** `tests/test_simulator_bills.py`:
  - `generate_orders` with per-item weights: over 56 days, the item with the largest weight is the most ordered; same seed → identical output; option choice follows `option_weights` within ±5 percentage points.
  - `persist_simulation` on a seeded Angeethi: every simulated order has a `bill_id`; bills are `source="simulated"`, `bill_no IS NULL`, `status="settled"`, `settled_at` 45–75 min after the order; tax equals `tax_for("PB", method, settled local date, subtotal)`; payment-method shares within ±5 points of the mix; re-running replaces (bill count unchanged, no orphan bills).
- [ ] **Step 3: Run → fail.**
- [ ] **Step 4: Implement.**
  - `generate_orders(items: list[SimItem], start, a, tz)` where `SimItem(id, weight, options: list[tuple[uuid.UUID, float]])`; popularity from `weight` (drop `popularity_ranking` for item order; keep the function for the promotion item: the promo item is the item at `promo_item_rank` in descending-weight order). Lines key by `(item_id, option_id | None)`. Each `SimOrder` gets `payment_method` drawn from `payment_mix` and `settle_after` minutes from `settle_minutes`, using the same seeded RNG after the existing draws so earlier fields keep their determinism.
  - `persist_simulation`: load items with options and read `sim_weight`/`option_weights` from a new nullable column? **No** — keep weights out of the database: the seed writes them into `restaurant.onboarding["simulation"]["weights"] = {item_key: weight}` and `["option_weights"] = {item_key: [..]}`; `persist_simulation` maps item keys via `uuid5(SEED_ITEM_NAMESPACE, f"{slug}:{key}")` (move `SEED_ITEM_NAMESPACE` to `src/services/simulator.py` and import it in `seed.py`). Items without a weight get weight 1.
  - For each simulated party: create a `Bill(source="simulated", bill_no=None, status="settled", table_id=None, opened_at=placed_at, settled_at=placed_at+settle_after, payment_method, subtotal, tax_*)` using `tax_for`; snapshot lines with `option=`; `Order.bill_id`.
  - `clear_simulated` also deletes `Bill` rows with `source='simulated'` for the restaurant (after deleting orders).
  - Owner simulate endpoints build `SimAssumptions.from_profile(restaurant.onboarding.get("simulation", {}))` and then apply the request overrides as today. `scripts/simulate.py` defaults to both demo slugs.
  - `docs/analytics.md`: document the profiles, weights and the **payment mix as an assumption** (no published breakdown for Pakistani restaurants).
- [ ] **Step 5: Run** `make test-py` → green (existing simulator tests updated for the new `generate_orders` signature; say so in the commit). **Step 6: Commit** — `feat(api): venue simulation profiles with options and settled bills`

---

### Task 17: Brief — portion rows and payment mix

**Files:**
- Modify: `src/services/analytics.py`, `src/services/brief.py`, `src/schemas/owner.py`, `tests/test_analytics_api.py`, `tests/test_analytics_pure.py`, `apps/owner-web/src/lib/analytics.ts`, `(dashboard)/brief/page.tsx`

- [ ] **Step 1: Failing tests.**
  - Menu engineering after simulating Angeethi contains separate rows `"Chicken Karahi — ½ kg"` and `"Chicken Karahi — 1 kg"`; each row's `item_id` is the menu item id and it has an `option_id`.
  - `payment_mix` block on known data (build 4 settled live bills: cash 1000 @16% = 160, card 2000 @8% = 160, wallet 1000 @8% = 80, bank_transfer 500 @16% = 80) → `{"bills": {"standard": 2, "digital": 2}, "revenue_share": {"standard": 0.3333, "digital": 0.6667}, "tax_by_rate": [{"rate": "0.08", "tax": "240.00"}, {"rate": "0.16", "tax": "240.00"}], "digital_tax_saving": "240.00"}` (saving = digital subtotal 3000 × (0.16 − 0.08) = 240, computed per bill with the standard rate in force on its settle date).
  - The brief summary (template path) mentions the digital share and saving using only those numbers; the existing number-consistency check passes.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement.** In `analytics.py` the per-item queries group by `oi.menu_item_id, oi.option_id` and carry `oi.option_label`; display name `f"{name} — {label}"` when a label exists. Forecast stays per menu item (sum options) — note it in a code comment. New `payment_mix(db, w, restaurant)` over bills settled in the window (`source` filter same as orders), computing shares in Python with `Decimal`, `digital_tax_saving = Σ digital bills (tax_for(jur, "cash", settled_date, subtotal).tax − tax_amount)`. Add it to the brief facts, the response schema (`PaymentMix` model) and the template sentence. The LLM prompt receives the same numbers it already receives plus these; no personal data.
- [ ] **Step 4: Web.** Brief page gets a "Payments and tax" `Card` with two `StatTile`s (digital share of revenue, tax saved by digital payments) and a two-row table of tax by rate.
- [ ] **Step 5: Run** all tests → green. **Step 6: Commit** — `feat: brief shows portion mix and payment mix with tax`

---

### Task 18: Scripts, browser tests, docs and full verification

**Files:**
- Modify: `e2e/flows.spec.ts`, `scripts/verify_phase1.sh`, `scripts/verify_d.sh`, `scripts/simulate.py`, `README.md`, `docs/architecture.md`, `docs/analytics.md`, `CLAUDE.md`, `packages/api-client` (regenerated)

- [ ] **Step 1: Browser tests.** Rewrite `e2e/flows.spec.ts` (keep the serial-story structure and screenshots):
  1. `beforeAll`: demo-login staff for `angeethi-house`, bump open tickets, settle open bills by cash (via API) so the story starts clean.
  2. Guest at Angeethi: `/api/demo/info` → `venues[0]`; open `/q/{qr_token}` → "View Menu" → heading "Angeethi House", "Table: {label}", tax note visible; tap `Add Chicken Karahi` → sheet → `Add Chicken Karahi 1 kg`; add Naan; View order → Confirm (ack allergen if shown) → "Received by Kitchen"; tap "Request bill" → "Bill requested" text. Screenshot `guest-menu-phone.png`, `size-sheet-phone.png`.
  3. Kitchen (demo staff Angeethi): one BUMP; the line shows "1 kg".
  4. Bills (same staff session): `/bills` shows the "Bill requested" chip; open it, both previews visible ("16%" and "8%"), choose Card, reference "AUTH1", Mark paid → print page shows "Bill no.", "Sales tax (illustrative) 8%", the footer; screenshot `sample-bill.png`. Guest page then shows "Paid".
  5. Owner: demo owner → venue switcher lists both; switch to Kehwa & Crumb → header shows it; `/brief` shows "Revenue Brief" and "Payments and tax".
  6. Café: guest at Kehwa orders a Cappuccino Regular → demo staff Kehwa kitchen shows it.
  7. Isolation: demo staff Kehwa context requests `GET /api/restaurants/angeethi-house/kitchen/orders` → 404.
- [ ] **Step 2: Scripts.** `verify_phase1.sh`: `SLUG=angeethi-house`; seed both venues plus demo users; simulate both; the brief/what-if step checks `currency == "PKR"`; the "live order survives" step places an order through the guest API, settles its bill and checks the bill exists after re-simulation; edge-proxy step unchanged. `verify_d.sh`: demo-login only, new slug. `simulate.py`: both slugs.
- [ ] **Step 3: Docs.**
  - `CLAUDE.md`: under Architecture add "Auth is per user; restaurant routes use `restaurant_access` and answer 404 to non-members." and "Demo bills never imitate a tax invoice: no fiscal number, QR code, authority logo, 'invoice', 'FBR integrated' or 'compliant'." Cookies line: `mise_auth` (signed user id). Leave the language rule for priority 3.
  - `README.md` and `docs/architecture.md`: replace OWNER_API_KEY/STAFF_PIN with users, memberships, `scripts/admin.py` onboarding, demo users; describe venues, options, bills, tax data file and its sources; only what is implemented and tested.
  - `docs/analytics.md`: payment mix block, portion rows, simulation profiles and their assumptions.
- [ ] **Step 4: Regenerate the API client** with the stack up: `LLM_PROVIDER=mock DEMO_MODE=true make up && make migrate && make seed && make gen-client`; commit the generated files.
- [ ] **Step 5: Full verification.** `LLM_PROVIDER=mock DEMO_MODE=true make verify-f` → all 10 steps pass; `make ci` → green; `bash scripts/check_branding.sh` → clean. Fix anything red at its root cause before continuing.
- [ ] **Step 6: Commit** — `test: end-to-end story for both venues; docs for accounts, bills and tax`

---

## Self-review notes

- Spec coverage: isolation (T2–T5), admin onboarding (T8), venues/options (T6, T9–T11), tax (T7), bills and sample bill (T12–T14), simulator (T16), analytics rename and payment mix (T15, T17), scripts/e2e/docs (T18). Non-goals untouched.
- Spec adjustments made while planning (already written into the spec): advisory lock for bill numbers; simulated bills have no number; `GET /api/guest/bill`; bill events on the kitchen channel; bank transfer at the standard rate.
- Known follow-ups (not in this plan): Floor view (priority 2), kitchen stations, café counter flow, Urdu (priority 3), split payments, service charge.
