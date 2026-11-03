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
        name=f"{jur} Venue",
        slug=f"g-{uuid.uuid4().hex[:8]}",
        currency=currency,
        timezone=tz,
        languages=["en"],
        default_language="en",
        tax_jurisdiction=jur,
        service_charge_rate=Decimal(service),
    )
    db.add(r)
    await db.flush()
    t = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    dish = _item(r.id, "Pie", "12.00", 1)
    side = _item(r.id, "Chips", "4.50", 2)
    db.add_all([t, dish, side])
    await db.flush()
    s = GuestSession(
        restaurant_id=r.id,
        table_id=t.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
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
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(i.id), "quantity": q} for i, q in lines],
            "acknowledge_allergen_risk": True,
        },
    )
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
        "included",
        Decimal("3.50"),
        Decimal("2.63"),
        Decimal("23.63"),
    )


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
    resp = await client.post(
        f"/api/restaurants/{r.slug}/bills/{bill_id}/settle",
        json={
            "payment_method": "card",
            "expected_method": "card",
            "expected_total": "12.00",
            "service_included": True,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Bill changed"


async def test_raast_refused_on_a_uk_bill(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(
        f"/api/restaurants/{r.slug}/bills/{bill_id}/settle",
        json={
            "payment_method": "raast",
            "expected_method": "raast",
            "expected_total": "12.00",
            "payment_reference": "R1",
        },
    )
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
