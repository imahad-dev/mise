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


async def test_uk_settle_with_service(client, db_session, uk):
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


async def _counter_order(client, db, r, dish):
    counter = DiningTable(
        restaurant_id=r.id, label="Counter", kind="counter", qr_token=uuid.uuid4().hex
    )
    db.add(counter)
    await db.flush()
    s = GuestSession(
        restaurant_id=r.id,
        table_id=counter.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    guest(client, s)
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(dish.id), "quantity": 1}],
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


async def test_uk_counter_bill_has_no_service_charge(client, db_session, uk):
    r, _, dish, _, _ = uk
    bill_id = await bill_id_of(db_session, await _counter_order(client, db_session, r, dish))
    await as_member(client, db_session, r.id, "staff")
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{bill_id}")).json()
    assert (d["service_charge_rate"], d["service_charge_amount"]) == ("0.0000", "0.00")
    resp = await settle(client, r.slug, bill_id, "card", service_included=True)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["total"], resp.json()["service_charge_amount"]) == ("12.00", "0.00")
    b = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    await db_session.refresh(b)
    assert (b.service_charge_amount, b.total) == (Decimal("0.00"), Decimal("12.00"))


async def test_pakistan_venue_ignores_a_service_charge_rate(client, db_session):
    r, _, dish, _, s = await _venue(db_session, "PB", "PKR", "Asia/Karachi", service="0.10")
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{bill_id}")).json()
    assert d["service_charge_amount"] == "0.00"
    cash = next(m for m in d["methods"] if m["method"] == "cash")
    resp = await settle(client, r.slug, bill_id, "cash", service_included=True)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["total"], resp.json()["service_charge_amount"]) == (cash["total"], "0.00")


async def test_service_rate_change_before_settle_is_bill_changed(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{bill_id}")).json()
    assert d["service_charge_amount"] == "1.50"
    r.service_charge_rate = Decimal("0.10")
    await db_session.flush()
    resp = await client.post(
        f"/api/restaurants/{r.slug}/bills/{bill_id}/settle",
        json={
            "payment_method": "card",
            "expected_method": "card",
            "expected_total": "13.50",
            "service_included": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "Bill changed"
    fresh = resp.json()["bill"]
    assert (fresh["service_charge_rate"], fresh["service_charge_amount"]) == ("0.1000", "1.20")


async def test_settled_bill_keeps_its_service_snapshot(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await settle(client, r.slug, bill_id, "card", service_included=True)
    assert resp.status_code == 200, resp.text
    r.service_charge_rate = Decimal("0.05")
    await db_session.flush()
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{bill_id}")).json()
    assert (d["service_charge_rate"], d["service_charge_amount"], d["total"]) == (
        "0.1250",
        "1.50",
        "13.50",
    )


async def test_void_after_a_uk_claim_names_pounds(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    assert (await client.post("/api/guest/bill/payment", json={"method": "card"})).is_success
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(f"/api/restaurants/{r.slug}/orders/{o}/void", json={"reason": "Left"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"].startswith("Guest says they paid by Card (GBP 12.00) — ")


async def test_cancel_after_a_uk_counter_claim_names_pounds(client, db_session, uk):
    r, _, dish, _, _ = uk
    bill_id = await bill_id_of(db_session, await _counter_order(client, db_session, r, dish))
    assert (await client.post("/api/guest/bill/payment", json={"method": "card"})).is_success
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(f"/api/restaurants/{r.slug}/bills/{bill_id}/cancel", json={})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"].startswith("Guest says they paid by Card (GBP 12.00) — ")


async def test_guest_sees_vat_and_optional_service(client, db_session, uk):
    _, _, dish, side, s = uk
    await _order(client, s, [(dish, 1), (side, 2)])
    guest(client, s)
    b = (await client.get("/api/guest/bill")).json()
    assert [m["method"] for m in b["methods"]] == ["cash", "card"]
    assert b["methods"][0]["tax_included"] is True
    assert (b["service_charge_rate"], b["service_charge_amount"]) == ("0.1250", "2.63")


async def _staff_due(client, db, r, order_id):
    await as_member(client, db, r.id, "staff")
    d = await client.get(f"/api/restaurants/{r.slug}/bills/{await bill_id_of(db, order_id)}")
    return d.json()


async def test_guest_claim_records_service_choice(client, db_session, uk):
    r, _, dish, _, s = uk
    o = await _order(client, s, [(dish, 1)])
    guest(client, s)
    on = await client.post(
        "/api/guest/bill/payment",
        json={"method": "card", "reference": None, "service_included": True},
    )
    assert on.status_code == 200, on.text
    assert on.json()["claim"]["total"] == "13.50"  # 12.00 + 12.5%
    assert on.json()["claim"]["service_included"] is True
    d = await _staff_due(client, db_session, r, o)
    assert (d["claim"]["service_included"], d["amount_due_after_claim"]) == (True, "0.00")
    guest(client, s)
    off = await client.post(
        "/api/guest/bill/payment",
        json={"method": "card", "reference": None, "service_included": False},
    )
    assert off.json()["claim"]["total"] == "12.00"
    assert off.json()["claim"]["service_included"] is False
    # Staff see the guest's latest choice and nothing still due.
    d = await _staff_due(client, db_session, r, o)
    assert d["claim"]["service_included"] is False
    assert d["amount_due_after_claim"] == "0.00"


async def test_due_rises_by_a_new_line_and_its_service(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1)])
    claim = {"method": "card", "service_included": True}
    assert (await client.post("/api/guest/bill/payment", json=claim)).is_success
    await _order(client, s, [(side, 1)])  # 4.50; service on 16.50 is 2.06 (was 1.50)
    d = await _staff_due(client, db_session, r, o)
    assert d["amount_due_after_claim"] == "5.06"


async def test_due_rises_by_the_new_line_without_service(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1)])
    claim = {"method": "card", "service_included": False}
    assert (await client.post("/api/guest/bill/payment", json=claim)).is_success
    await _order(client, s, [(side, 1)])
    d = await _staff_due(client, db_session, r, o)
    assert d["amount_due_after_claim"] == "4.50"


async def test_service_asked_where_none_applies_is_not_recorded(client, db_session, dubai):
    _, _, dish, _, s = dubai
    o = await _order(client, s, [(dish, 1)])
    claim = {"method": "card", "service_included": True}
    resp = await client.post("/api/guest/bill/payment", json=claim)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["claim"]["total"], resp.json()["claim"]["service_included"]) == (
        "12.00",
        False,
    )
    b = await db_session.execute(select(Bill).where(Bill.id == await bill_id_of(db_session, o)))
    b = b.scalar_one()
    await db_session.refresh(b)
    claimed_at = b.claimed_at
    # The same request again is no change (the stored claim is not rewritten).
    assert (await client.post("/api/guest/bill/payment", json=claim)).is_success
    await db_session.refresh(b)
    assert b.claimed_at == claimed_at


async def test_guest_cannot_claim_raast_in_the_uk(client, db_session, uk):
    _, _, dish, _, s = uk
    await _order(client, s, [(dish, 1)])
    guest(client, s)
    resp = await client.post("/api/guest/bill/payment", json={"method": "raast", "reference": "R1"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Payment method not accepted here"


async def test_menu_shows_the_service_rate(client, db_session, uk, dubai):
    for (*_rest, s), rate in ((uk, "0.1250"), (dubai, "0.0000")):
        guest(client, s)
        menu = (await client.get("/api/guest/menu")).json()
        assert menu["restaurant"]["service_charge_rate"] == rate
