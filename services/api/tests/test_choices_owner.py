"""Owners edit dish choices: the save rules, the limits and who may edit."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
import pytest_asyncio
from tests.helpers import as_member

from src.models.menu import MenuItem
from src.models.restaurant import Restaurant


@dataclass
class OwnerSetup:
    restaurant: Restaurant
    dish: MenuItem
    pay_forward: MenuItem


def _dish(restaurant_id, **extra) -> MenuItem:
    return MenuItem(
        restaurant_id=restaurant_id,
        category="drinks",
        price=Decimal("300.00"),
        unit_cost=Decimal("60.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
        sort_order=1,
        **extra,
    )


@pytest_asyncio.fixture
async def owner_setup(client, db_session):
    restaurant = Restaurant(
        name="Owner Venue",
        slug=f"own-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add(restaurant)
    await db_session.flush()
    dish = _dish(restaurant.id)
    pay_forward = _dish(restaurant.id, is_pay_forward=True)
    db_session.add_all([dish, pay_forward])
    await db_session.flush()
    await as_member(client, db_session, restaurant.id, "owner")
    return OwnerSetup(restaurant, dish, pay_forward)


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
    other = Restaurant(
        name="Other",
        slug=f"o-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
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
    onions = await client.post(url, json={"label": "Onions"})
    assert onions.status_code == 201
    body = onions.json()
    assert (body["allergen_verified"], body["is_vegetarian"], body["is_vegan"]) == (
        True,
        True,
        True,
    )


async def test_leave_out_stays_confirmed_when_patched_unverified(client, owner_setup):
    s = owner_setup
    base = f"/api/restaurants/{s.restaurant.slug}"
    group = (
        await client.post(
            groups_url(s),
            json={"label": "Leave out", "kind": "leave_out", "min_select": 0, "max_select": 3},
        )
    ).json()
    onions = (
        await client.post(f"{base}/choice-groups/{group['id']}/choices", json={"label": "Onions"})
    ).json()
    resp = await client.patch(f"{base}/choices/{onions['id']}", json={"allergen_verified": False})
    assert resp.status_code == 200
    assert resp.json()["allergen_verified"] is True


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


async def test_vegetarian_fish_is_refused(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}/choices"
    body = {"label": "Anchovy", "is_vegetarian": True, "allergens": ["fish"]}
    assert (await client.post(url, json=body)).status_code == 422


async def test_limits(client, owner_setup):
    s = owner_setup
    for n in range(8):
        body = {**SPICE, "label": f"G{n}"}
        assert (await client.post(groups_url(s), json=body)).status_code == 201
    assert (await client.post(groups_url(s), json={**SPICE, "label": "G9"})).status_code == 422


async def test_choice_limit(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json={**SPICE, "max_select": 2})).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}/choices"
    for n in range(20):
        assert (await client.post(url, json={"label": f"C{n}"})).status_code == 201
    assert (await client.post(url, json={"label": "C20"})).status_code == 422


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


async def test_group_kind_cannot_change(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}"
    resp = await client.patch(url, json={"kind": "leave_out"})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "pick"


async def test_delete_group(client, owner_setup):
    s = owner_setup
    group = (await client.post(groups_url(s), json=SPICE)).json()
    url = f"/api/restaurants/{s.restaurant.slug}/choice-groups/{group['id']}"
    assert (await client.delete(url)).status_code == 200
