"""Floor view API: tiles follow a table through seated, ordered, served, paying, clearing."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, settle

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.models.sitting import TableSitting
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
    # "²" is a digit to str.isdigit() but not a [0-9] run: it sorts, never crashes int().
    assert sorted(["T²", "T2", "T1"], key=_natural) == ["T1", "T2", "T²"]


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
    assert tile(d, "T1")["waiting_for_open"] is True

    # Guests order once staff open the table.
    opened = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{fv.t1.id}/sitting")
    assert opened.status_code == 201, opened.text
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

    settled = await settle(client, fv.r.slug, bill_id)
    assert settled.status_code == 200, settled.text
    t1 = tile(await floor(client, fv), "T1")
    assert (t1["state"], t1["running_total"], t1["bill_id"]) == ("needs_clearing", None, None)

    cleared = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{fv.t1.id}/clear")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["table_id"] == str(fv.t1.id)
    assert tile(await floor(client, fv), "T1")["state"] == "free"
    assert events == [
        {"event": "table_opened", "table_id": str(fv.t1.id)},
        {"event": "table_cleared", "table_id": str(fv.t1.id)},
    ]


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


async def test_cancelled_orders_do_not_drive_the_tile(client, db_session, fv):
    db_session.add(TableSitting(table_id=fv.t1.id))
    s1 = await seat(db_session, fv, fv.t1)
    cancelled = await order(client, s1, fv.naan)
    kept = await order(client, s1, fv.naan)
    await db_session.execute(
        update(Order)
        .where(Order.id == cancelled)
        .values(status="cancelled", placed_at=func.now() - timedelta(minutes=30))
    )
    await as_member(client, db_session, fv.r.id, "staff")
    t1 = tile(await floor(client, fv), "T1")
    assert (t1["state"], t1["level"], t1["running_total"]) == ("ordered", "none", "60.00")

    bump = await client.post(f"/api/restaurants/{fv.r.slug}/kitchen/orders/{kept}/bump")
    assert bump.status_code == 200, bump.text
    assert tile(await floor(client, fv), "T1")["state"] == "served"


async def test_simulated_bills_without_table_do_not_affect_tiles(client, db_session, fv):
    db_session.add_all(
        [
            Bill(
                restaurant_id=fv.r.id,
                table_id=None,
                source="simulated",
                status="settled",
                payment_method="cash",
                subtotal=Decimal("60.00"),
                total=Decimal("60.00"),
                settled_at=func.now(),
            ),
            Bill(restaurant_id=fv.r.id, table_id=None, source="simulated", status="open"),
        ]
    )
    await db_session.flush()
    await as_member(client, db_session, fv.r.id, "staff")
    d = await floor(client, fv)
    assert [(t["label"], t["state"]) for t in d["tiles"]] == [
        ("T1", "free"),
        ("T2", "free"),
        ("T3", "free"),
    ]


def sitting_url(venue: FloorVenue, table: DiningTable) -> str:
    return f"/api/restaurants/{venue.r.slug}/tables/{table.id}/sitting"


async def test_open_table_returns_a_code_only_when_required(client, db_session, fv, monkeypatch):
    events = record_events(monkeypatch, "src.routers.floor.publish_event")
    await as_member(client, db_session, fv.r.id, "staff")

    resp = await client.post(sitting_url(fv, fv.t1))
    assert resp.status_code == 201, resp.text
    assert resp.json()["code"] is None
    assert events == [{"event": "table_opened", "table_id": str(fv.t1.id)}]
    t1 = tile(await floor(client, fv), "T1")
    assert (t1["sitting_open"], t1["waiting_for_open"]) == (True, False)

    fv.r.sitting_code_required = True
    await db_session.flush()
    resp = await client.post(sitting_url(fv, fv.t2))
    assert resp.status_code == 201, resp.text
    code = resp.json()["code"]
    assert len(code) == 4 and code.isdigit()
    assert "code" not in tile(await floor(client, fv), "T2")


async def test_open_table_refuses_twice_counters_and_other_venues(client, db_session, fv):
    other = new_restaurant("Other Venue")
    db_session.add(other)
    await db_session.flush()
    foreign = new_table(other.id, "T1")
    db_session.add(foreign)
    await db_session.flush()
    await as_member(client, db_session, fv.r.id, "staff")

    assert (await client.post(sitting_url(fv, fv.t1))).status_code == 201
    resp = await client.post(sitting_url(fv, fv.t1))
    assert (resp.status_code, resp.json()["detail"]) == (409, "Table is already open")
    resp = await client.post(sitting_url(fv, fv.counter))
    assert (resp.status_code, resp.json()["detail"]) == (409, "Counter tables are not opened")
    assert (await client.post(sitting_url(fv, foreign))).status_code == 404
    assert (await client.delete(sitting_url(fv, foreign))).status_code == 404


async def test_close_table(client, db_session, fv, monkeypatch):
    events = record_events(monkeypatch, "src.routers.floor.publish_event")
    await as_member(client, db_session, fv.r.id, "staff")
    assert (await client.post(sitting_url(fv, fv.t1))).status_code == 201

    resp = await client.delete(sitting_url(fv, fv.t1))
    assert resp.status_code == 200, resp.text
    assert resp.json()["table_id"] == str(fv.t1.id)
    assert events[-1] == {"event": "table_closed", "table_id": str(fv.t1.id)}
    assert tile(await floor(client, fv), "T1")["sitting_open"] is False

    resp = await client.delete(sitting_url(fv, fv.t1))
    assert (resp.status_code, resp.json()["detail"]) == (409, "No sitting is open")


async def test_close_table_with_open_bill_is_refused(client, db_session, fv):
    await as_member(client, db_session, fv.r.id, "staff")
    assert (await client.post(sitting_url(fv, fv.t2))).status_code == 201
    s2 = await seat(db_session, fv, fv.t2)
    await order(client, s2, fv.naan)
    await as_member(client, db_session, fv.r.id, "staff")

    resp = await client.delete(sitting_url(fv, fv.t2))
    assert (resp.status_code, resp.json()["detail"]) == (409, "Settle the bill first")
    assert tile(await floor(client, fv), "T2")["sitting_open"] is True


async def test_floor_shows_waiting_guests_and_pending_approval(client, db_session, fv):
    s1 = await seat(db_session, fv, fv.t1)
    await as_member(client, db_session, fv.r.id, "staff")
    t1 = tile(await floor(client, fv), "T1")
    assert (t1["state"], t1["sitting_open"], t1["waiting_for_open"]) == ("seated", False, True)
    assert t1["pending_order_id"] is None

    opened = await client.post(sitting_url(fv, fv.t1))
    assert opened.status_code == 201
    guest(client, s1)
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(fv.naan.id), "quantity": 3}],
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 201, resp.text
    order_id = resp.json()["id"]
    await db_session.execute(
        # Spec: a pending_approval order is always the first order of its sitting.
        update(Order)
        .where(Order.id == uuid.UUID(order_id))
        .values(status="pending_approval", sitting_id=uuid.UUID(opened.json()["sitting_id"]))
    )
    await as_member(client, db_session, fv.r.id, "staff")
    t1 = tile(await floor(client, fv), "T1")
    assert t1["state"] == "approval_needed"
    assert (t1["sitting_open"], t1["waiting_for_open"]) == (True, False)
    assert t1["pending_order_id"] == order_id
    assert (t1["pending_order_total"], t1["pending_order_items"]) == ("180.00", 3)


async def test_open_table_race_answers_409_not_500(client, db_session, fv, monkeypatch):
    """Two simultaneous opens both pass get_open_sitting; the second insert hits the
    one-open-sitting-per-table unique index and must answer 409, not 500."""
    await as_member(client, db_session, fv.r.id, "staff")
    url = sitting_url(fv, fv.t1)
    db_session.add(TableSitting(table_id=fv.t1.id))
    await db_session.flush()

    async def none(db, table_id):
        return None

    monkeypatch.setattr("src.routers.floor.get_open_sitting", none)
    resp = await client.post(url)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Table is already open")


async def test_open_table_with_open_bill_is_refused(client, db_session, fv):
    await as_member(client, db_session, fv.r.id, "staff")
    db_session.add(Bill(restaurant_id=fv.r.id, table_id=fv.t1.id, bill_no=1))
    await db_session.flush()

    resp = await client.post(sitting_url(fv, fv.t1))
    assert (resp.status_code, resp.json()["detail"]) == (409, "Settle the bill first")


async def test_pending_order_of_a_closed_sitting_does_not_show_on_the_next_party(
    client, db_session, fv
):
    await as_member(client, db_session, fv.r.id, "staff")
    old = TableSitting(
        table_id=fv.t1.id,
        opened_at=func.now() - timedelta(hours=2),
        closed_at=func.now() - timedelta(hours=1),
        close_reason="staff_closed",
    )
    db_session.add(old)
    await db_session.flush()
    s1 = await seat(db_session, fv, fv.t1, minutes_ago=120)
    db_session.add(
        Order(
            guest_session_id=s1.id,
            restaurant_id=fv.r.id,
            table_id=fv.t1.id,
            sitting_id=old.id,
            status="pending_approval",
            total=Decimal("60.00"),
            idempotency_key=uuid.uuid4().hex,
            payload_hash=uuid.uuid4().hex,
        )
    )
    await db_session.flush()

    assert (await client.post(sitting_url(fv, fv.t1))).status_code == 201
    t1 = tile(await floor(client, fv), "T1")
    assert t1["pending_order_id"] is None
    assert t1["state"] != "approval_needed"
