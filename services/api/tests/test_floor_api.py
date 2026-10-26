"""Floor view API: tiles follow a table through seated, ordered, served, paying, clearing."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.routers.floor import _natural


@dataclass
class FloorVenue:
    r: Restaurant
    t1: DiningTable
    t2: DiningTable
    t3: DiningTable
    counter: DiningTable
    naan: MenuItem


def new_restaurant(name: str) -> Restaurant:
    return Restaurant(
        name=name,
        slug=f"floor-{uuid.uuid4().hex[:8]}",
        city="Lahore",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
        service_extra_label="More naan / roti",
    )


def new_table(restaurant_id: uuid.UUID, label: str, kind: str = "table") -> DiningTable:
    return DiningTable(
        restaurant_id=restaurant_id, label=label, qr_token=uuid.uuid4().hex, kind=kind
    )


@pytest_asyncio.fixture
async def fv(db_session: AsyncSession) -> FloorVenue:
    r = new_restaurant("Floor Venue")
    db_session.add(r)
    await db_session.flush()
    t1, t2, t3 = (new_table(r.id, label) for label in ("T1", "T2", "T3"))
    counter = new_table(r.id, "Counter", "counter")
    naan = MenuItem(
        restaurant_id=r.id,
        category="breads",
        price=Decimal("60.00"),
        unit_cost=Decimal("1.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
        sort_order=1,
    )
    naan.translations = [MenuTranslation(language="en", name="Naan")]
    db_session.add_all([t1, t2, t3, counter, naan])
    await db_session.flush()
    return FloorVenue(r, t1, t2, t3, counter, naan)


async def seat(
    db: AsyncSession, venue: FloorVenue, table: DiningTable, minutes_ago: int = 0
) -> GuestSession:
    session = GuestSession(
        restaurant_id=venue.r.id,
        table_id=table.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        created_at=func.now() - timedelta(minutes=minutes_ago),
    )
    db.add(session)
    await db.flush()
    return session


def guest(client: AsyncClient, session: GuestSession) -> None:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))


async def order(client: AsyncClient, session: GuestSession, item: MenuItem) -> uuid.UUID:
    guest(client, session)
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(item.id), "quantity": 1}],
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


def record_events(monkeypatch, *targets: str) -> list[dict]:
    events: list[dict] = []

    async def fake(channel: str, message: str) -> None:
        events.append(json.loads(message))

    for target in targets:
        monkeypatch.setattr(target, fake)
    return events


async def floor(client: AsyncClient, venue: FloorVenue) -> dict:
    resp = await client.get(f"/api/restaurants/{venue.r.slug}/floor")
    assert resp.status_code == 200, resp.text
    return resp.json()


def tile(data: dict, label: str) -> dict:
    return next(t for t in data["tiles"] if t["label"] == label)


def test_natural_label_order():
    assert sorted(["T10", "T2", "F1", "T1"], key=_natural) == ["F1", "T1", "T2", "T10"]


async def test_floor_follows_a_table(client, db_session, fv, monkeypatch):
    events = record_events(monkeypatch, "src.routers.floor.publish_event")
    await as_member(client, db_session, fv.r.id, "staff")

    d = await floor(client, fv)
    assert [t["label"] for t in d["tiles"]] == ["T1", "T2", "T3"]
    assert {t["state"] for t in d["tiles"]} == {"free"}
    assert d["counts"] == {"red": 0, "amber": 0}
    assert d["server_time"]
    assert d["thresholds"]["seated"] == [180, 300]
    assert d["service_extra_label"] == "More naan / roti"

    s1 = await seat(db_session, fv, fv.t1, minutes_ago=6)
    await seat(db_session, fv, fv.t3)
    d = await floor(client, fv)
    assert d["tiles"][0]["label"] == "T1"
    assert (d["tiles"][0]["state"], d["tiles"][0]["level"]) == ("seated", "red")
    assert d["counts"] == {"red": 1, "amber": 0}
    assert (tile(d, "T3")["state"], tile(d, "T3")["level"]) == ("seated", "none")

    order_id = await order(client, s1, fv.naan)
    t1 = tile(await floor(client, fv), "T1")
    assert t1["state"] == "ordered"
    assert t1["running_total"] == "60.00"
    bill_id = t1["bill_id"]
    assert bill_id is not None

    bump = await client.post(f"/api/restaurants/{fv.r.slug}/kitchen/orders/{order_id}/bump")
    assert bump.status_code == 200, bump.text
    assert tile(await floor(client, fv), "T1")["state"] == "served"

    guest(client, s1)
    assert (await client.post("/api/guest/bill-request")).status_code == 200
    assert tile(await floor(client, fv), "T1")["state"] == "paying"

    settle = await client.post(
        f"/api/restaurants/{fv.r.slug}/bills/{bill_id}/settle", json={"payment_method": "cash"}
    )
    assert settle.status_code == 200, settle.text
    t1 = tile(await floor(client, fv), "T1")
    assert (t1["state"], t1["running_total"], t1["bill_id"]) == ("needs_clearing", None, None)

    cleared = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{fv.t1.id}/clear")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["table_id"] == str(fv.t1.id)
    assert tile(await floor(client, fv), "T1")["state"] == "free"
    assert events == [{"event": "table_cleared", "table_id": str(fv.t1.id)}]


async def test_clear_refuses_open_bill_and_other_venues(client, db_session, fv):
    s2 = await seat(db_session, fv, fv.t2)
    await order(client, s2, fv.naan)
    other = new_restaurant("Other Venue")
    db_session.add(other)
    await db_session.flush()
    foreign = new_table(other.id, "T1")
    db_session.add(foreign)
    await db_session.flush()
    await as_member(client, db_session, fv.r.id, "owner")

    resp = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{fv.t2.id}/clear")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Settle the bill first"
    assert (
        await db_session.scalar(
            select(Bill.status)
            .join(Order, Order.bill_id == Bill.id)
            .where(Order.table_id == fv.t2.id)
        )
        == "open"
    )

    resp = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{foreign.id}/clear")
    assert resp.status_code == 404
    resp = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{uuid.uuid4()}/clear")
    assert resp.status_code == 404
