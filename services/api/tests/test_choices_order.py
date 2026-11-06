"""Placing an order with dish choices: server prices, allergen union, hashing, snapshots."""

import hashlib
import json
import uuid
from decimal import Decimal

from tests.choices_setup import line, order, tea_setup  # noqa: F401 - fixture

from src.models.menu import (
    MenuChoice,
    MenuChoiceGroup,
    MenuItem,
    MenuItemOption,
    MenuTranslation,
)
from src.models.order import OrderItem


async def test_server_prices_the_line(client, tea_setup):  # noqa: F811
    s = tea_setup
    resp = await order(client, "k1", [line(s, s.mild, s.extra_milk, quantity=2)], ack=True)
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "700.00"
    item = body["items"][0]
    assert item["unit_price"] == "350.00"
    assert [c["label"] for c in item["choices"]] == ["Mild", "Extra milk"]
    assert "cost_delta" not in item["choices"][0]


async def test_cost_is_snapshotted(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    resp = await order(client, "k2", [line(s, s.mild, s.extra_milk)], ack=True)
    row = await db_session.get(OrderItem, uuid.UUID(resp.json()["items"][0]["id"]))
    assert row.unit_cost == Decimal("72.00")
    assert row.allergens == ["milk"]


async def test_extra_milk_stops_at_the_acknowledgement(client, tea_setup):  # noqa: F811
    s = tea_setup  # this session avoids milk
    resp = await order(client, "k3", [line(s, s.mild, s.extra_milk)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "allergen_ack_required"
    assert resp.json()["detail"]["items"][0]["matched_allergens"] == ["milk"]
    resp = await order(client, "k3", [line(s, s.mild, s.extra_milk)], ack=True)
    assert resp.status_code == 201
    assert resp.json()["items"][0]["allergen_status"] == "contains"


async def test_unconfirmed_choice_needs_the_acknowledgement(client, tea_setup):  # noqa: F811
    s = tea_setup
    resp = await order(client, "k4", [line(s, s.mild, s.honey)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["items"][0]["status"] == "unverified"
    resp = await order(client, "k4", [line(s, s.mild, s.honey)], ack=True)
    assert resp.status_code == 201
    item = resp.json()["items"][0]
    assert item["allergen_status"] == "unverified"
    assert item["allergen_verified"] is False


async def test_leave_out_changes_nothing(client, tea_setup):  # noqa: F811
    s = tea_setup
    item = (await order(client, "k5", [line(s, s.mild, s.no_sugar)])).json()["items"][0]
    assert item["allergens"] == []
    assert item["allergen_status"] == "no_declared_match"
    assert item["unit_price"] == "300.00"


async def test_repeated_choice_is_refused(client, tea_setup):  # noqa: F811
    s = tea_setup
    resp = await order(client, "k6", [line(s, s.mild, s.mild)])
    assert resp.status_code == 422


async def test_missing_required_choice_is_choices_changed(client, tea_setup):  # noqa: F811
    resp = await order(client, "k7", [line(tea_setup)])
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "choices_changed"


async def test_sold_out_choice_is_refused(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    s.mild.available = False
    await db_session.flush()
    resp = await order(client, "k8", [line(s, s.mild)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "unavailable_choices"


async def test_required_group_sold_out_stops_the_dish(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    s.mild.available = False
    s.hot.available = False
    await db_session.flush()
    resp = await order(client, "k9", [line(s)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "unavailable_items"


async def test_retry_with_choices_in_any_order_is_a_retry(client, tea_setup):  # noqa: F811
    s = tea_setup
    first = await order(client, "k10", [line(s, s.mild, s.no_sugar)])
    again = await order(client, "k10", [line(s, s.no_sugar, s.mild)])
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]


async def test_same_key_with_other_choices_conflicts(client, tea_setup):  # noqa: F811
    s = tea_setup
    first = await order(client, "k11", [line(s, s.mild)])
    assert first.status_code == 201
    again = await order(client, "k11", [line(s, s.hot)])
    assert again.status_code == 409
    assert again.json()["detail"] == {"error": "already_sent", "order_id": first.json()["id"]}


async def test_retry_with_lines_reversed_is_a_retry(client, tea_setup):  # noqa: F811
    s = tea_setup
    first = await order(client, "k18", [line(s, s.mild), line(s, s.hot)])
    again = await order(client, "k18", [line(s, s.hot), line(s, s.mild)])
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]


def test_a_line_without_choices_keeps_its_old_hash():
    from src.routers.orders import compute_payload_hash
    from src.schemas.orders import OrderItemRequest

    menu_item_id = uuid.UUID(int=1)
    canonical = [{"menu_item_id": str(menu_item_id), "option_id": "", "quantity": 1, "notes": ""}]
    expected = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    assert (
        compute_payload_hash([OrderItemRequest(menu_item_id=menu_item_id, quantity=1)]) == expected
    )


async def test_menu_price_change_leaves_old_lines(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    placed = (await order(client, "k12", [line(s, s.mild, s.no_sugar)])).json()
    s.tea.price = Decimal("999.00")
    await db_session.flush()
    fetched = (await client.get(f"/api/orders/{placed['id']}")).json()
    assert fetched["items"][0]["unit_price"] == "300.00"


async def _soup(db_session, restaurant, extras_min=0):
    """A dish with a Half/Full size and an Extras group (0/2), and its choices."""
    soup = MenuItem(
        restaurant_id=restaurant.id,
        category="mains",
        price=Decimal("500.00"),
        unit_cost=Decimal("200.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
        sort_order=2,
    )
    soup.translations = [MenuTranslation(language="en", name="Soup")]
    db_session.add(soup)
    await db_session.flush()
    full = MenuItemOption(
        menu_item_id=soup.id, label="Full", price=Decimal("800.00"), unit_cost=Decimal("350.00")
    )
    group = MenuChoiceGroup(
        menu_item_id=soup.id, label="Extras", kind="add", min_select=0, max_select=2
    )
    db_session.add_all([full, group])
    await db_session.flush()
    bread = MenuChoice(
        group_id=group.id,
        label="Bread",
        price_delta=Decimal("40.00"),
        cost_delta=Decimal("10.00"),
        allergen_verified=True,
        sort_order=0,
    )
    egg = MenuChoice(
        group_id=group.id,
        label="Egg",
        price_delta=Decimal("25.00"),
        cost_delta=Decimal("7.00"),
        allergen_verified=True,
        sort_order=1,
    )
    db_session.add_all([bread, egg])
    await db_session.flush()
    return soup, full, bread, egg


async def test_unknown_choice_is_choices_changed(client, tea_setup):  # noqa: F811
    s = tea_setup
    bogus = {
        "menu_item_id": str(s.tea.id),
        "quantity": 1,
        "choice_ids": [str(s.mild.id), str(uuid.uuid4())],
    }
    resp = await order(client, "k14", [bogus])
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "choices_changed"


async def test_choice_from_another_dish_is_choices_changed(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    _, _, bread, _ = await _soup(db_session, s.restaurant)
    resp = await order(client, "k15", [line(s, s.mild, bread)])
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "choices_changed"


async def test_too_many_in_a_group_is_choices_changed(client, tea_setup):  # noqa: F811
    s = tea_setup
    resp = await order(client, "k16", [line(s, s.mild, s.hot)])
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "choices_changed"


async def test_size_plus_extras_add_up(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    soup, full, bread, egg = await _soup(db_session, s.restaurant)
    resp = await order(
        client,
        "k17",
        [
            {
                "menu_item_id": str(soup.id),
                "option_id": str(full.id),
                "quantity": 1,
                "choice_ids": [str(bread.id), str(egg.id)],
            }
        ],
    )
    assert resp.status_code == 201
    item = resp.json()["items"][0]
    assert item["unit_price"] == "865.00"
    row = await db_session.get(OrderItem, uuid.UUID(item["id"]))
    assert row.unit_cost == Decimal("367.00")


async def test_menu_sends_choices_with_status_and_no_cost(client, tea_setup):  # noqa: F811
    menu = (await client.get("/api/guest/menu")).json()
    tea = next(i for i in menu["items"] if i["name"] == "Tea")
    spice, extras, leave_out = tea["choice_groups"]
    assert (spice["label"], spice["kind"], spice["min_select"], spice["max_select"]) == (
        "Spice",
        "pick",
        1,
        1,
    )
    milk = next(c for c in extras["choices"] if c["label"] == "Extra milk")
    assert milk["price_delta"] == "50.00"
    assert milk["allergen_status"] == "contains"
    assert milk["matched_allergens"] == ["milk"]
    assert "cost_delta" not in milk
    mild = next(c for c in spice["choices"] if c["label"] == "Mild")
    assert mild["allergen_status"] == "no_declared_match"
    honey = next(c for c in extras["choices"] if c["label"] == "Honey")
    assert honey["allergen_status"] == "unverified"
    assert leave_out["choices"][0]["price_delta"] == "0.00"


async def test_menu_marks_a_dish_sold_out_when_a_required_group_is(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    s.mild.available = False
    s.hot.available = False
    await db_session.flush()
    menu = (await client.get("/api/guest/menu")).json()
    assert next(i for i in menu["items"] if i["name"] == "Tea")["available"] is False
