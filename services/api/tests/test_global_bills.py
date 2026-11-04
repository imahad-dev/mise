"""UK and Dubai bills: VAT inside the menu price, venue methods only, optional service charge."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest_asyncio
from sqlalchemy import select, update
from tests.helpers import approve_order, as_member, seat_table, settle
from tests.test_bills import _item, bill_id_of, guest
from tests.test_counter import _backdate
from tests.test_floor_api import record_events

from src.config import settings
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services import analytics
from src.services.brief import current_prices, local_today
from src.services.order_snapshot import snapshot_order_item
from src.services.simulator import SimAssumptions, persist_simulation


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


async def _claim_audits(db, r):
    rows = await db.scalars(
        select(AuditLog.payload)
        .where(AuditLog.restaurant_id == r.id, AuditLog.event_type == "payment_claimed")
        .order_by(AuditLog.created_at)
    )
    return list(rows.all())


async def test_repeat_claim_after_a_new_order_refreshes_the_total(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1)])
    claim = {"method": "card", "service_included": True}
    assert (await client.post("/api/guest/bill/payment", json=claim)).json()["claim"][
        "total"
    ] == "13.50"
    await _order(client, s, [(side, 1)])  # 16.50 + 2.06 service
    resp = await client.post("/api/guest/bill/payment", json=claim)
    assert resp.status_code == 200, resp.text
    assert resp.json()["claim"]["total"] == "18.56"
    d = await _staff_due(client, db_session, r, o)
    assert d["amount_due_after_claim"] == "0.00"
    assert [a["total"] for a in await _claim_audits(db_session, r)] == ["13.50", "18.56"]


async def test_identical_repeat_claim_adds_no_audit_row(client, db_session, uk, monkeypatch):
    r, _, dish, _, s = uk
    await _order(client, s, [(dish, 1)])
    claim = {"method": "card", "service_included": True}
    assert (await client.post("/api/guest/bill/payment", json=claim)).is_success
    events = record_events(monkeypatch, "src.routers.guest.publish_event")
    assert (await client.post("/api/guest/bill/payment", json=claim)).is_success
    assert events == []
    audits = await _claim_audits(db_session, r)
    assert audits == [
        {
            "bill_id": audits[0]["bill_id"],
            "method": "card",
            "reference_last4": None,
            "service_included": True,
            "total": "13.50",
        }
    ]


async def test_uk_counter_claim_never_carries_service(client, db_session, uk):
    r, _, dish, _, _ = uk
    bill_id = await bill_id_of(db_session, await _counter_order(client, db_session, r, dish))
    resp = await client.post(
        "/api/guest/bill/payment", json={"method": "card", "service_included": True}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["claim"]["total"], resp.json()["claim"]["service_included"]) == (
        "12.00",
        False,
    )
    b = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    await db_session.refresh(b)
    assert (b.claimed_service_included, b.claimed_total) == (False, Decimal("12.00"))


async def test_pakistan_claim_never_carries_service(client, db_session):
    _, _, dish, _, s = await _venue(db_session, "PB", "PKR", "Asia/Karachi", service="0.10")
    o = await _order(client, s, [(dish, 1)])
    guest(client, s)
    bill = (await client.get("/api/guest/bill")).json()
    cash = next(m["total"] for m in bill["methods"] if m["method"] == "cash")
    resp = await client.post(
        "/api/guest/bill/payment", json={"method": "cash", "service_included": True}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["claim"]["total"], resp.json()["claim"]["service_included"]) == (
        cash,
        False,
    )
    b = await db_session.execute(select(Bill).where(Bill.id == await bill_id_of(db_session, o)))
    b = b.scalar_one()
    await db_session.refresh(b)
    assert b.claimed_service_included is False


async def test_refused_method_does_not_revive_an_expired_counter_bill(client, db_session, uk):
    r, _, dish, _, _ = uk
    o = await _counter_order(client, db_session, r, dish)
    bill_id = await bill_id_of(db_session, o)
    await _backdate(db_session, str(o), 31)
    await as_member(client, db_session, r.id, "staff")
    await client.get(f"/api/restaurants/{r.slug}/bills")  # a list read expires it
    b = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    await db_session.refresh(b)
    assert b.status == "cancelled"
    resp = await client.post("/api/guest/bill/payment", json={"method": "raast", "reference": "R1"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Payment method not accepted here"
    await db_session.refresh(b)
    assert (b.status, b.claimed_method) == ("cancelled", None)


async def test_guest_claim_with_service_settles_at_the_claimed_total(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1), (side, 2)])
    claim = (
        await client.post(
            "/api/guest/bill/payment", json={"method": "card", "service_included": True}
        )
    ).json()["claim"]
    assert claim["total"] == "23.63"
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(
        f"/api/restaurants/{r.slug}/bills/{await bill_id_of(db_session, o)}/settle",
        json={
            "payment_method": "card",
            "expected_method": "card",
            "expected_total": claim["total"],
            "service_included": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["total"], resp.json()["service_charge_amount"]) == ("23.63", "2.63")
    [audit] = await _claim_audits(db_session, r)
    assert (audit["service_included"], audit["total"]) == (True, "23.63")


async def test_settings_service_charge(client, db_session, uk, dubai):
    r, *_ = uk
    await as_member(client, db_session, r.id, "owner")
    s = (await client.get(f"/api/restaurants/{r.slug}/settings")).json()
    assert s["tax_rule"] == {"name": "United Kingdom", "rate": "0.20", "pricing": "included"}
    assert (s["service_charge_allowed"], s["service_charge_rate"]) == (True, "0.1250")
    url = f"/api/restaurants/{r.slug}/settings"
    ok = await client.patch(url, json={"service_charge_rate": "0.10"})
    assert ok.status_code == 200 and ok.json()["service_charge_rate"] == "0.1000"
    assert (await client.patch(url, json={"service_charge_rate": "0.25"})).status_code == 422
    assert (await client.patch(url, json={"service_charge_rate": "-0.01"})).status_code == 422
    assert (await client.patch(url, json={"service_charge_rate": "0.12345"})).status_code == 422

    d, *_ = dubai
    await as_member(client, db_session, d.id, "owner")
    durl = f"/api/restaurants/{d.slug}/settings"
    refused = await client.patch(durl, json={"service_charge_rate": "0.10"})
    assert refused.status_code == 422
    assert refused.json()["detail"] == "An optional service charge is not offered in Dubai, UAE"
    got = (await client.get(durl)).json()
    assert got["service_charge_allowed"] is False
    # Turning it off is always allowed.
    assert (await client.patch(durl, json={"service_charge_rate": "0"})).status_code == 200


async def test_settings_service_charge_persists_audits_and_normalises(client, db_session, uk):
    r, *_ = uk
    await as_member(client, db_session, r.id, "owner")
    url = f"/api/restaurants/{r.slug}/settings"

    async def edits():
        rows = await db_session.scalars(
            select(AuditLog).where(
                AuditLog.restaurant_id == r.id, AuditLog.event_type == "owner_service_charge_edit"
            )
        )
        return [x.payload for x in rows]

    assert (await client.patch(url, json={"service_charge_rate": "0.10"})).status_code == 200
    assert (await client.get(url)).json()["service_charge_rate"] == "0.1000"
    assert await edits() == [{"before": "0.1250", "after": "0.1000"}]
    assert (await client.patch(url, json={"service_charge_rate": "0.10"})).status_code == 200
    assert len(await edits()) == 1
    neg = await client.patch(url, json={"service_charge_rate": "-0"})
    assert (neg.status_code, neg.json()["service_charge_rate"]) == (200, "0.0000")


async def test_settings_pakistan_and_no_jurisdiction(client, db_session):
    pk, *_ = await _venue(db_session, "PB", "PKR", "Asia/Karachi")
    await as_member(client, db_session, pk.id, "owner")
    s = (await client.get(f"/api/restaurants/{pk.slug}/settings")).json()
    assert s["tax_rule"] == {"name": "Punjab, Pakistan", "rate": "0.16", "pricing": "on_top"}
    assert s["service_charge_allowed"] is False

    none, *_ = await _venue(db_session, None, "PKR", "Asia/Karachi")
    await as_member(client, db_session, none.id, "owner")
    resp = await client.patch(
        f"/api/restaurants/{none.slug}/settings", json={"service_charge_rate": "0.10"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "An optional service charge is not offered at this venue"


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


async def test_uk_brief_excludes_vat_and_reports_service_apart(client, db_session, uk):
    r, _, dish, side, s = uk
    o = await _order(client, s, [(dish, 1), (side, 2)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    assert (await settle(client, r.slug, bill_id, "card", service_included=True)).status_code == 200
    # The brief window ends yesterday: move the sale there.
    yesterday = datetime.now(UTC) - timedelta(days=1)
    await db_session.execute(update(Order).where(Order.id == o).values(placed_at=yesterday))
    await db_session.execute(update(Bill).where(Bill.id == bill_id).values(settled_at=yesterday))
    await db_session.commit()
    await as_member(client, db_session, r.id, "owner")
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{r.slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert (b["kpis"]["revenue"], b["kpis"]["contribution_margin"]) == (17.5, 14.5)
    assert {m["name"]: m["revenue"] for m in b["menu_engineering"]} == {"Pie": 10.0, "Chips": 7.5}
    assert b["peak_hours"][0]["avg_revenue_per_day"] == 0.62  # 17.50 over 28 days
    assert b["service_charge_collected"] == "2.63"
    assert (b["prices_include_tax"], b["tax_split_by_method"]) == (True, False)
    # One VAT rate for every method: the payment mix says nothing worth narrating.
    assert "Digital payments" not in b["summary"]
    assert "revenue GBP 17.5 (excl. VAT), average order GBP 17.5 (excl. VAT)" in b["summary"]
    assert "contribution margin GBP 14.5 (excl. VAT;" in b["summary"]
    assert "2.63" not in b["summary"]


async def test_uk_what_if_prices_exclude_vat(db_session, uk):
    r, _, dish, side, _ = uk
    prices = await current_prices(db_session, r)
    assert prices[str(dish.id)] == (10.0, 1.0)  # 12.00 / 1.20
    assert prices[str(side.id)] == (3.75, 1.0)  # 4.50 / 1.20


async def test_pakistan_prices_and_brief_flags_unchanged(client, db_session):
    pk, _, dish, *_ = await _venue(db_session, "PB", "PKR", "Asia/Karachi")
    assert (await current_prices(db_session, pk))[str(dish.id)] == (12.0, 1.0)
    await as_member(client, db_session, pk.id, "owner")
    with patch.object(settings, "demo_mode", False):
        b = (await client.get(f"/api/restaurants/{pk.slug}/ai/brief")).json()
    assert (b["prices_include_tax"], b["tax_split_by_method"]) == (False, True)
    assert b["service_charge_collected"] == "0.00"


async def _settled_gb_bill(db, r, s, item, n):
    """One live GB bill settled yesterday for one line of `item`, VAT as charge_for stamps it."""
    at = datetime.now(UTC) - timedelta(days=1)
    bill = Bill(
        restaurant_id=r.id,
        bill_no=n,
        status="settled",
        source="live",
        payment_method="card",
        subtotal=item.price,
        tax_jurisdiction="GB",
        tax_rate=Decimal("0.20"),
        tax_pricing="included",
        tax_amount=Decimal("2.03"),
        total=item.price,
        opened_at=at - timedelta(hours=1),
        settled_at=at,
    )
    db.add(bill)
    await db.flush()
    line = snapshot_order_item(item, 1, None, "en", "en", [])
    db.add(
        Order(
            guest_session_id=s.id,
            restaurant_id=r.id,
            status="bumped",
            total=item.price,
            bill_id=bill.id,
            idempotency_key=uuid.uuid4().hex,
            payload_hash="x",
            placed_at=at,
            bumped_at=at,
            items=[line],
        )
    )
    await db.flush()


async def test_uk_revenue_matches_the_vat_each_bill_recorded(db_session, uk):
    r, _, _, _, s = uk
    item = _item(r.id, "Soup", "12.15", 3)
    db_session.add(item)
    await db_session.flush()
    for n in (1, 2):
        await _settled_gb_bill(db_session, r, s, item, n)  # VAT 2.025 rounds to 2.03
    today = local_today(r)
    w = analytics.Window(r.id, r.timezone, today - timedelta(days=2), today + timedelta(days=1))
    # 2 x (12.15 - 2.03); dividing by the 1.20 rate would give 20.25.
    assert (await analytics.kpis(db_session, w))["revenue"] == 20.24


async def test_simulated_uk_revenue_is_billed_net(db_session, uk):
    r, *_ = uk
    db_session.add_all([_item(r.id, "Soup", "12.15", 3), _item(r.id, "Tea", "2.35", 4)])
    await db_session.flush()
    await persist_simulation(db_session, r, SimAssumptions(days=14))
    today = local_today(r)
    w = analytics.Window(r.id, r.timezone, today - timedelta(days=15), today + timedelta(days=1))
    bills = (await db_session.scalars(select(Bill).where(Bill.restaurant_id == r.id))).all()
    assert bills and all(b.status == "settled" for b in bills)
    net = sum((b.subtotal - b.tax_amount for b in bills), Decimal(0))
    assert (await analytics.kpis(db_session, w))["revenue"] == float(net)
