# Dish Page and Choices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guests tap a dish, make it theirs (spice, sugar, extras, leave-outs), and every price, allergen, kitchen ticket and bill stays correct.

**Architecture:** Two new tables hold what can be chosen. The order line stores a JSONB snapshot of what was chosen and folds prices into `unit_price`, so tax, bills and settle need no new maths. All rules live in one service, `services/choices.py`.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, Postgres 16, Next.js 15, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-05-dish-choices-design.md`. Read section 3 (allergen rules) before Task 3.

**Branch:** `feat/dish-choices`. Never commit `.gitignore`, `.claude/` or `.impeccable/`.

**Running things:**
- One Python test file: `docker compose build api-test && docker compose run --rm api-test pytest -q tests/test_x.py`. The image bakes the source, so always rebuild. Never run two pytest at once: they share a test database.
- After editing migration 0021 once it has run, drop the persisted test database before the next run.
- Front end: `pnpm --filter guest-web test`, `pnpm --filter owner-web test`.
- Use `LLM_PROVIDER=mock` for anything that starts the stack. Never read `.env`.

---

## File map

| File | Job |
|---|---|
| `services/api/alembic/versions/0021_dish_choices.py` | New tables, `order_item.choices` |
| `services/api/src/models/menu.py` | `MenuChoiceGroup`, `MenuChoice` |
| `services/api/src/services/choices.py` | Every choice rule: resolve, availability, allergens, snapshot, save checks |
| `services/api/src/services/order_snapshot.py` | Folds choices into the line |
| `services/api/src/routers/orders.py` | Resolve, acknowledgement on the union, hash |
| `services/api/src/routers/guest.py`, `schemas/guest.py` | Menu sends groups |
| `services/api/src/services/bills.py`, `schemas/{orders,bills,payments,kitchen}.py` | Lines carry choices |
| `services/api/src/routers/menu_choices.py` | Owner editing routes |
| `scripts/seed.py`, `data/seed/*.json`, `services/api/src/services/simulator.py` | Demo data |
| `services/api/src/services/analytics.py`, `brief.py`, `schemas/owner.py` | Extras report |
| `apps/guest-web/src/lib/choices.ts` | Pure dish-page rules |
| `apps/guest-web/src/lib/cart.ts`, `lib/ordering.ts` | Cart identity, refusals |
| `apps/guest-web/src/components/DishSheet.tsx` | The dish page |
| `apps/owner-web/src/components/ChoiceEditor.tsx` | Owner editing |

---

### Task 1: Tables and models

**Files:**
- Create: `services/api/alembic/versions/0021_dish_choices.py`
- Modify: `services/api/src/models/menu.py`, `services/api/src/models/order.py`, `services/api/src/models/__init__.py`
- Test: `services/api/tests/test_schema_constraints.py`

- [ ] **Step 1: Write the failing test** (append to `test_schema_constraints.py`, reusing that file's restaurant and item setup)

```python
@pytest.mark.parametrize(
    "group_kwargs",
    [{"min_select": 2, "max_select": 1}, {"min_select": 0, "max_select": 0}, {"kind": "other"}],
)
async def test_choice_group_constraints(db_session, group_kwargs):
    item = await _menu_item(db_session)  # use this file's existing item helper
    base = {"label": "Spice", "kind": "pick", "min_select": 1, "max_select": 1}
    db_session.add(MenuChoiceGroup(menu_item_id=item.id, **{**base, **group_kwargs}))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    "choice_kwargs",
    [
        {"price_delta": Decimal("-1")},
        {"cost_delta": Decimal("-1")},
        {"allergens": ["bananas"]},
        {"is_vegan": True, "is_vegetarian": False},
        {"is_vegan": True, "is_vegetarian": True, "allergens": ["milk"]},
    ],
)
async def test_choice_constraints(db_session, choice_kwargs):
    item = await _menu_item(db_session)
    group = MenuChoiceGroup(
        menu_item_id=item.id, label="Extras", kind="add", min_select=0, max_select=3
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add(MenuChoice(group_id=group.id, label="Milk", **choice_kwargs))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run it.** `docker compose build api-test && docker compose run --rm api-test pytest -q tests/test_schema_constraints.py`. Expected: FAIL, `ImportError: MenuChoiceGroup`.

- [ ] **Step 3: Add the models** to `models/menu.py`, after `MenuItemOption`:

```python
ALLERGEN_CHECK = (
    "ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
    "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]"
)


class MenuChoiceGroup(Base):
    __tablename__ = "menu_choice_group"
    __table_args__ = (
        CheckConstraint("kind IN ('pick', 'add', 'leave_out')", name="chk_choice_group_kind"),
        CheckConstraint(
            "min_select >= 0 AND max_select >= 1 AND min_select <= max_select",
            name="chk_choice_group_select",
        ),
        UniqueConstraint("menu_item_id", "label", name="uq_choice_group_label"),
        Index("idx_choice_group_item", "menu_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_item.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, nullable=False)
    max_select: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    menu_item: Mapped["MenuItem"] = relationship(
        "MenuItem", back_populates="choice_groups", lazy="raise"
    )
    choices: Mapped[list["MenuChoice"]] = relationship(
        "MenuChoice",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="MenuChoice.sort_order",
        lazy="raise",
    )


class MenuChoice(Base):
    __tablename__ = "menu_choice"
    __table_args__ = (
        CheckConstraint("price_delta >= 0 AND cost_delta >= 0", name="chk_choice_money"),
        CheckConstraint(f"allergens <@ {ALLERGEN_CHECK}", name="chk_choice_allergens"),
        CheckConstraint("NOT (is_vegan AND NOT is_vegetarian)", name="chk_choice_vegan_vegetarian"),
        CheckConstraint(
            "NOT is_vegan OR NOT ("
            "allergens && ARRAY['milk','eggs','fish','crustaceans','molluscs']::text[])",
            name="chk_choice_vegan_allergens",
        ),
        UniqueConstraint("group_id", "label", name="uq_choice_label"),
        Index("idx_choice_group", "group_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_choice_group.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    cost_delta: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    allergens: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    # All three default to false: the safe answer for a choice nobody has confirmed.
    allergen_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_vegetarian: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    group: Mapped["MenuChoiceGroup"] = relationship(
        "MenuChoiceGroup", back_populates="choices", lazy="raise"
    )
```

On `MenuItem`, next to `options`:

```python
    choice_groups: Mapped[list["MenuChoiceGroup"]] = relationship(
        "MenuChoiceGroup",
        back_populates="menu_item",
        cascade="all, delete-orphan",
        order_by="MenuChoiceGroup.sort_order",
        lazy="raise",
    )
```

On `OrderItem` in `models/order.py`, after `option_label` (import `JSONB` from `sqlalchemy.dialects.postgresql`):

```python
    # Immutable snapshot of what the guest chose: old bills never change.
    choices: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
```

Export both models from `models/__init__.py`.

- [ ] **Step 4: Write migration `0021_dish_choices.py`** with `down_revision = "0020_money_goes_global"`. `upgrade()` creates both tables with exactly the columns, names and constraints above, and adds `order_item.choices` as `postgresql.JSONB`, `nullable=False`, `server_default=sa.text("'[]'::jsonb")`. `downgrade()` drops the column, then `menu_choice`, then `menu_choice_group`.

- [ ] **Step 5: Run the test and the drift check.** Same command as Step 2, then `pytest -q tests/test_schema_constraints.py tests/test_seed.py`. Expected: PASS. Run whichever test covers migration drift (`grep -rln "compare_metadata\|alembic check" services/api/tests scripts`).

- [ ] **Step 6: Commit**

```bash
git add services/api/alembic/versions/0021_dish_choices.py services/api/src/models services/api/tests/test_schema_constraints.py
git commit -m "feat(api): tables for dish choices"
```

---

### Task 2: The choice rules

**Files:**
- Create: `services/api/src/services/choices.py`
- Test: `services/api/tests/test_choices_rules.py`

These functions take objects with `choice_groups` and `choices` already loaded, so the tests need no database.

- [ ] **Step 1: Write the failing test**

```python
"""Choice rules: resolving picks, availability, allergens, save checks."""

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem
from src.services.choices import (
    can_be_ordered,
    check_choice,
    check_label,
    line_allergens,
    resolve_choices,
    snapshot_choices,
)


def choice(label, price="0", allergens=(), verified=True, available=True, default=False):
    return MenuChoice(
        id=uuid.uuid4(), label=label, price_delta=Decimal(price), cost_delta=Decimal("0"),
        allergens=list(allergens), allergen_verified=verified, available=available,
        is_default=default,
    )


def group(label, kind, lo, hi, *choices):
    return MenuChoiceGroup(
        id=uuid.uuid4(), label=label, kind=kind, min_select=lo, max_select=hi, choices=list(choices)
    )


def dish(*groups, allergens=(), verified=True):
    return MenuItem(
        id=uuid.uuid4(), allergens=list(allergens), allergen_verified=verified,
        choice_groups=list(groups),
    )


def error(exc):
    return exc.value.status_code, exc.value.detail


def test_resolve_keeps_only_this_dishes_choices():
    mild = choice("Mild")
    item = dish(group("Spice", "pick", 1, 1, mild))
    assert resolve_choices(item, [mild.id]) == [mild]
    with pytest.raises(HTTPException) as e:
        resolve_choices(item, [mild.id, uuid.uuid4()])
    assert e.value.status_code == 422


def test_sold_out_choice_is_409_naming_it():
    milk = choice("Extra milk", available=False)
    item = dish(group("Extras", "add", 0, 2, milk))
    with pytest.raises(HTTPException) as e:
        resolve_choices(item, [milk.id])
    code, detail = error(e)
    assert code == 409
    assert detail["error"] == "unavailable_choices"
    assert detail["unavailable_choices"][0]["label"] == "Extra milk"


@pytest.mark.parametrize("picked", [0, 2])
def test_wrong_count_is_choices_changed(picked):
    a, b = choice("Mild"), choice("Hot")
    item = dish(group("Spice", "pick", 1, 1, a, b))
    with pytest.raises(HTTPException) as e:
        resolve_choices(item, [a.id, b.id][:picked])
    code, detail = error(e)
    assert code == 422
    assert detail["error"] == "choices_changed"
    assert detail["menu_item_id"] == str(item.id)


def test_required_group_with_nothing_left_stops_the_dish():
    assert not can_be_ordered(dish(group("Spice", "pick", 1, 1, choice("Mild", available=False))))
    assert can_be_ordered(dish(group("Extras", "add", 0, 1, choice("Milk", available=False))))
    assert can_be_ordered(dish())


def test_a_choice_adds_allergens():
    milk = choice("Extra milk", allergens=["milk"])
    item = dish(group("Extras", "add", 0, 1, milk), allergens=["gluten"])
    allergens, verified = line_allergens(item, [milk])
    assert sorted(allergens) == ["gluten", "milk"]
    assert verified is True


def test_an_unconfirmed_choice_makes_the_line_unverified():
    honey = choice("Honey", verified=False)
    item = dish(group("Extras", "add", 0, 1, honey))
    assert line_allergens(item, [honey])[1] is False


def test_leave_out_never_removes_an_allergen():
    nuts = choice("Nuts")
    item = dish(group("Leave out", "leave_out", 0, 1, nuts), allergens=["tree_nuts"])
    assert line_allergens(item, [nuts]) == (["tree_nuts"], True)


def test_snapshot_keeps_group_kind_and_money_as_strings():
    milk = choice("Extra milk", "0.50", ["milk"])
    item = dish(group("Extras", "add", 0, 1, milk))
    assert snapshot_choices(item, [milk]) == [
        {
            "choice_id": str(milk.id), "group": "Extras", "kind": "add", "label": "Extra milk",
            "price_delta": "0.50", "cost_delta": "0", "allergens": ["milk"],
        }
    ]


@pytest.mark.parametrize(
    "label", ["Nut free", "Sugar-free", "ALLERGY safe", "allergen check", "Safe for kids"]
)
def test_labels_cannot_promise_safety(label):
    with pytest.raises(HTTPException) as e:
        check_label(label)
    assert e.value.status_code == 422


@pytest.mark.parametrize("label", ["No sugar", "Saffron", "Freekeh", "Extra milk"])
def test_ordinary_labels_pass(label):
    check_label(label)


def test_leave_out_choices_are_free_and_carry_no_allergens():
    for bad in ({"price_delta": Decimal("1")}, {"cost_delta": Decimal("1")}, {"allergens": ["milk"]}):
        fields = {"price_delta": Decimal("0"), "cost_delta": Decimal("0"), "allergens": [], **bad}
        with pytest.raises(HTTPException):
            check_choice("leave_out", **fields)
    check_choice("add", price_delta=Decimal("1"), cost_delta=Decimal("1"), allergens=["milk"])
```

Note the expected `"cost_delta": "0"` follows `str(Decimal("0"))`; live values come from `Numeric(10, 2)` as `"0.00"`.

- [ ] **Step 2: Run it.** `docker compose build api-test && docker compose run --rm api-test pytest -q tests/test_choices_rules.py`. Expected: FAIL, module not found.

- [ ] **Step 3: Write `services/choices.py`**

```python
"""Dish choices: every rule in one place. `item.choice_groups` and their `choices` must be loaded.

A choice can add an allergen and can never remove one.
"""

import re
import uuid
from decimal import Decimal

from fastapi import HTTPException, status

from src.models.menu import MenuChoice, MenuItem

# Whole words: "Freekeh" and "Saffron" are fine, "Nut free" and "Sugar-free" are not.
PROMISES_SAFETY = re.compile(r"\b(free|allergy|allergen|safe)\b", re.IGNORECASE)


def resolve_choices(item: MenuItem, choice_ids: list[uuid.UUID]) -> list[MenuChoice]:
    """The guest's picks for one line, or the refusal the guest must see."""
    if not choice_ids and not item.choice_groups:
        return []
    known = {c.id: c for g in item.choice_groups for c in g.choices}
    if any(i not in known for i in choice_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown choice for {item.id}",
        )
    chosen = [known[i] for i in choice_ids]
    sold_out = [c for c in chosen if not c.available]
    if sold_out:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "unavailable_choices",
                "unavailable_choices": [
                    {"menu_item_id": str(item.id), "choice_id": str(c.id), "label": c.label}
                    for c in sold_out
                ],
            },
        )
    picked = set(choice_ids)
    for g in item.choice_groups:
        count = sum(c.id in picked for c in g.choices)
        if not g.min_select <= count <= g.max_select:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"error": "choices_changed", "menu_item_id": str(item.id)},
            )
    return chosen


def can_be_ordered(item: MenuItem) -> bool:
    """False when a required group no longer has enough available choices."""
    return all(sum(c.available for c in g.choices) >= g.min_select for g in item.choice_groups)


def line_allergens(item: MenuItem, choices: list[MenuChoice]) -> tuple[list[str], bool]:
    """The union of dish and choice allergens, and whether all of it is confirmed."""
    allergens = list(item.allergens)
    for c in choices:
        allergens += [a for a in c.allergens if a not in allergens]
    return allergens, item.allergen_verified and all(c.allergen_verified for c in choices)


def snapshot_choices(item: MenuItem, choices: list[MenuChoice]) -> list[dict]:
    """JSON for `order_item.choices`, in menu order."""
    picked = {c.id for c in choices}
    return [
        {
            "choice_id": str(c.id),
            "group": g.label,
            "kind": g.kind,
            "label": c.label,
            "price_delta": str(c.price_delta),
            "cost_delta": str(c.cost_delta),
            "allergens": list(c.allergens),
        }
        for g in item.choice_groups
        for c in g.choices
        if c.id in picked
    ]


def check_label(label: str) -> None:
    if PROMISES_SAFETY.search(label):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='A choice can\'t promise safety. Write "No sugar", not "Sugar free".',
        )


def check_choice(
    kind: str, *, price_delta: Decimal, cost_delta: Decimal, allergens: list[str]
) -> None:
    if kind == "leave_out" and (price_delta or cost_delta or allergens):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Leaving something out is free and carries no allergens",
        )
```

`\bfree\b` matches inside `Sugar-free` because `-` is a word boundary. `HTTP_422_UNPROCESSABLE_CONTENT` is the name `orders.py` uses.

- [ ] **Step 4: Run it.** Same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/src/services/choices.py services/api/tests/test_choices_rules.py
git commit -m "feat(api): rules for dish choices"
```

---

### Task 3: Placing an order

**Files:**
- Modify: `services/api/src/services/order_snapshot.py`, `services/api/src/routers/orders.py`, `services/api/src/schemas/orders.py`
- Test: `services/api/tests/test_choices_order.py`

- [ ] **Step 1: Write the failing test.** Build a fixture the way `tests/test_options.py::karahi_setup` does, including its guest-session cookie and `open_table`. Set the session's `allergens_to_avoid=["milk"]`. Add a `tea` dish (price 300.00, cost 60.00, `allergens=[]`, verified) with groups `Spice` (pick, 1/1: Mild, Hot) and `Extras` (add, 0/2: `Extra milk` +50.00, cost 12.00, allergens milk, verified; `Honey` +30.00, unverified) and `Leave out` (leave_out, 0/1: `Sugar`, exposed as `s.no_sugar`). All choices except Honey are verified. Then:

```python
async def order(client, key, lines, ack=False):
    return await client.post(
        "/api/orders",
        json={"idempotency_key": key, "items": lines, "acknowledge_allergen_risk": ack},
    )


def line(s, *choices, quantity=1):
    return {
        "menu_item_id": str(s.tea.id),
        "quantity": quantity,
        "choice_ids": [str(c.id) for c in choices],
    }


async def test_server_prices_the_line(client, tea_setup):
    s = tea_setup
    resp = await order(client, "k1", [line(s, s.mild, s.extra_milk, quantity=2)], ack=True)
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "700.00"
    item = body["items"][0]
    assert item["unit_price"] == "350.00"
    assert [c["label"] for c in item["choices"]] == ["Mild", "Extra milk"]
    assert "cost_delta" not in item["choices"][0]


async def test_cost_is_snapshotted(client, tea_setup, db_session):
    s = tea_setup
    resp = await order(client, "k2", [line(s, s.mild, s.extra_milk)], ack=True)
    row = await db_session.get(OrderItem, uuid.UUID(resp.json()["items"][0]["id"]))
    assert row.unit_cost == Decimal("72.00")
    assert row.allergens == ["milk"]


async def test_extra_milk_stops_at_the_acknowledgement(client, tea_setup):
    s = tea_setup  # this session avoids milk
    resp = await order(client, "k3", [line(s, s.mild, s.extra_milk)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "allergen_ack_required"
    assert resp.json()["detail"]["items"][0]["matched_allergens"] == ["milk"]
    resp = await order(client, "k3", [line(s, s.mild, s.extra_milk)], ack=True)
    assert resp.status_code == 201
    assert resp.json()["items"][0]["allergen_status"] == "contains"


async def test_unconfirmed_choice_needs_the_acknowledgement(client, tea_setup):
    s = tea_setup
    resp = await order(client, "k4", [line(s, s.mild, s.honey)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["items"][0]["status"] == "unverified"


async def test_leave_out_changes_nothing(client, tea_setup):
    s = tea_setup
    item = (await order(client, "k5", [line(s, s.mild, s.no_sugar)])).json()["items"][0]
    assert item["allergens"] == []
    assert item["allergen_status"] == "no_declared_match"
    assert item["unit_price"] == "300.00"


async def test_repeated_choice_is_refused(client, tea_setup):
    s = tea_setup
    resp = await order(client, "k6", [line(s, s.mild, s.mild)])
    assert resp.status_code == 422


async def test_missing_required_choice_is_choices_changed(client, tea_setup):
    resp = await order(client, "k7", [line(tea_setup)])
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "choices_changed"


async def test_sold_out_choice_is_refused(client, tea_setup, db_session):
    s = tea_setup
    s.mild.available = False
    await db_session.flush()
    resp = await order(client, "k8", [line(s, s.mild)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "unavailable_choices"


async def test_required_group_sold_out_stops_the_dish(client, tea_setup, db_session):
    s = tea_setup
    s.mild.available = False
    s.hot.available = False
    await db_session.flush()
    resp = await order(client, "k9", [line(s)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "unavailable_items"


async def test_retry_with_choices_in_any_order_is_a_retry(client, tea_setup):
    s = tea_setup
    first = await order(client, "k10", [line(s, s.mild, s.no_sugar)])
    again = await order(client, "k10", [line(s, s.no_sugar, s.mild)])
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]


async def test_same_key_with_other_choices_conflicts(client, tea_setup):
    s = tea_setup
    assert (await order(client, "k11", [line(s, s.mild)])).status_code == 201
    assert (await order(client, "k11", [line(s, s.hot)])).status_code == 409


def test_a_line_without_choices_keeps_its_old_hash():
    from src.routers.orders import compute_payload_hash
    from src.schemas.orders import OrderItemRequest

    menu_item_id = uuid.UUID(int=1)
    canonical = [
        {"menu_item_id": str(menu_item_id), "option_id": "", "quantity": 1, "notes": ""}
    ]
    expected = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    assert compute_payload_hash([OrderItemRequest(menu_item_id=menu_item_id, quantity=1)]) == expected


async def test_menu_price_change_leaves_old_lines(client, tea_setup, db_session):
    s = tea_setup
    placed = (await order(client, "k12", [line(s, s.mild, s.no_sugar)])).json()
    s.tea.price = Decimal("999.00")
    await db_session.flush()
    fetched = (await client.get(f"/api/orders/{placed['id']}")).json()
    assert fetched["items"][0]["unit_price"] == "300.00"
```

If the existing same-key conflict in `create_order` returns another status, use that status in `test_same_key_with_other_choices_conflicts`.

- [ ] **Step 2: Run it.** Expected: FAIL (422s and missing `choices`).

- [ ] **Step 3: `schemas/orders.py`.** Add `LineChoice` above `OrderItemRequest`, and the fields:

```python
class LineChoice(BaseModel):
    """One chosen choice as guests and staff see it. Never carries cost."""

    choice_id: uuid.UUID
    group: str
    kind: Literal["pick", "add", "leave_out"]
    label: str
    price_delta: Decimal
```

```python
class OrderItemRequest(BaseModel):
    menu_item_id: uuid.UUID
    option_id: uuid.UUID | None = None
    choice_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    quantity: int = Field(..., ge=1, le=20)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _no_repeats(self) -> "OrderItemRequest":
        if len(set(self.choice_ids)) != len(self.choice_ids):
            raise ValueError("A choice can only be picked once")
        return self
```

`OrderItemResponse` gains `choices: list[LineChoice] = []` after `option_label`. Pydantic ignores the snapshot's extra keys, which keeps `cost_delta` out.

- [ ] **Step 4: `order_snapshot.py`.** New parameter `choices: Sequence[MenuChoice] = ()` (import `Sequence` from `collections.abc`). Replace the money and allergen fields:

```python
    chosen = list(choices)
    base_price = option.price if option else item.price
    base_cost = option.unit_cost if option else item.unit_cost
    allergens, verified = line_allergens(item, chosen)

    return OrderItem(
        menu_item_id=item.id,
        quantity=quantity,
        unit_price=base_price + sum((c.price_delta for c in chosen), Decimal("0")),
        unit_cost=base_cost + sum((c.cost_delta for c in chosen), Decimal("0")),
        option_id=option.id if option else None,
        option_label=option.label if option else None,
        choices=snapshot_choices(item, chosen) if chosen else [],
        item_name=guest_trans.name if guest_trans else "",
        kitchen_name=default_trans.name if default_trans else "",
        allergens=allergens,
        allergen_verified=verified,
        allergen_status=compute_allergen_status(
            item_allergens=allergens,
            allergen_verified=verified,
            guest_allergens_to_avoid=guest_allergens_to_avoid,
        ),
        notes=notes,
        is_pay_forward=item.is_pay_forward,
    )
```

The `if chosen` guard means callers that pass no choices (pay-forward, plain simulator lines) never touch the unloaded `choice_groups` relationship. `line_allergens` reads only `item.allergens` and the passed list, so it is safe too.

- [ ] **Step 5: `routers/orders.py`.**

(a) `compute_payload_hash`: include choices only when present, so hashes of plain lines stay what they were:

```python
    canonical = [
        {
            "menu_item_id": str(i.menu_item_id),
            "option_id": str(i.option_id or ""),
            "quantity": i.quantity,
            "notes": i.notes or "",
            **({"choice_ids": sorted(map(str, i.choice_ids))} if i.choice_ids else {}),
        }
        for i in sorted(
            items,
            key=lambda x: (
                str(x.menu_item_id),
                str(x.option_id or ""),
                x.quantity,
                x.notes or "",
                sorted(map(str, x.choice_ids)),
            ),
        )
    ]
```

(b) Load groups with the items: add `selectinload(MenuItem.choice_groups).selectinload(MenuChoiceGroup.choices)` to the options on `stmt_items`.

(c) Availability: the comprehension becomes `if not item.available or not can_be_ordered(item)`.

(d) After step 4b, add step 4c, then replace step 5's item reads with the union:

```python
    # 4c. Resolve each line's choices (refusals before any allergen check)
    line_choices = [
        resolve_choices(found_items[req.menu_item_id], req.choice_ids) for req in payload.items
    ]

    # 5. Check allergen conflict against session's allergens_to_avoid
    conflict_items: list[dict] = []
    for req, chosen in zip(payload.items, line_choices, strict=True):
        item = found_items[req.menu_item_id]
        allergens, verified = line_allergens(item, chosen)
        s_val = compute_allergen_status(
            item_allergens=allergens,
            allergen_verified=verified,
            guest_allergens_to_avoid=session.allergens_to_avoid,
        )
        matched = (
            [a for a in allergens if a in session.allergens_to_avoid]
            if s_val == "contains"
            else []
        )
```

(e) Step 6 zips three lists and passes `choices=chosen`:

```python
        for req, opt, chosen in zip(payload.items, line_options, line_choices, strict=True)
```

Add the 409 description `unavailable choices` and imports `MenuChoiceGroup`, and `can_be_ordered, line_allergens, resolve_choices` from `src.services.choices`.

- [ ] **Step 6: Run** `tests/test_choices_order.py tests/test_options.py tests/test_order_path.py`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/src/services/order_snapshot.py services/api/src/routers/orders.py services/api/src/schemas/orders.py services/api/tests/test_choices_order.py
git commit -m "feat(api): orders carry choices; the server prices them and checks allergens"
```

---

### Task 4: Guest menu sends the groups

**Files:**
- Modify: `services/api/src/routers/guest.py`, `services/api/src/schemas/guest.py`
- Test: `services/api/tests/test_choices_order.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_menu_sends_choices_with_status_and_no_cost(client, tea_setup):
    menu = (await client.get("/api/guest/menu")).json()
    tea = next(i for i in menu["items"] if i["name"] == "Tea")
    spice, extras, leave_out = tea["choice_groups"]
    assert (spice["label"], spice["kind"], spice["min_select"], spice["max_select"]) == (
        "Spice", "pick", 1, 1,
    )
    milk = next(c for c in extras["choices"] if c["label"] == "Extra milk")
    assert milk["price_delta"] == "50.00"
    assert milk["allergen_status"] == "contains"
    assert milk["matched_allergens"] == ["milk"]
    assert "cost_delta" not in milk
    honey = next(c for c in extras["choices"] if c["label"] == "Honey")
    assert honey["allergen_status"] == "unverified"


async def test_menu_marks_a_dish_sold_out_when_a_required_group_is(client, tea_setup, db_session):
    s = tea_setup
    s.mild.available = False
    s.hot.available = False
    await db_session.flush()
    menu = (await client.get("/api/guest/menu")).json()
    assert next(i for i in menu["items"] if i["name"] == "Tea")["available"] is False
```

- [ ] **Step 2: Run it.** Expected: FAIL, `KeyError: 'choice_groups'`.

- [ ] **Step 3: `schemas/guest.py`**, above `GuestMenuItemResponse`:

```python
class GuestMenuChoice(BaseModel):
    id: uuid.UUID
    label: str
    price_delta: Decimal
    allergens: list[str]
    is_vegetarian: bool
    is_vegan: bool
    available: bool
    is_default: bool
    allergen_status: str
    matched_allergens: list[str]

    model_config = ConfigDict(extra="forbid")


class GuestMenuChoiceGroup(BaseModel):
    id: uuid.UUID
    label: str
    kind: str
    min_select: int
    max_select: int
    choices: list[GuestMenuChoice]

    model_config = ConfigDict(extra="forbid")
```

`GuestMenuItemResponse` gains `choice_groups: list[GuestMenuChoiceGroup] = []`.

- [ ] **Step 4: `routers/guest.py`.** Add the nested `selectinload` to `stmt_items`. Add a helper above the route and use it:

```python
def _guest_choice(c: MenuChoice, avoid: list[str]) -> GuestMenuChoice:
    status_val = compute_allergen_status(
        item_allergens=c.allergens,
        allergen_verified=c.allergen_verified,
        guest_allergens_to_avoid=avoid,
    )
    return GuestMenuChoice(
        id=c.id,
        label=c.label,
        price_delta=c.price_delta,
        allergens=c.allergens,
        is_vegetarian=c.is_vegetarian,
        is_vegan=c.is_vegan,
        available=c.available,
        is_default=c.is_default,
        allergen_status=status_val,
        matched_allergens=[a for a in c.allergens if a in avoid] if status_val == "contains" else [],
    )
```

In the response: `available=item.available and can_be_ordered(item)`, and

```python
                choice_groups=[
                    GuestMenuChoiceGroup(
                        id=g.id,
                        label=g.label,
                        kind=g.kind,
                        min_select=g.min_select,
                        max_select=g.max_select,
                        choices=[_guest_choice(c, session.allergens_to_avoid) for c in g.choices],
                    )
                    for g in item.choice_groups
                ],
```

- [ ] **Step 5: Run** `tests/test_choices_order.py tests/test_options.py`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/src/routers/guest.py services/api/src/schemas/guest.py services/api/tests/test_choices_order.py
git commit -m "feat(api): guest menu lists each dish's choices"
```

---

### Task 5: Bills and kitchen show choices

**Files:**
- Modify: `services/api/src/services/bills.py`, `services/api/src/schemas/bills.py`, `services/api/src/schemas/payments.py`, `services/api/src/schemas/kitchen.py`, `services/api/src/routers/kitchen.py`, `services/api/src/routers/guest.py`
- Test: `services/api/tests/test_choices_bills.py`

- [ ] **Step 1: Write the failing test.** Reuse the `tea_setup` fixture by moving it and the `order`/`line` helpers from `test_choices_order.py` into a shared `tests/choices_setup.py`. Add a GB fixture (`currency="GBP"`, `tax_jurisdiction="GB"`, `service_charge_rate=Decimal("0.125")`, tea at 3.00, milk at 0.50, session avoiding nothing) and an AE-DU one (`currency="AED"`, same prices). Use `approve_order`, `as_member` and `settle` from `tests/helpers.py`, as `tests/test_global_bills.py` does.

```python
async def test_same_price_different_choices_stay_separate_lines():
    from src.models.order import Order, OrderItem
    from src.services.bills import bill_lines

    def oi(label):
        return OrderItem(
            item_name="Tea", option_label=None, unit_price=Decimal("300.00"), quantity=1,
            choices=[{"choice_id": str(uuid.uuid4()), "group": "Sugar", "kind": "pick",
                      "label": label, "price_delta": "0.00"}],
        )

    lines, subtotal = bill_lines([Order(items=[oi("No sugar"), oi("Less sugar"), oi("No sugar")])])
    assert sorted((l.choices[0].label, l.quantity) for l in lines) == [
        ("Less sugar", 1), ("No sugar", 2),
    ]
    assert subtotal == Decimal("900.00")


async def test_kitchen_ticket_shows_choices_and_the_union(client, tea_setup, db_session):
    s = tea_setup
    placed = await order(client, "kk", [line(s, s.mild, s.extra_milk, s.no_sugar)], ack=True)
    await approve_order(placed.json()["id"])
    await as_member(client, db_session, s.restaurant.id, "staff")
    orders = (await client.get(f"/api/restaurants/{s.restaurant.slug}/kitchen/orders")).json()
    item = orders[0]["items"][0]
    assert [(c["kind"], c["label"]) for c in item["choices"]] == [
        ("pick", "Mild"), ("add", "Extra milk"), ("leave_out", "Sugar"),
    ]
    assert "milk" in item["allergens"]
    assert "cost_delta" not in item["choices"][0]


async def test_gb_vat_is_inside_the_price_with_extras(client, gb_tea, db_session):
    """£3.00 tea + £0.50 milk: the guest pays the menu price, VAT worked out on the total."""
    bill = await settled_bill(client, db_session, gb_tea, [gb_tea.mild, gb_tea.extra_milk])
    assert (str(bill.total), str(bill.tax_amount)) == ("3.50", "0.58")


async def test_dubai_vat_is_inside_the_price_with_extras(client, dubai_tea, db_session):
    bill = await settled_bill(client, db_session, dubai_tea, [dubai_tea.mild, dubai_tea.extra_milk])
    assert (str(bill.total), str(bill.tax_amount)) == ("3.50", "0.17")


async def test_pakistan_bill_with_extras_adds_tax_on_top(client, tea_setup, db_session):
    """Rs 350 at the 16% cash rate: tax 56, total 406."""
    s = tea_setup
    bill = await settled_bill(client, db_session, s, [s.mild, s.extra_milk])
    assert (bill.subtotal, bill.tax_amount, bill.total) == (
        Decimal("350.00"), Decimal("56.00"), Decimal("406.00"),
    )


async def test_gb_service_charge_includes_extras(client, gb_tea, db_session):
    """Optional 12.5% of £3.50 = £0.44, on top of the menu price."""
    s = gb_tea
    bill = await settled_bill(client, db_session, s, [s.mild, s.extra_milk], service_included=True)
    assert (str(bill.service_charge_amount), str(bill.total)) == ("0.44", "3.94")
```

`settled_bill(client, db, s, choices, **settle_kwargs)` is a helper you write in this file: place the order with `ack=True`, `approve_order`, sign in as staff with `as_member`, read the bill id from `s`'s table the way `test_global_bills.py` does, call `settle`, then load the `Bill` row. Take the kitchen URL from `routers/kitchen.py`. Check the 16% rate against `data/tax_rates.json` for today's date.

- [ ] **Step 2: Run it.** Expected: FAIL.

- [ ] **Step 3: Schemas.** Import `LineChoice` from `src.schemas.orders` and add `choices: list[LineChoice] = []` to `BillLine`, `VoidedLine` and `KitchenOrderItemResponse`.

- [ ] **Step 4: `bill_lines`.**

```python
def bill_lines(orders: list[Order]) -> tuple[list[BillLine], Decimal]:
    """Lines grouped by (dish, option, unit price, choices), sorted by dish then price; and subtotal."""
    qty: dict[tuple, int] = {}
    chosen: dict[tuple, list[dict]] = {}
    for order in orders:
        for oi in order.items:
            names = tuple(f"{c['group']}: {c['label']}" for c in oi.choices)
            key = (oi.item_name, oi.option_label, oi.unit_price, names)
            qty[key] = qty.get(key, 0) + oi.quantity
            chosen[key] = oi.choices
    # Sorted, not first-seen: orders of one transaction share placed_at, so arrival order
    # is not recoverable from the database.
    lines = [
        BillLine(
            name=key[0],
            option_label=key[1],
            quantity=q,
            unit_price=key[2],
            line_total=key[2] * Decimal(q),
            choices=chosen[key],
        )
        for key, q in sorted(
            qty.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1] or "", kv[0][3])
        )
    ]
    return lines, sum((line.line_total for line in lines), Decimal("0.00"))
```

Pydantic validates `chosen[key]` dicts into `LineChoice`. Rows built with `OrderItem(...)` in a test skip the column default, which is why the test sets `choices` explicitly. Grep tests for `OrderItem(` handed to `bill_lines` without `choices` and use `oi.choices or []` if any exist.

- [ ] **Step 5: `routers/guest.py`** at the `VoidedLine(...)` call: add `choices=v.choices`. **`routers/kitchen.py`**: add `choices=item.choices` to `KitchenOrderItemResponse(...)`.

- [ ] **Step 6: Run** `tests/test_choices_bills.py tests/test_bills.py tests/test_global_bills.py tests/test_money_agreement.py`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/src services/api/tests
git commit -m "feat(api): bills and kitchen tickets list choices; different choices stay separate lines"
```

---

### Task 6: Owner editing routes

**Files:**
- Create: `services/api/src/routers/menu_choices.py`
- Modify: `services/api/src/schemas/owner.py`, `services/api/src/routers/owner.py`, `services/api/src/main.py`
- Test: `services/api/tests/test_choices_owner.py`

- [ ] **Step 1: Write the failing test.** Fixture `owner_setup`: a restaurant with a `dish` and a `pay_forward` dish (`is_pay_forward=True`), signed in as owner with `as_member`.

```python
def groups_url(s, item=None):
    return f"/api/restaurants/{s.restaurant.slug}/menu-items/{(item or s.dish).id}/choice-groups"


SPICE = {"label": "Spice", "kind": "pick", "min_select": 1, "max_select": 1}
MILK = {"label": "Extra milk", "price_delta": "0.50", "cost_delta": "0.12", "allergens": ["milk"]}


async def test_owner_builds_a_group_and_a_choice(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}/choices"
    resp = await client.post(url, json=MILK)
    assert resp.status_code == 201
    assert resp.json()["allergen_verified"] is False
    assert resp.json()["is_vegan"] is False
    listed = (await client.get(f"/api/restaurants/{s.restaurant.slug}/menu-items")).json()
    dish = next(i for i in listed if i["id"] == str(s.dish.id))
    assert dish["choice_groups"][0]["choices"][0]["cost_delta"] == "0.12"


async def test_non_member_gets_404(client, owner_setup, db_session):
    s = owner_setup
    other = Restaurant(name="Other", slug=f"o-{uuid.uuid4().hex[:8]}", currency="PKR",
                       timezone="Asia/Karachi", languages=["en"], default_language="en")
    db_session.add(other)
    await db_session.flush()
    await as_member(client, db_session, other.id, "owner")
    assert (await client.post(groups_url(s), json=SPICE)).status_code == 404


async def test_staff_cannot_edit(client, owner_setup, db_session):
    s = owner_setup
    await as_member(client, db_session, s.restaurant.id, "staff")
    assert (await client.post(groups_url(s), json=SPICE)).status_code == 403


async def test_pay_forward_dish_refuses_groups(client, owner_setup):
    s = owner_setup
    assert (await client.post(groups_url(s, s.pay_forward), json=SPICE)).status_code == 422


async def test_dish_with_groups_cannot_become_pay_forward(client, owner_setup):
    s = owner_setup
    await client.post(groups_url(s), json=SPICE)
    url = f"/api/restaurants/{s.restaurant.slug}/menu-items/{s.dish.id}"
    assert (await client.patch(url, json={"is_pay_forward": True})).status_code == 422


@pytest.mark.parametrize("body", [{"label": "Nut free"}, {"label": "Sugar-free"}])
async def test_labels_cannot_promise_safety(client, owner_setup, body):
    s = owner_setup
    assert (await client.post(groups_url(s), json={**SPICE, **body})).status_code == 422


async def test_leave_out_cannot_cost_or_carry_allergens(client, owner_setup):
    s = owner_setup
    group = (
        await client.post(
            groups_url(s),
            json={"label": "Leave out", "kind": "leave_out", "min_select": 0, "max_select": 3},
        )
    ).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}/choices"
    assert (await client.post(url, json=MILK)).status_code == 422
    assert (await client.post(url, json={"label": "Onions"})).status_code == 201


async def test_defaults_cannot_exceed_the_maximum(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}/choices"
    assert (await client.post(url, json={"label": "Mild", "is_default": True})).status_code == 201
    assert (await client.post(url, json={"label": "Hot", "is_default": True})).status_code == 422


async def test_vegan_milk_is_refused_not_a_server_error(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}/choices"
    body = {**MILK, "is_vegan": True, "is_vegetarian": True}
    assert (await client.post(url, json=body)).status_code == 422


async def test_limits(client, owner_setup):
    s = owner_setup
    for n in range(8):
        body = {**SPICE, "label": f"G{n}"}
        assert (await client.post(groups_url(s), json=body)).status_code == 201
    assert (await client.post(groups_url(s), json={**SPICE, "label": "G9"})).status_code == 422


async def test_changing_allergens_clears_the_confirmation(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    base = f"/api/restaurants/{s.restaurant.slug}"
    choice = (
        await client.post(
            f"{base}/choice-groups/{group['id']}/choices",
            json={"label": "Hot", "allergen_verified": True},
        )
    ).json()
    resp = await client.patch(f"{base}/choices/{choice['id']}", json={"allergens": ["mustard"]})
    assert resp.json()["allergen_verified"] is False


async def test_delete_group(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}"
    assert (await client.delete(url)).status_code == 200
```

- [ ] **Step 2: Run it.** Expected: FAIL, 404s.

- [ ] **Step 3: Schemas** in `schemas/owner.py`. Reuse `EU14Allergen` from `src.schemas.guest` for allergens.

```python
class OwnerChoice(BaseModel):
    id: uuid.UUID
    label: str
    price_delta: Decimal
    cost_delta: Decimal
    allergens: list[str]
    allergen_verified: bool
    is_vegetarian: bool
    is_vegan: bool
    available: bool
    is_default: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class OwnerChoiceGroup(BaseModel):
    id: uuid.UUID
    label: str
    kind: Literal["pick", "add", "leave_out"]
    min_select: int
    max_select: int
    sort_order: int
    choices: list[OwnerChoice] = []

    model_config = ConfigDict(from_attributes=True)


class CreateChoiceGroup(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    kind: Literal["pick", "add", "leave_out"]
    min_select: int = Field(0, ge=0, le=20)
    max_select: int = Field(1, ge=1, le=20)
    sort_order: int = 0

    @model_validator(mode="after")
    def _range(self) -> "CreateChoiceGroup":
        if self.min_select > self.max_select:
            raise ValueError("The minimum can't be above the maximum")
        return self


class PatchChoiceGroup(BaseModel):
    """`kind` is fixed once created: it decides which save rules its choices passed."""

    label: str | None = Field(None, min_length=1, max_length=60)
    min_select: int | None = Field(None, ge=0, le=20)
    max_select: int | None = Field(None, ge=1, le=20)
    sort_order: int | None = None


class CreateChoice(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    price_delta: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    cost_delta: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    allergens: list[EU14Allergen] = []
    allergen_verified: bool = False
    is_vegetarian: bool = False
    is_vegan: bool = False
    available: bool = True
    is_default: bool = False
    sort_order: int = 0


class PatchChoice(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=60)
    price_delta: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    cost_delta: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    allergens: list[EU14Allergen] | None = None
    allergen_verified: bool | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    available: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = None
```

`OwnerMenuItemResponse` gains `choice_groups: list[OwnerChoiceGroup] = []`. In `routers/owner.py`, `_build_owner_item_response` passes `choice_groups=item.choice_groups`, and every query that feeds it (the list, the patch load, the patch reload and both loads in `verify_menu_item`) adds the nested `selectinload`. In `patch_menu_item`, before `ensure_can_flag`:

```python
        if payload.is_pay_forward and item.choice_groups:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A dish with choices can't be pay-it-forward",
            )
```

- [ ] **Step 4: Router `menu_choices.py`**

```python
"""Owner editing of dish choices. Past orders hold their own snapshot, so edits never reach them."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.access import RestaurantAccess, owner_access
from src.database import get_db
from src.models.audit import AuditLog
from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem
from src.schemas.owner import (
    CreateChoice,
    CreateChoiceGroup,
    OwnerChoice,
    OwnerChoiceGroup,
    PatchChoice,
    PatchChoiceGroup,
    StatusOkResponse,
)
from src.services.choices import check_choice, check_label

router = APIRouter(prefix="/api/restaurants/{slug}", tags=["owner"])

MAX_GROUPS = 8
MAX_CHOICES = 20
ANIMAL = {"milk", "eggs", "fish", "crustaceans", "molluscs"}


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _audit(db: AsyncSession, access: RestaurantAccess, action: str, target: uuid.UUID) -> None:
    db.add(
        AuditLog(
            restaurant_id=access.restaurant.id,
            event_type="owner_choice_edit",
            actor=f"user:{access.user.id}",
            payload={"action": action, "id": str(target)},
        )
    )


async def _item(db: AsyncSession, access: RestaurantAccess, item_id: uuid.UUID) -> MenuItem:
    item = await db.scalar(
        select(MenuItem)
        .options(selectinload(MenuItem.choice_groups))
        .where(
            MenuItem.id == item_id,
            MenuItem.restaurant_id == access.restaurant.id,
            MenuItem.deleted_at.is_(None),
        )
    )
    if item is None:
        raise _not_found()
    return item


async def _group(db: AsyncSession, access: RestaurantAccess, group_id: uuid.UUID) -> MenuChoiceGroup:
    group = await db.scalar(
        select(MenuChoiceGroup)
        .join(MenuItem)
        .options(selectinload(MenuChoiceGroup.choices))
        .where(MenuChoiceGroup.id == group_id, MenuItem.restaurant_id == access.restaurant.id)
    )
    if group is None:
        raise _not_found()
    return group


async def _choice(
    db: AsyncSession, access: RestaurantAccess, choice_id: uuid.UUID
) -> tuple[MenuChoice, MenuChoiceGroup]:
    group_id = await db.scalar(select(MenuChoice.group_id).where(MenuChoice.id == choice_id))
    if group_id is None:
        raise _not_found()
    group = await _group(db, access, group_id)
    return next(c for c in group.choices if c.id == choice_id), group


def _check_defaults(group: MenuChoiceGroup) -> None:
    if sum(c.is_default for c in group.choices) > group.max_select:
        raise _refuse("Too many choices start selected for this group")


def _check_flags(is_vegetarian: bool, is_vegan: bool, allergens: list[str]) -> None:
    if is_vegan and (not is_vegetarian or ANIMAL & set(allergens)):
        raise _refuse("A vegan choice must be vegetarian and carry no animal allergen")


def _check_unique(labels: list[str], label: str) -> None:
    if label in labels:
        raise _refuse("That name is already used here")


@router.post(
    "/menu-items/{item_id}/choice-groups",
    response_model=OwnerChoiceGroup,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    item_id: uuid.UUID,
    payload: CreateChoiceGroup,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoiceGroup:
    item = await _item(db, access, item_id)
    if item.is_pay_forward:
        raise _refuse("A pay-it-forward dish can't have choices")
    if len(item.choice_groups) >= MAX_GROUPS:
        raise _refuse(f"A dish can have up to {MAX_GROUPS} groups")
    check_label(payload.label)
    _check_unique([g.label for g in item.choice_groups], payload.label)
    group = MenuChoiceGroup(menu_item_id=item.id, **payload.model_dump())
    db.add(group)
    await db.flush()
    _audit(db, access, "create_group", group.id)
    response = OwnerChoiceGroup(id=group.id, choices=[], **payload.model_dump())
    await db.commit()
    return response


@router.patch("/choice-groups/{group_id}", response_model=OwnerChoiceGroup)
async def patch_group(
    group_id: uuid.UUID,
    payload: PatchChoiceGroup,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoiceGroup:
    group = await _group(db, access, group_id)
    changes = payload.model_dump(exclude_unset=True)
    if "label" in changes:
        check_label(changes["label"])
    for field, value in changes.items():
        setattr(group, field, value)
    if group.min_select > group.max_select:
        raise _refuse("The minimum can't be above the maximum")
    _check_defaults(group)
    _audit(db, access, "patch_group", group.id)
    response = OwnerChoiceGroup.model_validate(group)
    await db.commit()
    return response


@router.delete("/choice-groups/{group_id}", response_model=StatusOkResponse)
async def delete_group(
    group_id: uuid.UUID,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    group = await _group(db, access, group_id)
    await db.delete(group)
    _audit(db, access, "delete_group", group_id)
    await db.commit()
    return StatusOkResponse(status="ok")


@router.post(
    "/choice-groups/{group_id}/choices",
    response_model=OwnerChoice,
    status_code=status.HTTP_201_CREATED,
)
async def create_choice(
    group_id: uuid.UUID,
    payload: CreateChoice,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoice:
    group = await _group(db, access, group_id)
    if len(group.choices) >= MAX_CHOICES:
        raise _refuse(f"A group can have up to {MAX_CHOICES} choices")
    check_label(payload.label)
    _check_unique([c.label for c in group.choices], payload.label)
    check_choice(
        group.kind,
        price_delta=payload.price_delta,
        cost_delta=payload.cost_delta,
        allergens=payload.allergens,
    )
    _check_flags(payload.is_vegetarian, payload.is_vegan, payload.allergens)
    choice = MenuChoice(**payload.model_dump())
    group.choices.append(choice)
    _check_defaults(group)
    await db.flush()
    _audit(db, access, "create_choice", choice.id)
    response = OwnerChoice.model_validate(choice)
    await db.commit()
    return response


@router.patch("/choices/{choice_id}", response_model=OwnerChoice)
async def patch_choice(
    choice_id: uuid.UUID,
    payload: PatchChoice,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoice:
    choice, group = await _choice(db, access, choice_id)
    changes = payload.model_dump(exclude_unset=True)
    if "label" in changes:
        check_label(changes["label"])
    # Same rule as dishes: changed allergens are unconfirmed until someone says otherwise.
    if "allergens" in changes and changes["allergens"] != choice.allergens:
        changes.setdefault("allergen_verified", False)
    for field, value in changes.items():
        setattr(choice, field, value)
    check_choice(
        group.kind,
        price_delta=choice.price_delta,
        cost_delta=choice.cost_delta,
        allergens=choice.allergens,
    )
    _check_flags(choice.is_vegetarian, choice.is_vegan, choice.allergens)
    _check_defaults(group)
    _audit(db, access, "patch_choice", choice.id)
    response = OwnerChoice.model_validate(choice)
    await db.commit()
    return response


@router.delete("/choices/{choice_id}", response_model=StatusOkResponse)
async def delete_choice(
    choice_id: uuid.UUID,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    choice, group = await _choice(db, access, choice_id)
    group.choices.remove(choice)
    _audit(db, access, "delete_choice", choice_id)
    await db.commit()
    return StatusOkResponse(status="ok")
```

Column defaults are server-side, so `OwnerChoice.model_validate(choice)` works because `payload.model_dump()` sets every column except `id` (filled by the flush) and `group_id`. A refused request raises before commit, and `get_db` rolls back, so a half-applied `setattr` never persists. A concurrent duplicate label reaches the unique constraint as a 500: two owners editing one group at the same second is accepted here.

Register it in `main.py`: `app.include_router(menu_choices_router)`, beside `owner_router`.

- [ ] **Step 5: Run** `tests/test_choices_owner.py tests/test_restaurant_isolation.py`. Expected: PASS. If `test_restaurant_isolation.py` lists routes explicitly, add these.

- [ ] **Step 6: Commit**

```bash
git add services/api/src services/api/tests/test_choices_owner.py
git commit -m "feat(api): owners edit dish choices"
```

---

### Task 7: Seed data and simulator

**Files:**
- Modify: `scripts/seed.py`, `data/seed/angeethi_house.json`, `data/seed/kehwa_and_crumb.json`, `services/api/src/services/simulator.py`, `scripts/verify_phase1.sh`
- Test: `services/api/tests/test_seed.py`, `services/api/tests/test_simulator_bills.py`

- [ ] **Step 1: Write the failing tests**

In `test_seed.py`:

```python
async def test_seed_creates_choices_with_stable_ids_and_reseeds_cleanly(db_session):
    data = load_seed_data(ANGEETHI_SEED)  # use this file's existing path constant
    await seed_data(data, db_session)
    first = {c.id for c in (await db_session.scalars(select(MenuChoice))).all()}
    await seed_data(data, db_session)
    second = {c.id for c in (await db_session.scalars(select(MenuChoice))).all()}
    assert first and first == second


async def test_seed_never_puts_choices_on_pay_it_forward(db_session):
    for path in (ANGEETHI_SEED, KEHWA_SEED):
        data = load_seed_data(path)
        chai = next(i for i in data["items"] if i["key"] == "pay_forward_chai")
        assert "choice_groups" not in chai
```

In `test_simulator_bills.py`:

```python
SPICE = (uuid.UUID(int=101), uuid.UUID(int=102))
EXTRA = uuid.UUID(int=103)


def test_choices_never_shift_the_order_stream():
    plain = generate_orders(assumptions(), ITEMS, start=START, tz=TZ)  # match this file's call
    with_choices = [
        replace(i, required=(SPICE,), extras=(EXTRA,)) if i.id == ITEMS[0].id else i for i in ITEMS
    ]
    drawn = generate_orders(assumptions(), with_choices, start=START, tz=TZ)
    assert [(o.placed_at, o.lines, o.payment_method) for o in plain] == [
        (o.placed_at, o.lines, o.payment_method) for o in drawn
    ]
    picks = [ids for o in drawn for ids in o.choices.values()]
    assert picks and all(any(s in ids for s in SPICE) for ids in picks)
    assert any(EXTRA in ids for ids in picks)
```

Use the file's real generator name and arguments; `dataclasses.replace` needs importing.

- [ ] **Step 2: Run them.** Expected: FAIL.

- [ ] **Step 3: Seed data.** Add `choice_groups` to these items. Shared shape:

```json
"choice_groups": [
  {"label": "Spice", "kind": "pick", "min_select": 1, "max_select": 1, "choices": [
    {"label": "Mild", "allergen_verified": true, "is_vegetarian": true, "is_vegan": true},
    {"label": "Medium", "allergen_verified": true, "is_vegetarian": true, "is_vegan": true},
    {"label": "Hot", "allergen_verified": true, "is_vegetarian": true, "is_vegan": true}
  ]},
  {"label": "Leave out", "kind": "leave_out", "min_select": 0, "max_select": 3, "choices": [
    {"label": "Onions", "allergen_verified": true, "is_vegetarian": true, "is_vegan": true},
    {"label": "Green chilli", "allergen_verified": true, "is_vegetarian": true, "is_vegan": true},
    {"label": "Ginger", "allergen_verified": true, "is_vegetarian": true, "is_vegan": true}
  ]}
]
```

- `angeethi_house.json`: that block on `chicken_karahi`, `mutton_karahi`. On `doodh_patti_chai`: Sugar (pick, 1/1: Normal `is_default`, Less, No sugar; all verified, vegetarian, vegan) and Extras (add, 0/1: `Extra milk`, `price_delta` 50, `cost_delta` 15, allergens `["milk"]`, verified, vegetarian).
- `kehwa_and_crumb.json`: on `cappuccino`, `cafe_latte`: Extras (add, 0/2: `Extra shot` 150/40, verified, vegetarian, vegan; `Almond milk` 120/50, allergens `["tree_nuts"]`, verified, vegetarian, vegan). On `karak_chai`, `green_kehwa`: the Sugar group. On `fudge_brownie`: Extras (add, 0/1: `Vanilla ice cream` 250/80, allergens `["milk", "eggs"]`, verified, vegetarian).

Leave `butter_croissant`, `naan` and `chicken_tikka` plain: browser stories rely on their one-tap add.

- [ ] **Step 4: `scripts/seed.py`.** Add this function, and call it inside the item loop right after the options block (import `delete` from sqlalchemy; import `MenuChoice`, `MenuChoiceGroup`). If `target_item` was just created, flush first so the row exists.

```python
async def seed_choices(
    session: AsyncSession, slug: str, item_data: dict[str, Any], item_id: uuid.UUID
) -> None:
    """Replace a dish's choices with the file's; ids are stable, and past orders keep snapshots."""
    await session.execute(delete(MenuChoiceGroup).where(MenuChoiceGroup.menu_item_id == item_id))
    for g_pos, g in enumerate(item_data.get("choice_groups", [])):
        group_id = uuid.uuid5(SEED_ITEM_NAMESPACE, f"{slug}:{item_data['key']}:group:{g['label']}")
        session.add(
            MenuChoiceGroup(
                id=group_id,
                menu_item_id=item_id,
                label=g["label"],
                kind=g["kind"],
                min_select=g["min_select"],
                max_select=g["max_select"],
                sort_order=g_pos,
            )
        )
        for c_pos, c in enumerate(g["choices"]):
            session.add(
                MenuChoice(
                    id=uuid.uuid5(SEED_ITEM_NAMESPACE, f"{group_id}:{c['label']}"),
                    group_id=group_id,
                    label=c["label"],
                    price_delta=c.get("price_delta", 0),
                    cost_delta=c.get("cost_delta", 0),
                    allergens=c.get("allergens", []),
                    allergen_verified=c.get("allergen_verified", False),
                    is_vegetarian=c.get("is_vegetarian", False),
                    is_vegan=c.get("is_vegan", False),
                    is_default=c.get("is_default", False),
                    sort_order=c_pos,
                )
            )
```

SQLAlchemy orders inserts by dependency, so groups land before choices in one flush.

- [ ] **Step 5: `simulator.py`.** `LineKey` stays a pair, so existing tests hold.

`SimItem` gains:

```python
    # Each required group's choice ids (one is always drawn), then optional extras.
    required: tuple[tuple[uuid.UUID, ...], ...] = ()
    extras: tuple[uuid.UUID, ...] = ()
```

`SimOrder` gains `choices: dict[LineKey, tuple[uuid.UUID, ...]] = field(default_factory=dict)`.

Module constant `EXTRA_RATE = 0.2`, comment `# Share of lines with an optional extra, so demos show the report.`

In the generator docstring, add that choices come from a third generator seeded `[seed, 2]`. Create `picks = np.random.default_rng([a.seed, 2])` beside `extra`. After `key = (item.id, option_id)`:

```python
                    if key not in order.choices and (item.required or item.extras):
                        drawn = [ids[int(picks.integers(len(ids)))] for ids in item.required]
                        drawn += [e for e in item.extras if picks.random() < EXTRA_RATE]
                        order.choices[key] = tuple(drawn)
```

`sim_items` fills them, using available choices only:

```python
                required=tuple(
                    ids
                    for g in item.choice_groups
                    if g.min_select > 0
                    and (ids := tuple(c.id for c in g.choices if c.available))
                ),
                extras=tuple(
                    c.id
                    for g in item.choice_groups
                    if g.kind == "add" and g.min_select == 0
                    for c in g.choices
                    if c.available
                ),
```

Seeded `add` groups have a maximum at or above their number of extras, except `doodh_patti_chai` and `fudge_brownie`, which hold one extra in a 0/1 group. So a draw never exceeds a maximum. Add a `# shortcut: extras ignore max_select, fine while seeds stay within it; cap per group if seeds grow` comment on the `drawn +=` line.

Every caller that loads items for `sim_items` and `persist_simulation` adds the nested `selectinload` (grep `selectinload(MenuItem.options)` in `simulator.py` and `routers/`).

In `persist_simulation`, resolve and pass choices, and keep the old `canonical` shape for plain lines:

```python
        def chosen(key: LineKey) -> list[MenuChoice]:
            ids = set(so.choices.get(key, ()))
            item = by_id[key[0]]
            return [c for g in item.choice_groups for c in g.choices if c.id in ids] if ids else []
```

Pass `choices=chosen((item_id, option_id))` to `snapshot_order_item`. Canonical entries become `[str(i), str(o) if o else None, q, *map(str, so.choices.get((i, o), ()))]`.

- [ ] **Step 6: `scripts/verify_phase1.sh`.** At line ~261 a dish is picked by `not i['options']`. Add the required-group filter so the script sends a valid order:

```python
dish = next(i for i in items if not i['options'] and i['id'] != chai['id'] and not any(g['min_select'] for g in i['choice_groups']))
```

Line ~190 uses `items[0]`, and `scripts/e2e_smoke.sh` too. Those are `chicken_tikka` and `americano` (no required group), so they stay.

- [ ] **Step 7: Run** `tests/test_seed.py tests/test_simulator_bills.py tests/test_analytics_pure.py tests/test_simulator_concurrency.py tests/test_demo.py`. Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scripts data/seed services/api/src/services/simulator.py services/api/src/routers services/api/tests
git commit -m "feat(api): seed and simulate dish choices"
```

---

### Task 8: Extras report

**Files:**
- Modify: `services/api/src/services/analytics.py`, `services/api/src/services/brief.py`, `services/api/src/schemas/owner.py`
- Test: `services/api/tests/test_analytics_api.py`

- [ ] **Step 1: Write the failing test.** Follow how `test_analytics_api.py` builds settled orders. Fixture `gb_with_extras`: one settled GB bill with VAT included at 20%. Line A has a £0.50 extra named `Extra milk`, quantity 2. Line B is plain. Fixture `plain_venue_window`: a Pakistan venue with one plain settled order.

```python
async def test_extras_summary(db_session, gb_with_extras):
    summary = await analytics.extras_summary(db_session, gb_with_extras.window)
    assert summary["attach_rate_pct"] == 50.0   # 1 of 2 lines
    assert summary["sales"] == pytest.approx(0.83, abs=0.01)  # £1.00 excl. VAT at 20%
    assert summary["top"] == [{"label": "Extra milk", "count": 2}]


async def test_extras_summary_empty(db_session, plain_venue_window):
    assert await analytics.extras_summary(db_session, plain_venue_window) == {
        "attach_rate_pct": 0.0, "sales": 0.0, "top": [],
    }


async def test_brief_carries_extras_but_the_model_never_sees_them(client, gb_with_extras, monkeypatch):
    seen = {}

    async def spy(inference, db, facts, template, task):
        seen.update(facts)
        return template, "template"

    monkeypatch.setattr("src.services.brief.narrate", spy)
    brief = (await client.get(f"/api/restaurants/{gb_with_extras.slug}/ai/brief")).json()
    assert brief["extras"]["attach_rate_pct"] == 50.0
    assert "extras" not in seen
```

- [ ] **Step 2: Run it.** Expected: FAIL.

- [ ] **Step 3: `analytics.py`**, after `service_charge_collected`:

```python
_PAID = (
    "CROSS JOIN LATERAL jsonb_array_elements(oi.choices) e "
    "WHERE (e->>'price_delta')::numeric > 0 AND "
)


async def extras_summary(db: AsyncSession, w: Window) -> dict:
    """How often paid extras are added, what they sell (excl. VAT where included), the top five."""
    join = f"FROM orders o JOIN order_item oi ON oi.order_id = o.id {_BILL}"
    lines, with_extra = (
        await db.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE EXISTS ("
                "SELECT 1 FROM jsonb_array_elements(oi.choices) e "
                f"WHERE (e->>'price_delta')::numeric > 0)) {join} WHERE {_SCOPE}"
            ),
            w.params(),
        )
    ).one()
    sales = await db.scalar(
        text(
            "SELECT coalesce(sum(oi.quantity * (e->>'price_delta')::numeric "
            f"/ {_NET}), 0) {join} {_PAID}{_SCOPE}"
        ),
        w.params(),
    )
    top = await db.execute(
        text(
            f"SELECT e->>'label', sum(oi.quantity) {join} {_PAID}{_SCOPE} "
            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5"
        ),
        w.params(),
    )
    return {
        "attach_rate_pct": round(100 * with_extra / lines, 1) if lines else 0.0,
        "sales": round(float(sales), 2),
        "top": [{"label": label, "count": int(n)} for label, n in top.all()],
    }
```

- [ ] **Step 4: `schemas/owner.py`.**

```python
class TopExtra(BaseModel):
    label: str
    count: int


class ExtrasSummary(BaseModel):
    attach_rate_pct: float
    sales: float
    top: list[TopExtra]
```

`DailyBriefResponse` gains `extras: ExtrasSummary`, next to `service_charge_collected`.

- [ ] **Step 5: `brief.py`.** In the returned dict, beside `service_charge_collected`:

```python
        # Not narrated: the model gets no new figures.
        "extras": await analytics.extras_summary(db, w),
```

- [ ] **Step 6: Run** `tests/test_analytics_api.py tests/test_ai_privacy.py`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/src services/api/tests
git commit -m "feat(api): report how often extras are added"
```

---

### Task 9: Regenerate the API client

**Files:** `packages/api-client/openapi.json` and its generated output.

- [ ] **Step 1:**

```bash
LLM_PROVIDER=mock DEMO_MODE=true docker compose up -d --build api
docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json
pnpm --filter api-client generate
docker compose stop api
```

- [ ] **Step 2: Check.** `git diff --stat packages/api-client` shows the new routes. `grep -c cost_delta packages/api-client/openapi.json` finds it only in owner schemas (`OwnerChoice`, `CreateChoice`, `PatchChoice`).

- [ ] **Step 3: Commit**

```bash
git add packages/api-client
git commit -m "chore: regenerate the API client for dish choices"
```

---

### Task 10: Guest rules, cart and refusals

**Files:**
- Create: `apps/guest-web/src/lib/choices.ts`, `apps/guest-web/src/lib/choices.test.ts`
- Modify: `apps/guest-web/src/lib/cart.ts`, `apps/guest-web/src/lib/cart.test.ts`, `apps/guest-web/src/lib/ordering.ts`, `apps/guest-web/src/lib/ordering.test.ts`

- [ ] **Step 1: Write the failing tests**

`choices.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  defaultPicks, firstMissing, needsPage, pickedChoices, requirement, toggle, unitPrice, worstStatus,
  type ChoiceGroup,
} from "./choices";

const c = (id: string, extra = {}) => ({
  id, label: id, price_delta: "0", allergens: [], is_vegetarian: true, is_vegan: true,
  available: true, is_default: false, allergen_status: "no_declared_match" as const,
  matched_allergens: [], ...extra,
});
const spice: ChoiceGroup = {
  id: "s", label: "Spice", kind: "pick", min_select: 1, max_select: 1, choices: [c("mild"), c("hot")],
};
const sugar: ChoiceGroup = {
  id: "u", label: "Sugar", kind: "pick", min_select: 1, max_select: 1,
  choices: [c("normal", { is_default: true }), c("none")],
};
const extras: ChoiceGroup = {
  id: "e", label: "Extras", kind: "add", min_select: 0, max_select: 2,
  choices: [c("milk", { price_delta: "0.50" }), c("shot", { price_delta: "0.80" }), c("oat")],
};

describe("dish page rules", () => {
  it("starts with available defaults only", () => {
    expect(defaultPicks([sugar, spice])).toEqual(["normal"]);
    const gone = { ...sugar, choices: [c("normal", { is_default: true, available: false })] };
    expect(defaultPicks([gone])).toEqual([]);
  });
  it("finds the first empty required group", () => {
    expect(firstMissing([sugar, spice], ["normal"])?.id).toBe("s");
    expect(firstMissing([sugar, spice], ["normal", "hot"])).toBeNull();
  });
  it("a radio group swaps, a checkbox group adds up to its maximum", () => {
    expect(toggle(spice, ["mild", "normal"], "hot")).toEqual(["normal", "hot"]);
    expect(toggle(extras, ["milk"], "shot")).toEqual(["milk", "shot"]);
    expect(toggle(extras, ["milk", "shot"], "oat")).toEqual(["milk", "shot"]);
    expect(toggle(extras, ["milk", "shot"], "milk")).toEqual(["shot"]);
  });
  it("an optional pick of one can be cleared and swapped", () => {
    const one = { ...extras, max_select: 1 };
    expect(toggle(one, ["milk"], "shot")).toEqual(["shot"]);
    expect(toggle(one, ["shot"], "shot")).toEqual([]);
  });
  it("adds prices to the base", () => {
    expect(unitPrice(3, [extras], ["milk", "shot"])).toBeCloseTo(4.3);
  });
  it("takes the worst allergen status of dish and picks", () => {
    const risky = { ...extras, choices: [c("milk", { allergen_status: "contains" })] };
    expect(worstStatus("no_declared_match", [risky], ["milk"])).toBe("contains");
    expect(worstStatus("unverified", [risky], [])).toBe("unverified");
  });
  it("+ adds in one tap only when defaults are enough and there are no sizes", () => {
    expect(needsPage({ options: [], choice_groups: [] })).toBe(false);
    expect(needsPage({ options: [], choice_groups: [sugar, extras] })).toBe(false);
    expect(needsPage({ options: [], choice_groups: [spice] })).toBe(true);
    expect(needsPage({ options: [{ id: "h", label: "Half", price: "1" }], choice_groups: [] })).toBe(true);
  });
  it("says what a group needs in words", () => {
    expect(requirement(spice)).toEqual({ key: "chooseOne", n: 1 });
    expect(requirement(extras)).toEqual({ key: "upTo", n: 2 });
    expect(requirement({ ...extras, max_select: 1 })).toEqual({ key: "optional", n: 1 });
  });
  it("lists picks in menu order for the cart", () => {
    expect(pickedChoices([extras], ["shot", "milk"]).map((p) => p.id)).toEqual(["milk", "shot"]);
  });
});
```

Add to `cart.test.ts`:

```ts
it("two coffees with different choices are two lines; the same choices merge in any order", () => {
  const coffee = { menuItemId: "c", name: "Coffee", price: 3, allergenStatus: "no_declared_match" as const, matchedAllergens: [] };
  const milk = { id: "m", group: "Extras", kind: "add" as const, label: "Milk", priceDelta: 0.5 };
  const shot = { id: "s", group: "Extras", kind: "add" as const, label: "Shot", priceDelta: 0.8 };
  addToCart(coffee, 1, undefined, [milk]);
  addToCart(coffee, 1, undefined, [milk, shot]);
  const cart = addToCart(coffee, 1, undefined, [shot, milk]);
  expect(cart.items.map((i) => i.quantity)).toEqual([1, 2]);
  expect(cart.items[1].price).toBeCloseTo(4.3);
  expect(toOrderPayload(cart).items[1].choice_ids).toEqual(["m", "s"]);
});

it("quantity changes reach only the line with those choices", () => {
  const coffee = { menuItemId: "c", name: "Coffee", price: 3, allergenStatus: "no_declared_match" as const, matchedAllergens: [] };
  const milk = { id: "m", group: "Extras", kind: "add" as const, label: "Milk", priceDelta: 0.5 };
  addToCart(coffee, 1);
  addToCart(coffee, 1, undefined, [milk]);
  const cart = updateCartItemQuantity("c", 0, undefined, undefined, ["m"]);
  expect(cart.items).toHaveLength(1);
  expect(cart.items[0].choices ?? []).toEqual([]);
});
```

Add to `ordering.test.ts`:

```ts
it("reads choice refusals", () => {
  expect(orderOutcome(409, { detail: { error: "unavailable_choices", unavailable_choices: [] } })).toBe("choice_gone");
  expect(orderOutcome(422, { detail: { error: "choices_changed", menu_item_id: "x" } })).toBe("choices_changed");
  expect(soldOutChoices({ detail: { unavailable_choices: [{ choice_id: "a", label: "Extra milk" }] } })).toEqual([{ id: "a", label: "Extra milk" }]);
  expect(changedDish({ detail: { error: "choices_changed", menu_item_id: "x" } })).toBe("x");
});
```

- [ ] **Step 2: Run** `pnpm --filter guest-web test`. Expected: FAIL.

- [ ] **Step 3: `lib/choices.ts`**

```ts
export type AllergenStatus = "contains" | "unverified" | "no_declared_match";

export interface Choice {
  id: string;
  label: string;
  price_delta: string;
  allergens: string[];
  is_vegetarian: boolean;
  is_vegan: boolean;
  available: boolean;
  is_default: boolean;
  allergen_status: AllergenStatus;
  matched_allergens: string[];
}

export interface ChoiceGroup {
  id: string;
  label: string;
  kind: "pick" | "add" | "leave_out";
  min_select: number;
  max_select: number;
  choices: Choice[];
}

export interface CartChoice {
  id: string;
  group: string;
  kind: ChoiceGroup["kind"];
  label: string;
  priceDelta: number;
}

const inGroup = (g: ChoiceGroup, picked: string[]) => picked.filter((id) => g.choices.some((c) => c.id === id));

export const isRadio = (g: ChoiceGroup) => g.min_select === 1 && g.max_select === 1;

export function defaultPicks(groups: ChoiceGroup[]): string[] {
  return groups.flatMap((g) => g.choices.filter((c) => c.is_default && c.available).map((c) => c.id));
}

export function firstMissing(groups: ChoiceGroup[], picked: string[]): ChoiceGroup | null {
  return groups.find((g) => inGroup(g, picked).length < g.min_select) ?? null;
}

/** The picks after tapping `id`. A radio button swaps; a full group ignores another tick. */
export function toggle(group: ChoiceGroup, picked: string[], id: string): string[] {
  const mine = inGroup(group, picked);
  const others = picked.filter((p) => !mine.includes(p));
  if (isRadio(group)) return [...others, id];
  if (mine.includes(id)) return picked.filter((p) => p !== id);
  if (group.max_select === 1) return [...others, id];
  return mine.length >= group.max_select ? picked : [...picked, id];
}

export function pickedChoices(groups: ChoiceGroup[], picked: string[]): CartChoice[] {
  return groups.flatMap((g) =>
    g.choices
      .filter((c) => picked.includes(c.id))
      .map((c) => ({ id: c.id, group: g.label, kind: g.kind, label: c.label, priceDelta: Number(c.price_delta) })),
  );
}

export function unitPrice(base: number, groups: ChoiceGroup[], picked: string[]): number {
  return pickedChoices(groups, picked).reduce((sum, c) => sum + c.priceDelta, base);
}

const RANK: AllergenStatus[] = ["no_declared_match", "unverified", "contains"];

/** For display only: the server decides. */
export function worstStatus(dish: AllergenStatus, groups: ChoiceGroup[], picked: string[]): AllergenStatus {
  const statuses = groups.flatMap((g) => g.choices.filter((c) => picked.includes(c.id)).map((c) => c.allergen_status));
  return [dish, ...statuses].reduce((a, b) => (RANK.indexOf(b) > RANK.indexOf(a) ? b : a));
}

export function needsPage(item: { options?: unknown[]; choice_groups?: ChoiceGroup[] }): boolean {
  const groups = item.choice_groups ?? [];
  return (item.options?.length ?? 0) > 0 || firstMissing(groups, defaultPicks(groups)) !== null;
}

export function requirement(g: ChoiceGroup): { key: "chooseOne" | "choose" | "upTo" | "optional"; n: number } {
  if (g.min_select === 1 && g.max_select === 1) return { key: "chooseOne", n: 1 };
  if (g.min_select > 0) return { key: "choose", n: g.min_select };
  return g.max_select > 1 ? { key: "upTo", n: g.max_select } : { key: "optional", n: 1 };
}
```

- [ ] **Step 4: `lib/cart.ts`.**

```ts
import type { CartChoice } from "./choices";
```

`CartItem` gains `choices?: CartChoice[]`. Then:

```ts
const choiceKey = (ids?: string[]) => [...(ids ?? [])].sort().join(",");

/** A cart line is one dish in one size with one set of choices. */
export function lineKey(item: { menuItemId: string; optionId?: string; choices?: CartChoice[] }): string {
  return `${item.menuItemId}:${item.optionId ?? ""}:${choiceKey(item.choices?.map((c) => c.id))}`;
}

function sameLine(a: CartItem, menuItemId: string, optionId?: string, notes?: string, choiceIds?: string[]): boolean {
  return (
    a.menuItemId === menuItemId &&
    (a.optionId ?? "") === (optionId ?? "") &&
    choiceKey(a.choices?.map((c) => c.id)) === choiceKey(choiceIds) &&
    (a.notes || "") === (notes || "")
  );
}
```

`addToCart` gains a fourth parameter `choices: CartChoice[] = []`:

```ts
  const ids = choices.map((c) => c.id);
  const existing = cart.items.find((i) => sameLine(i, item.menuItemId, option?.id, item.notes, ids));
  ...
    const base = option?.price ?? item.price;
    cart.items.push({
      ...item,
      ...(option && { optionId: option.id, optionLabel: option.label }),
      ...(choices.length > 0 && { choices }),
      price: choices.reduce((sum, c) => sum + c.priceDelta, base),
      quantity,
    });
```

`updateCartItemQuantity` gains a fifth parameter `choiceIds?: string[]`, passed to both `sameLine` calls. `toOrderPayload` adds `choice_ids: (i.choices ?? []).map((c) => c.id)`.

- [ ] **Step 5: `lib/ordering.ts`.** Add `"choice_gone" | "choices_changed"` to `OrderOutcome`. In `orderOutcome`, in the 409 block: `if (error === "unavailable_choices") return "choice_gone";`. Before the `too_big` check: `if (status === 422 && error === "choices_changed") return "choices_changed";`. Add:

```ts
export function soldOutChoices(body: unknown): { id: string; label: string }[] {
  const gone = detailOf(body)?.unavailable_choices;
  return Array.isArray(gone) ? gone.map((c) => ({ id: String(c?.choice_id), label: String(c?.label) })) : [];
}

export function changedDish(body: unknown): string | null {
  const id = detailOf(body)?.menu_item_id;
  return typeof id === "string" ? id : null;
}
```

- [ ] **Step 6: Run** `pnpm --filter guest-web test`. Expected: PASS. Fix any existing `lineKey` expectation in `cart.test.ts` that hard-codes the old string, saying so in the commit message.

- [ ] **Step 7: Commit**

```bash
git add apps/guest-web/src/lib
git commit -m "feat(guest): cart lines and refusals know about choices"
```

---

### Task 11: The dish page

**Files:**
- Create: `apps/guest-web/src/components/DishSheet.tsx`
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx`, `apps/guest-web/src/i18n/en.ts`, `it.ts`, `types.ts`

- [ ] **Step 1: Strings.** Add to `types.ts`, `en.ts` and `it.ts` a `dish` block (`it` values in the comments):

```ts
dish: {
  addToOrder: "Add to order · {total}",      // "Aggiungi · {total}"
  chooseGroup: "Choose {group}",             // "Scegli: {group}"
  chooseOne: "Choose 1",                     // "Scegli 1"
  choose: "Choose {n}",                      // "Scegli {n}"
  upTo: "Up to {n}",                         // "Fino a {n}"
  optional: "Optional",                      // "Facoltativo"
  soldOut: "Sold out",                       // "Esaurito"
  size: "Size",                              // "Porzione"
  notVegan: "Not vegan",                     // "Non vegano"
  notVegetarian: "Not vegetarian",           // "Non vegetariano"
  leaveOutNotice: "Leaving something out doesn't make a dish safe for an allergy. Please ask a member of staff.",
  // "Togliere un ingrediente non rende un piatto sicuro per chi ha un'allergia. Chiedi al personale."
  choiceGone: "Sorry, {names} has just run out.",   // "Ci dispiace, {names} è appena finito."
  changed: "This dish has changed. Please choose again.", // "Questo piatto è cambiato. Scegli di nuovo."
  quantity: "Quantity",                      // "Quantità"
},
```

Delete `menu.chooseSize` from all three once nothing uses it (Step 3).

- [ ] **Step 2: `DishSheet.tsx`**

```tsx
"use client";

import React, { useEffect, useRef, useState } from "react";
import { Badge, Button, Sheet } from "ui";
import { AllergenChip } from "./allergen-chip";
import type { TranslationDict } from "../i18n/types";
import {
  defaultPicks, firstMissing, isRadio, pickedChoices, requirement, toggle, unitPrice, worstStatus,
  type AllergenStatus, type CartChoice, type ChoiceGroup,
} from "../lib/choices";

export interface DishSheetItem {
  id: string;
  name: string;
  description?: string | null;
  price: string | number;
  image_url?: string | null;
  allergen_status: AllergenStatus;
  matched_allergens?: string[];
  options?: { id: string; label: string; price: string }[];
  choice_groups?: ChoiceGroup[];
}

export interface DishSheetProps {
  item: DishSheetItem;
  lang: string;
  dict: TranslationDict;
  formatPrice: (n: number) => string;
  /** The guest's dietary preferences, so a choice that doesn't fit can say so. */
  dietary: string[];
  onClose: () => void;
  onAdd: (
    option: { id: string; label: string; price: number } | undefined,
    choices: CartChoice[],
    quantity: number,
    status: AllergenStatus,
    matched: string[],
  ) => void;
}

export function DishSheet({ item, lang, dict, formatPrice, dietary, onClose, onAdd }: DishSheetProps) {
  const groups = item.choice_groups ?? [];
  const sizes = item.options ?? [];
  const [picked, setPicked] = useState(() => defaultPicks(groups));
  const [sizeId, setSizeId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [flagged, setFlagged] = useState<string | null>(null);
  const pushed = useRef(false);

  // The phone's Back closes the sheet. pushState(null) keeps Next's own history state;
  // an entry with custom state makes the router reload the page on Back.
  useEffect(() => {
    window.history.pushState(null, "");
    pushed.current = true;
    const onPop = () => {
      pushed.current = false;
      onClose();
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [onClose]);

  const close = () => {
    if (pushed.current) {
      pushed.current = false;
      window.history.back();
    }
    onClose();
  };

  const size = sizes.find((s) => s.id === sizeId);
  const missingSize = sizes.length > 0 && !size;
  const missing = firstMissing(groups, picked);
  const unit = unitPrice(Number(size?.price ?? item.price), groups, picked);
  const total = formatPrice(unit * quantity);
  const action = missingSize
    ? dict.dish.chooseGroup.replace("{group}", dict.dish.size.toLowerCase())
    : missing
      ? dict.dish.chooseGroup.replace("{group}", missing.label.toLowerCase())
      : dict.dish.addToOrder.replace("{total}", total);

  const add = () => {
    const target = missingSize ? "size" : missing?.id;
    if (target) {
      setFlagged(target);
      const el = document.getElementById(`group-${target}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.focus();
      return;
    }
    const status = worstStatus(item.allergen_status, groups, picked);
    const matched = [
      ...(item.matched_allergens ?? []),
      ...groups.flatMap((g) => g.choices.filter((c) => picked.includes(c.id)).flatMap((c) => c.matched_allergens)),
    ];
    onAdd(
      size && { id: size.id, label: size.label, price: Number(size.price) },
      pickedChoices(groups, picked),
      quantity,
      status,
      [...new Set(matched)],
    );
    close();
  };

  const need = (g: ChoiceGroup) => {
    const r = requirement(g);
    return dict.dish[r.key].replace("{n}", String(r.n));
  };
  const legend = "flex items-baseline justify-between gap-3 text-base font-semibold text-ink";
  const row = "flex min-h-11 cursor-pointer items-center gap-3 py-1 text-sm text-ink";
  const box = (id: string) =>
    `space-y-1 rounded-xl p-2 outline-none ${flagged === id ? "ring-2 ring-danger-fg" : ""}`;

  return (
    <Sheet
      open
      onClose={close}
      title={item.name}
      footer={
        <div className="flex items-center gap-3">
          <div role="group" aria-label={dict.dish.quantity} className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              aria-label={dict.ui.decrease}
              onClick={() => setQuantity((q) => Math.max(1, q - 1))}
            >
              −
            </Button>
            <span className="w-5 text-center text-sm font-semibold tabular-nums">{quantity}</span>
            <Button
              variant="outline"
              size="icon"
              aria-label={dict.ui.increase}
              onClick={() => setQuantity((q) => Math.min(20, q + 1))}
            >
              +
            </Button>
          </div>
          <Button className="min-h-12 flex-1 text-base" onClick={add}>
            <span aria-live="polite">{action}</span>
          </Button>
        </div>
      }
    >
      {item.image_url && (
        <img src={item.image_url} alt="" className="aspect-[4/3] w-full rounded-xl object-cover" />
      )}
      {item.description && <p className="text-sm text-ink-muted">{item.description}</p>}
      <AllergenChip status={item.allergen_status} matchedAllergens={item.matched_allergens} locale={lang} />

      {sizes.length > 0 && (
        <fieldset id="group-size" tabIndex={-1} className={box("size")}>
          <legend className={`${legend} w-full`}>
            <span>{dict.dish.size}</span>
            <span className="text-xs font-normal text-ink-muted">{dict.dish.chooseOne}</span>
          </legend>
          {sizes.map((s) => (
            <label key={s.id} className={row}>
              <input
                type="radio"
                name="size"
                checked={sizeId === s.id}
                onChange={() => {
                  setSizeId(s.id);
                  setFlagged(null);
                }}
                className="h-5 w-5 accent-terracotta"
              />
              <span className="flex-1">{s.label}</span>
              <span className="tabular-nums">{formatPrice(Number(s.price))}</span>
            </label>
          ))}
        </fieldset>
      )}

      {groups.map((g) => {
        const mine = g.choices.filter((c) => picked.includes(c.id)).length;
        const full = !isRadio(g) && g.max_select > 1 && mine >= g.max_select;
        return (
          <fieldset key={g.id} id={`group-${g.id}`} tabIndex={-1} className={box(g.id)}>
            <legend className={`${legend} w-full`}>
              <span>{g.label}</span>
              <span className="text-xs font-normal text-ink-muted">{need(g)}</span>
            </legend>
            {g.kind === "leave_out" && <p className="text-xs text-ink-muted">{dict.dish.leaveOutNotice}</p>}
            {g.choices.map((c) => {
              const on = picked.includes(c.id);
              const notFit =
                dietary.includes("vegan") && !c.is_vegan
                  ? dict.dish.notVegan
                  : dietary.includes("vegetarian") && !c.is_vegetarian
                    ? dict.dish.notVegetarian
                    : null;
              return (
                <label key={c.id} className={`${row} ${c.available ? "" : "opacity-50"}`}>
                  <input
                    type={isRadio(g) ? "radio" : "checkbox"}
                    name={g.id}
                    checked={on}
                    disabled={!c.available || (full && !on)}
                    onChange={() => {
                      setPicked((p) => toggle(g, p, c.id));
                      setFlagged(null);
                    }}
                    className="h-5 w-5 accent-terracotta"
                  />
                  <span className="flex-1">
                    {c.label}
                    {!c.available && <span className="ml-2 text-xs italic">{dict.dish.soldOut}</span>}
                  </span>
                  {c.allergen_status !== "no_declared_match" && (
                    <AllergenChip status={c.allergen_status} matchedAllergens={c.matched_allergens} locale={lang} />
                  )}
                  {notFit && <Badge>{notFit}</Badge>}
                  {Number(c.price_delta) > 0 && (
                    <span className="tabular-nums">+{formatPrice(Number(c.price_delta))}</span>
                  )}
                </label>
              );
            })}
          </fieldset>
        );
      })}
    </Sheet>
  );
}
```

`Sheet` calls `onClose` on the dialog's `close` event, so `close` must be idempotent: the `pushed` ref makes it so. Pass a stable `onClose` from the page (`useCallback`), or the effect re-runs and pushes again. Render `DishSheet` only while a dish is open, with `key={dish.id}`, so its state starts fresh. The `.sheet` is 90vh tall on phones, which is the spec's "full height" within the existing component.

- [ ] **Step 3: `menu/page.tsx`.**

(a) `MenuItem` gains `image_url?: string | null` and `choice_groups?: ChoiceGroup[]`.

(b) Replace `sizePickerItem` state, `pickerItem` and the size `Sheet` with:

```tsx
const [dishOpen, setDishOpen] = useState<MenuItem | null>(null);
const closeDish = useCallback(() => setDishOpen(null), []);
```

and, in place of the removed `<Sheet>`:

```tsx
{dishOpen && (
  <DishSheet
    key={dishOpen.id}
    item={dishOpen}
    lang={lang}
    dict={dict}
    formatPrice={formatPrice}
    dietary={status?.dietary_preferences ?? []}
    onClose={closeDish}
    onAdd={(option, choices, quantity, allergenStatus, matched) => {
      setNotice(null);
      const updated = addToCart(
        {
          menuItemId: dishOpen.id,
          name: dishOpen.name,
          price: Number(dishOpen.price),
          allergenStatus,
          matchedAllergens: matched,
        },
        quantity,
        option,
        choices,
      );
      setCart({ ...updated });
    }}
  />
)}
```

`status` is what `useTableStatus` already gives this page. It comes from `GuestSessionStatusResponse`, which extends `GuestSessionResponse` and so carries `dietary_preferences`. Add the field to the hook's type if it is missing there.

(c) The dish row. `handleAddToCart` uses the dish's defaults:

```tsx
const handleAddToCart = (item: MenuItem) => {
  setNotice(null);
  const groups = item.choice_groups ?? [];
  const picks = defaultPicks(groups);
  const updated = addToCart(
    {
      menuItemId: item.id,
      name: item.name,
      price: Number(item.price),
      allergenStatus: worstStatus(item.allergen_status, groups, picks),
      matchedAllergens: item.matched_allergens || [],
    },
    1,
    undefined,
    pickedChoices(groups, picks),
  );
  setCart({ ...updated });
};
```

The + button: `onClick={() => (needsPage(item) ? setDishOpen(item) : handleAddToCart(item))}`. The heading becomes a button that opens the page, available dishes only:

```tsx
<h3 className="text-base font-semibold text-ink">
  {isAvailable ? (
    <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => setDishOpen(item)}>
      {item.name}
    </button>
  ) : (
    item.name
  )}
</h3>
```

Above the name, when `item.image_url` is set, add the same tap target as a photo: a `<button>` with `aria-label={item.name}`, holding `<img loading="lazy" alt="" className="aspect-[16/9] w-full rounded-xl object-cover" />`.

The accessible name `Add ${item.name}` stays, so one-tap browser stories keep working.

(d) Cart lines. Under the name:

```tsx
{item.choices && item.choices.length > 0 && (
  <p className={`text-xs ${item.choices.some((c) => goneChoices.has(c.id)) ? "text-danger-fg" : "text-ink-muted"}`}>
    {item.choices
      .map((c) => (c.kind === "leave_out" ? `No ${c.label.toLowerCase()}` : c.label))
      .join(", ")}
    {item.choices.some((c) => goneChoices.has(c.id)) && ` · ${dict.dish.soldOut}`}
  </p>
)}
```

with `const [goneChoices, setGoneChoices] = useState<Set<string>>(new Set());`.

Pass choice ids through every quantity call: `handleUpdateQuantity` gains a fifth argument, and the two buttons pass `item.choices?.map((c) => c.id)`. Add the choice labels to their aria-labels so two lines of one dish can be told apart.

(e) Refusals, in `handleCheckout`, before the `allergen` branch:

```tsx
} else if (outcome === "choice_gone") {
  const gone = soldOutChoices(body);
  setGoneChoices(new Set(gone.map((c) => c.id)));
  showError(dict.dish.choiceGone.replace("{names}", gone.map((c) => c.label).join(", ")));
} else if (outcome === "choices_changed") {
  const id = changedDish(body);
  const fresh = await fetchMenu();
  const dish = fresh?.items.find((i) => i.id === id);
  if (id) {
    const next = { ...cart, items: cart.items.filter((i) => i.menuItemId !== id) };
    saveCart(next);
    setCart(next);
  }
  setCartOpen(false);
  setNotice(dict.dish.changed);
  if (dish) setDishOpen(dish);
```

Extract the fetch inside `loadMenu` into `fetchMenu(): Promise<Menu | null>`, which sets `menu` and returns it. The removed line reappears when the guest re-adds it from the page that just opened, and the notice says why, so nothing vanishes silently.

(f) The declined-order restore. Add `choices?: { choice_id: string }[]` to the fetched item type. Then:

```tsx
const groups = item?.choice_groups ?? [];
const ids = (line.choices ?? []).map((c) => c.choice_id);
const picks = pickedChoices(groups, ids);
if (!item || item.available === false || (line.option_id && !option) || picks.length !== ids.length) continue;
```

Pass `picks` as `addToCart`'s fourth argument, and `allergenStatus: worstStatus(item.allergen_status, groups, ids)`.

- [ ] **Step 4: Run** `pnpm --filter guest-web test && pnpm --filter guest-web lint && pnpm --filter guest-web build`. Expected: PASS. Rendering is proved in Task 14.

- [ ] **Step 5: Commit**

```bash
git add apps/guest-web/src
git commit -m "feat(guest): tap a dish to choose size, spice, extras and leave-outs"
```

---

### Task 12: Kitchen, bills and order pages show choices

**Files:**
- Create: `packages/ui/src/choices.ts` (exported from `packages/ui/src/index.ts`), `packages/ui/src/choices.test.ts`
- Modify: `apps/owner-web/src/app/(kitchen)/kitchen/page.tsx`, `apps/owner-web/src/app/(dashboard)/bills/page.tsx`, `apps/owner-web/src/lib/bill.ts`, `apps/owner-web/src/lib/bill.test.ts`, `apps/guest-web/src/components/PaySheet.tsx`, `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`

- [ ] **Step 1: Write the failing test** (`packages/ui/src/choices.test.ts`)

```ts
import { describe, expect, it } from "vitest";
import { choiceLine } from "./choices";

const money = (n: number) => `£${n.toFixed(2)}`;

describe("choiceLine", () => {
  it("shows a paid extra with its price", () => {
    expect(choiceLine({ kind: "add", label: "Extra milk", price_delta: "0.50" }, money)).toBe("Extra milk +£0.50");
  });
  it("shows a free choice as its label", () => {
    expect(choiceLine({ kind: "pick", label: "Mild", price_delta: "0.00" }, money)).toBe("Mild");
  });
  it("says No for a leave-out", () => {
    expect(choiceLine({ kind: "leave_out", label: "Onions", price_delta: "0" }, money)).toBe("No onions");
  });
});
```

- [ ] **Step 2: Run** `pnpm --filter ui test`. Expected: FAIL.

- [ ] **Step 3: `packages/ui/src/choices.ts`**

```ts
export interface LineChoice {
  kind: "pick" | "add" | "leave_out";
  label: string;
  price_delta: string | number;
}

export function choiceLine(c: LineChoice, money: (n: number) => string): string {
  if (c.kind === "leave_out") return `No ${c.label.toLowerCase()}`;
  const price = Number(c.price_delta);
  return price > 0 ? `${c.label} +${money(price)}` : c.label;
}
```

- [ ] **Step 4: Kitchen page.** The item type gains `choices?: LineChoice[]`. After the dish row (before the allergy banner):

```tsx
{(item.choices ?? []).length > 0 && (
  <ul className="mt-1.5 space-y-0.5 text-right text-sm">
    {item.choices!.map((c) =>
      c.kind === "leave_out" ? (
        <li key={c.label} className="font-black uppercase text-kds-warn">
          NO {c.label}
        </li>
      ) : (
        <li key={c.label} className="text-cream">
          {c.label}
        </li>
      ),
    )}
  </ul>
)}
```

- [ ] **Step 5: Bills and guest pages.** In each place that prints `option_label`, add the choices under the name:

```tsx
{(l.choices ?? []).length > 0 && (
  <span className="block text-xs text-ink-muted">
    {l.choices!.map((c) => choiceLine(c, money)).join(", ")}
  </span>
)}
```

Use each page's own money formatter. Places:
- `apps/guest-web/src/components/PaySheet.tsx:134`, and the voided line at `:142`
- `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx:324`, and the voided line at `:286`
- `apps/owner-web/src/app/(dashboard)/bills/page.tsx:713`
- `apps/owner-web/src/lib/bill.ts:385`: the printed label gains the same text, joined with ` · `. Add `choices?: LineChoice[]` to its line type, and a test to `bill.test.ts` beside the existing printed-label test, using that file's fixtures:

```ts
it("a printed line lists its choices", () => {
  const withMilk = { ...LINE, choices: [{ kind: "add" as const, label: "Extra milk", price_delta: "50" }] };
  expect(printedRows({ ...BILL, lines: [withMilk] })[0].label).toContain("Extra milk");
});
```

`LINE`, `BILL` and `printedRows` stand for that file's line fixture, bill fixture and the function at `bill.ts:385`. Printed bills keep their footer and never gain tax-invoice wording.

- [ ] **Step 6: Run** `pnpm -r test`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/ui apps
git commit -m "feat: kitchen tickets, bills and order pages list choices"
```

---

### Task 13: Owner Menu page and extras card

**Files:**
- Create: `apps/owner-web/src/components/ChoiceEditor.tsx`, `apps/owner-web/src/components/ChoiceEditor.test.tsx`
- Modify: `apps/owner-web/src/app/(dashboard)/menu/page.tsx`, `apps/owner-web/src/app/(dashboard)/brief/page.tsx`, `apps/owner-web/src/lib/analytics.ts`

- [ ] **Step 1: Write the failing test.** Render the way `ServiceReportCard.test.tsx` does, and stub `fetch`.

```tsx
it("lists groups and their choices with prices and allergens", () => {
  const html = render(
    <ChoiceEditor slug="v" itemId="i" groups={[GROUP]} money={(n) => `£${n.toFixed(2)}`} onChanged={() => {}} />,
  );
  expect(html).toContain("Extras");
  expect(html).toContain("Extra milk");
  expect(html).toContain("+£0.50");
  expect(html).toContain("milk");
  expect(html).toContain("Unconfirmed");
});
```

`GROUP` is one `add` group holding `Extra milk`, `price_delta: "0.50"`, `allergens: ["milk"]`, `allergen_verified: false`.

- [ ] **Step 2: Run** `pnpm --filter owner-web test`. Expected: FAIL.

- [ ] **Step 3: `ChoiceEditor.tsx`**

```tsx
"use client";

import React, { useState } from "react";
import { Button } from "ui";

export const ALLERGENS = [
  "gluten", "milk", "eggs", "fish", "crustaceans", "molluscs", "tree_nuts", "peanuts", "soy",
  "celery", "mustard", "sesame", "sulphites", "lupin",
];

export interface OwnerChoice {
  id: string;
  label: string;
  price_delta: string;
  cost_delta: string;
  allergens: string[];
  allergen_verified: boolean;
  is_vegetarian: boolean;
  is_vegan: boolean;
  available: boolean;
  is_default: boolean;
  sort_order: number;
}

export interface OwnerChoiceGroup {
  id: string;
  label: string;
  kind: "pick" | "add" | "leave_out";
  min_select: number;
  max_select: number;
  sort_order: number;
  choices: OwnerChoice[];
}

const KINDS = { pick: "Pick one", add: "Add extras", leave_out: "Leave out" } as const;
const PRESET = {
  pick: { min_select: 1, max_select: 1 },
  add: { min_select: 0, max_select: 3 },
  leave_out: { min_select: 0, max_select: 5 },
};

type Send = (path: string, method: string, body?: unknown) => Promise<boolean>;

interface Props {
  slug: string;
  itemId: string;
  groups: OwnerChoiceGroup[];
  money: (n: number) => string;
  onChanged: () => void;
}

export function ChoiceEditor({ slug, itemId, groups, money, onChanged }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<keyof typeof KINDS>("pick");
  const base = `/api/restaurants/${slug}`;

  const send: Send = async (path, method, body) => {
    setError(null);
    const res = await fetch(`${base}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => null))?.detail;
      setError(typeof detail === "string" ? detail : "That change wasn't saved. Check the details and try again.");
      return false;
    }
    onChanged();
    return true;
  };

  // Swap positions: a neighbour's sort_order may equal this one's after seeding or adding.
  const moveGroup = async (i: number, by: number) => {
    const other = groups[i + by];
    if (!other) return;
    await send(`/choice-groups/${groups[i].id}`, "PATCH", { sort_order: i + by });
    await send(`/choice-groups/${other.id}`, "PATCH", { sort_order: i });
  };

  return (
    <div className="space-y-3 border-t border-line pt-3">
      <h4 className="text-sm font-semibold text-ink">Choices</h4>
      {error && <p role="alert" className="text-sm text-danger-fg">{error}</p>}
      {groups.map((g, i) => (
        <div key={g.id} className="space-y-2 rounded-xl bg-paper-2 p-3">
          <div className="flex items-center justify-between gap-2 text-sm font-semibold text-ink">
            <span>
              {g.label} · {KINDS[g.kind]} · {g.min_select > 0 ? "required" : "optional"}, up to {g.max_select}
            </span>
            <span className="flex gap-1">
              <Button variant="outline" size="icon" aria-label={`Move ${g.label} up`} onClick={() => void moveGroup(i, -1)}>↑</Button>
              <Button variant="outline" size="icon" aria-label={`Move ${g.label} down`} onClick={() => void moveGroup(i, 1)}>↓</Button>
              <Button variant="outline" aria-label={`Delete ${g.label}`} onClick={() => void send(`/choice-groups/${g.id}`, "DELETE")}>Delete</Button>
            </span>
          </div>
          <ul className="space-y-2">
            {g.choices.map((c) => (
              <ChoiceRow key={c.id} choice={c} kind={g.kind} money={money} send={send} />
            ))}
          </ul>
          <NewChoice groupId={g.id} kind={g.kind} send={send} />
        </div>
      ))}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(`/menu-items/${itemId}/choice-groups`, "POST", {
            label,
            kind,
            ...PRESET[kind],
            sort_order: groups.length,
          }).then((ok) => ok && setLabel(""));
        }}
      >
        <label className="text-xs text-ink-muted">
          New group
          <input required value={label} onChange={(e) => setLabel(e.target.value)} className="mt-1 block rounded-lg border border-line bg-card p-2 text-sm text-ink" />
        </label>
        <label className="text-xs text-ink-muted">
          Type
          <select value={kind} onChange={(e) => setKind(e.target.value as keyof typeof KINDS)} className="mt-1 block rounded-lg border border-line bg-card p-2 text-sm text-ink">
            {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <Button type="submit" variant="outline">Add group</Button>
      </form>
    </div>
  );
}

function ChoiceRow({
  choice: c, kind, money, send,
}: {
  choice: OwnerChoice;
  kind: OwnerChoiceGroup["kind"];
  money: (n: number) => string;
  send: Send;
}) {
  const patch = (body: object) => void send(`/choices/${c.id}`, "PATCH", body);
  const toggleAllergen = (a: string) =>
    patch({ allergens: c.allergens.includes(a) ? c.allergens.filter((x) => x !== a) : [...c.allergens, a] });
  return (
    <li className="space-y-1 text-sm text-ink">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {c.label}
          {Number(c.price_delta) > 0 && <span className="tabular-nums"> +{money(Number(c.price_delta))}</span>}
        </span>
        <span className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={c.available} onChange={(e) => patch({ available: e.target.checked })} /> On sale
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={c.is_default} onChange={(e) => patch({ is_default: e.target.checked })} /> Starts selected
          </label>
          <button type="button" className="underline" onClick={() => void send(`/choices/${c.id}`, "DELETE")}>Delete</button>
        </span>
      </div>
      {kind !== "leave_out" && (
        <details className="text-xs">
          <summary className="cursor-pointer">
            Allergens: {c.allergens.join(", ") || "none"} · {c.allergen_verified ? "Confirmed" : "Unconfirmed"}
          </summary>
          <div className="mt-1 flex flex-wrap gap-2">
            {ALLERGENS.map((a) => (
              <label key={a} className="flex items-center gap-1">
                <input type="checkbox" checked={c.allergens.includes(a)} onChange={() => toggleAllergen(a)} /> {a}
              </label>
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-3">
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={c.allergen_verified} onChange={(e) => patch({ allergen_verified: e.target.checked })} /> Allergens confirmed
            </label>
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={c.is_vegetarian} onChange={(e) => patch({ is_vegetarian: e.target.checked })} /> Vegetarian
            </label>
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={c.is_vegan} onChange={(e) => patch({ is_vegan: e.target.checked })} /> Vegan
            </label>
          </div>
        </details>
      )}
    </li>
  );
}

function NewChoice({ groupId, kind, send }: { groupId: string; kind: OwnerChoiceGroup["kind"]; send: Send }) {
  const [label, setLabel] = useState("");
  const [price, setPrice] = useState("0");
  const [cost, setCost] = useState("0");
  const field = "mt-1 block w-24 rounded-lg border border-line bg-card p-2 text-sm text-ink";
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const money = kind === "leave_out" ? {} : { price_delta: price, cost_delta: cost };
        void send(`/choice-groups/${groupId}/choices`, "POST", { label, ...money }).then((ok) => ok && setLabel(""));
      }}
    >
      <label className="text-xs text-ink-muted">
        New choice
        <input required value={label} onChange={(e) => setLabel(e.target.value)} className={`${field} w-40`} />
      </label>
      {kind !== "leave_out" && (
        <>
          <label className="text-xs text-ink-muted">
            Price
            <input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} className={field} />
          </label>
          <label className="text-xs text-ink-muted">
            Cost
            <input type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} className={field} />
          </label>
        </>
      )}
      <Button type="submit" variant="outline">Add</Button>
    </form>
  );
}
```

- [ ] **Step 4: Menu page.** `OwnerMenuItem` gains `choice_groups: OwnerChoiceGroup[]` and `is_pay_forward: boolean`. In each dish card, after the existing details:

```tsx
{!item.is_pay_forward && (
  <details>
    <summary className="cursor-pointer text-sm font-semibold text-ink">
      Choices ({item.choice_groups.length})
    </summary>
    <ChoiceEditor slug={slug!} itemId={item.id} groups={item.choice_groups} money={money} onChanged={loadMenuItems} />
  </details>
)}
```

`money` uses `formatPrice` from `ui` with `venue.currency`, the way other owner pages do. A `<details>` stays open across a reload of the list because rows are keyed by `item.id`.

- [ ] **Step 5: Extras card.** `analytics.ts` type gains `extras: { attach_rate_pct: number; sales: number; top: { label: string; count: number }[] }`, beside `service_charge_collected`. In `brief/page.tsx`, beside the service-charge tile:

```tsx
{brief.extras.top.length > 0 && (
  <StatTile
    label={exVat("Extras sales", vat)}
    value={money(brief.extras.sales, brief.currency)}
    sub={`Added to ${brief.extras.attach_rate_pct}% of lines. Top: ${brief.extras.top.map((t) => `${t.label} (${t.count})`).join(", ")}`}
  />
)}
```

Add `extras` to any brief fixture the owner tests build. In the what-if section's help text, add: "Changes base prices only; extras stay as they are."

- [ ] **Step 6: Run** `pnpm --filter owner-web test && pnpm --filter owner-web lint`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/owner-web/src
git commit -m "feat(owner): edit dish choices and see how often extras are added"
```

---

### Task 14: Browser stories

**Files:**
- Modify: `e2e/flows.spec.ts`, `e2e/self-service.spec.ts`, `e2e/helpers.ts`
- Create: `e2e/dish-choices.spec.ts`

The size chooser is gone, so stories that use it change. The spec approved this, so these are correct test changes, not weakened ones. Say so in the commit message.

- [ ] **Step 1: Helper** in `e2e/helpers.ts`:

```ts
/** Open a dish's page from its + button and add it with these picks (radio or checkbox names). */
export async function addWithChoices(page: Page, dish: string, picks: string[]) {
  await page.getByRole("button", { name: `Add ${dish}`, exact: true }).click();
  const sheet = page.getByRole("dialog", { name: dish });
  await expect(sheet).toBeVisible();
  for (const pick of picks) await sheet.getByText(pick, { exact: true }).click();
  await sheet.getByRole("button", { name: /Add to order/ }).click();
  await expect(sheet).toBeHidden();
}
```

- [ ] **Step 2: Update stories.**
  - `e2e/flows.spec.ts:38-43`: replace the chooser steps with `await addWithChoices(page, "Chicken Karahi", ["1 kg", "Medium"]);`. Before it, take the screenshot `dish-sheet-phone.png` with the sheet open, in place of `size-sheet-phone.png`.
  - `e2e/flows.spec.ts:156-157`: `await addWithChoices(page, "Cappuccino", ["Regular"]);`.
  - `e2e/self-service.spec.ts:86-87`: `await addWithChoices(guest, "Chicken Karahi", ["1 kg", "Medium"]);`.
  - Totals in those stories are unchanged: Medium is free.

- [ ] **Step 3: New story** `e2e/dish-choices.spec.ts`. Copy the setup of `e2e/self-service.spec.ts` story 10: `demoInfo`, opening the table, a 375x812 phone context bound to `page`, and a `staff` page from `staffPage`. Copy the settle steps from that story too. The three tests:

```ts
test.describe.serial("Dish choices: a phone guest makes it theirs", () => {
  test("sent to what is missing, leave-out notice, kitchen sees NO ONIONS, bill lists it", async ({ browser }) => {
    await page.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Chicken Karahi" });

    // The action names what is missing and takes the guest there
    await sheet.getByRole("button", { name: "Choose size" }).click();
    await expect(sheet.locator("#group-size")).toBeFocused();
    await sheet.getByText("1 kg", { exact: true }).click();
    await sheet.getByRole("button", { name: "Choose spice" }).click();
    await sheet.getByText("Hot", { exact: true }).click();

    await expect(sheet.getByText("Leaving something out doesn't make a dish safe")).toBeVisible();

    // Back closes the sheet and the phone stays on the menu
    await page.goBack();
    await expect(sheet).toBeHidden();
    await expect(page).toHaveURL(/\/en\/menu$/);

    await addWithChoices(page, "Chicken Karahi", ["1 kg", "Hot", "Onions"]);
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(page.getByRole("dialog", { name: "Your Order" }).getByText("Hot, No onions")).toBeVisible();
    const id = await placeOrder(page);
    await approveOrder(id);

    await staff.goto(`${OWNER}/kitchen`);
    await expect(staff.getByText("NO Onions")).toBeVisible();

    await staff.goto(`${OWNER}/bills`);
    await staff.getByText(venue.table_label).first().click();
    await expect(staff.getByText("No onions", { exact: false })).toBeVisible();
  });

  test("a chai with defaults still adds in one tap", async ({ browser }) => {
    await page.getByRole("button", { name: "Add Doodh Patti Chai", exact: true }).click();
    await expect(page.getByRole("button", { name: /View order/ })).toBeVisible();
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("extra milk warns a guest avoiding milk", async ({ browser }) => {
    // On the welcome screen, tick Milk before View Menu. Open the page from the dish name.
    await page.getByRole("button", { name: "Doodh Patti Chai", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Doodh Patti Chai" });
    await sheet.getByText("Extra milk", { exact: false }).click();
    await sheet.getByRole("button", { name: /Add to order/ }).click();
    await page.getByRole("button", { name: /View order/ }).click();
    await expect(page.getByText("Allergen Warning")).toBeVisible();
  });

  test("the phone-width dish page has no sideways scroll and a reachable action", async ({ browser }) => {
    await page.getByRole("button", { name: "Add Chicken Karahi", exact: true }).click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
    await expect(page.getByRole("button", { name: "Choose size" })).toBeInViewport();
  });
});
```

Match `Allergen Warning` to `dict.ui.allergenWarningTitle` in `en.ts`.

- [ ] **Step 4: Run the stack checks**

```bash
LLM_PROVIDER=mock DEMO_MODE=true bash scripts/verify_phase1.sh
```

Expected: every step PASS. On failure it keeps the full log at `${TMPDIR:-/tmp}/verify-failed-XXXXXX.log`. Git Bash mangles `/tmp` paths: use `MSYS_NO_PATHCONV=1`.

- [ ] **Step 5: Commit**

```bash
git add e2e scripts
git commit -m "test(e2e): browser stories for the dish page; size is now chosen there"
```

---

### Task 15: Docs and the full check

**Files:** `README.md`, `docs/architecture.md`, `docs/analytics.md`, `CLAUDE.md`

- [ ] **Step 1: `CLAUDE.md`,** under Architecture, after the allergen line:

```markdown
- A dish choice can add an allergen, never remove one; 'leave out' has no allergen effect.
```

- [ ] **Step 2: Docs.** `README.md`: one line on dish choices in the guest features. `docs/architecture.md`: the two tables, the `order_item.choices` snapshot and `services/choices.py`. `docs/analytics.md`: the extras card, its definitions, and that the what-if tool changes base prices only.

- [ ] **Step 3: Full run**

```bash
make ci
LLM_PROVIDER=mock DEMO_MODE=true bash scripts/verify_phase1.sh
```

Expected: lint clean, all tests pass, branding check passes, every verify step PASS. If `make` is missing, prepend the session's make shim folder to `PATH`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs CLAUDE.md
git commit -m "docs: dish choices"
```
