"""Guest bill with per-method totals, and payment claims from the table."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import approve_order, as_member, seat_table, settle
from tests.test_bills import Venue, _item, bill_id_of, guest, place

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.bills import VISIT_ENDED, session_is_current

SAMPLE = {"sample": True, "raast_id": "0000 SAMPLE", "account_title": "Sample account"}
PAY = "/api/guest/bill/payment"


async def _venue(db: AsyncSession, name: str) -> Venue:
    r = Restaurant(
        name=name,
        slug=f"pay-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
        payment_details=SAMPLE,
    )
    db.add(r)
    await db.flush()
    t1 = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    t2 = DiningTable(restaurant_id=r.id, label="T2", qr_token=uuid.uuid4().hex)
    karahi = _item(r.id, "Chicken Karahi", "1100.00", 1)
    naan = _item(r.id, "Naan", "60.00", 2)
    db.add_all([t1, t2, karahi, naan])
    await db.flush()
    half = MenuItemOption(
        menu_item_id=karahi.id, label="Half", price=Decimal("1100.00"), unit_cost=Decimal("1")
    )
    full = MenuItemOption(
        menu_item_id=karahi.id,
        label="Full",
        price=Decimal("2100.00"),
        unit_cost=Decimal("1"),
        sort_order=1,
    )
    expires = datetime.now(UTC) + timedelta(hours=2)
    s1 = GuestSession(restaurant_id=r.id, table_id=t1.id, language="en", expires_at=expires)
    s2 = GuestSession(restaurant_id=r.id, table_id=t2.id, language="en", expires_at=expires)
    db.add_all([half, full, s1, s2])
    await db.flush()
    return Venue(r, t1, t2, karahi, naan, half, full, s1, s2)


@pytest_asyncio.fixture
async def pv(db_session: AsyncSession) -> Venue:
    return await _venue(db_session, "Pay Venue")


async def order_2340(client: AsyncClient, v: Venue) -> uuid.UUID:
    """Full karahi 2100 + 4 naan 240 on table 1."""
    return await place(client, v.session_t1, [(v.karahi, 1, v.full), (v.naan, 4)])


async def test_bill_shows_lines_and_per_method_totals(client, pv):
    await order_2340(client, pv)
    guest(client, pv.session_t1)
    resp = await client.get("/api/guest/bill")
    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert b["status"] == "open"
    assert b["bill_no"] is not None
    assert b["bill_requested_at"] is None
    assert [(ln["name"], ln["quantity"]) for ln in b["lines"]] == [
        ("Chicken Karahi", 1),
        ("Naan", 4),
    ]
    assert b["subtotal"] == "2340.00"
    assert b["currency"] == "PKR"
    assert {
        m["method"]: (Decimal(m["tax_rate"]), m["tax_amount"], m["total"]) for m in b["methods"]
    } == {
        "cash": (Decimal("0.16"), "374.00", "2714.00"),
        "bank_transfer": (Decimal("0.16"), "374.00", "2714.00"),
        "card": (Decimal("0.08"), "187.00", "2527.00"),
        "wallet": (Decimal("0.08"), "187.00", "2527.00"),
        "raast": (Decimal("0.08"), "187.00", "2527.00"),
    }
    assert [m["label"] for m in b["methods"]] == [
        "Cash",
        "Card",
        "JazzCash / Easypaisa",
        "Raast QR",
        "Bank transfer",
    ]
    assert {m["method"]: m["payment_class"] for m in b["methods"]}["raast"] == "digital"
    assert b["payment_details"]["sample"] is True
    assert b["payment_details"]["raast_id"] == "0000 SAMPLE"
    assert b["claim"] is None
    assert (b["payment_method"], b["tax_rate"], b["total"]) == (None, None, None)
    assert b["voided"] == []
    assert b["order_status"] == "placed"


async def test_claim_is_idempotent_and_latest_wins(client, db_session, pv):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    guest(client, pv.session_t1)
    first = await client.post(PAY, json={"method": "raast", "reference": "TX123"})
    assert first.status_code == 200, first.text
    c = first.json()["claim"]
    assert (c["method"], c["reference"], c["total"]) == ("raast", "TX123", "2527.00")
    assert first.json()["bill_requested_at"] is not None

    repeat = await client.post(PAY, json={"method": "raast", "reference": "TX123"})
    assert repeat.status_code == 200
    assert repeat.json()["claim"]["claimed_at"] == c["claimed_at"]
    assert repeat.json()["bill_requested_at"] == first.json()["bill_requested_at"]

    switched = await client.post(PAY, json={"method": "cash", "reference": "ignored"})
    assert switched.status_code == 200, switched.text
    s = switched.json()["claim"]
    assert (s["method"], s["reference"], s["total"]) == ("cash", None, "2714.00")
    assert switched.json()["bill_requested_at"] == first.json()["bill_requested_at"]

    bill = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    assert (bill.status, bill.claimed_method, bill.claimed_total) == (
        "open",
        "cash",
        Decimal("2714.00"),
    )
    audits = (
        (
            await db_session.execute(
                select(AuditLog.payload)
                .where(AuditLog.restaurant_id == pv.r.id, AuditLog.event_type == "payment_claimed")
                .order_by(AuditLog.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [(a["method"], a["reference_last4"]) for a in audits] == [
        ("raast", "X123"),
        ("cash", None),
    ]
    assert "TX123" not in json.dumps(audits)


@pytest.mark.parametrize(
    "body",
    [
        {"method": "wallet"},
        {"method": "bank_transfer", "reference": "   "},
        {"method": "raast", "reference": "TX\n123"},
        {"method": "raast", "reference": "TX123\n"},
        {"method": "raast", "reference": "A" * 65},
        {"method": "wallet", "reference": "١٢٣"},  # Arabic-Indic digits
        {"method": "raast", "reference": "<script>x</script>"},
        {"method": "crypto", "reference": "TX1"},
    ],
)
async def test_invalid_claims_are_422(client, db_session, pv, body):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json=body)).status_code == 422
    bill = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    assert bill.claimed_method is None


async def test_reference_allows_its_characters(client, pv):
    await order_2340(client, pv)
    guest(client, pv.session_t1)
    ref = "Ab9 _-./#" + "x" * 55
    resp = await client.post(PAY, json={"method": "bank_transfer", "reference": ref})
    assert resp.status_code == 200, resp.text
    assert resp.json()["claim"]["reference"] == ref


async def test_no_bill_is_404_and_settled_bill_is_409(client, db_session, pv):
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "cash"})).status_code == 404
    assert (await client.get("/api/guest/bill")).status_code == 404

    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    settled = await settle(client, pv.r.slug, bill_id)
    assert settled.status_code == 200, settled.text
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "cash"})).status_code == 409
    after = (await client.get("/api/guest/bill")).json()
    assert (after["status"], after["subtotal"], after["methods"]) == ("settled", "2340.00", [])
    # What was paid, from the settled snapshot (cash at 16%).
    paid = (after["payment_method"], after["tax_rate"], after["total"])
    assert paid == ("cash", "0.1600", "2714.00")


async def test_other_table_and_other_venue_are_isolated(client, db_session, pv):
    await order_2340(client, pv)
    await place(client, pv.session_t2, [(pv.naan, 1)])
    guest(client, pv.session_t2)
    t2 = (await client.get("/api/guest/bill")).json()
    assert t2["subtotal"] == "60.00"
    claimed = await client.post(PAY, json={"method": "card"})
    assert claimed.json()["claim"]["total"] == "65.00"  # 60 + 8% = 4.8 -> 5

    other = await _venue(db_session, "Other Pay Venue")
    guest(client, other.session_t1)
    assert (await client.get("/api/guest/bill")).status_code == 404
    assert (await client.post(PAY, json={"method": "cash"})).status_code == 404

    guest(client, pv.session_t1)
    t1 = (await client.get("/api/guest/bill")).json()
    assert (t1["subtotal"], t1["claim"]) == ("2340.00", None)


async def test_brief_facts_never_contain_a_claimed_reference(client, db_session, pv, monkeypatch):
    import src.services.brief as brief

    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    guest(client, pv.session_t1)
    ref = "SECRETREF9876"
    assert (await client.post(PAY, json={"method": "raast", "reference": ref})).status_code == 200
    await as_member(client, db_session, pv.r.id, "staff")
    settled = await settle(client, pv.r.slug, bill_id, "raast")
    assert settled.status_code == 200, settled.text
    # Yesterday, so the bill falls inside the brief window (which ends before today).
    day = timedelta(days=1)
    await db_session.execute(
        update(Bill)
        .where(Bill.id == bill_id)
        .values(
            opened_at=Bill.opened_at - day,
            claimed_at=Bill.claimed_at - day,
            settled_at=Bill.settled_at - day,
        )
    )
    await db_session.execute(
        update(Order).where(Order.bill_id == bill_id).values(placed_at=Order.placed_at - day)
    )
    await db_session.flush()

    seen: list = []

    async def capture(inference, db, facts, template, task):
        seen.append(facts)
        return template, "template"

    monkeypatch.setattr(brief, "narrate", capture)
    result = await brief.compute_brief(db_session, pv.r, None)
    assert seen
    assert sum(seen[0]["payment_mix"]["bills"].values()) >= 1
    dumped = json.dumps([seen, result], default=str)
    assert ref not in dumped
    assert "9876" not in dumped
    assert "0000 SAMPLE" not in dumped


# --- A visit ends when the table is settled or cleared ---


async def new_session(db: AsyncSession, v: Venue) -> GuestSession:
    """A phone scanning table 1 now (clock time: the test runs in one transaction)."""
    s = GuestSession(
        restaurant_id=v.r.id,
        table_id=v.t1.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        created_at=await db.scalar(select(func.clock_timestamp())),
    )
    db.add(s)
    await db.flush()
    return s


async def test_session_is_current_rule(client, db_session, pv):
    a = pv.session_t1
    assert await session_is_current(db_session, a)  # table never reset
    order_id = await order_2340(client, pv)
    bill_id = await bill_id_of(db_session, order_id)
    pv.t1.cleared_at = await db_session.scalar(select(func.clock_timestamp()))
    await db_session.flush()
    # Reset after the session began, but it has an active order on the open bill.
    assert await session_is_current(db_session, a)
    await db_session.execute(update(Order).where(Order.id == order_id).values(status="cancelled"))
    await db_session.flush()
    assert not await session_is_current(db_session, a)  # only a cancelled order left
    await db_session.execute(update(Order).where(Order.id == order_id).values(status="placed"))
    await db_session.execute(
        update(Bill)
        .where(Bill.id == bill_id)
        .values(
            status="settled",
            payment_method="cash",
            total=Decimal("2714.00"),
            settled_at=func.clock_timestamp(),
        )
    )
    await db_session.flush()
    assert not await session_is_current(db_session, a)  # its bill was settled
    assert await session_is_current(db_session, await new_session(db_session, pv))
    assert await session_is_current(db_session, pv.session_t2)  # other table untouched


async def test_stale_phone_cannot_touch_the_next_partys_bill(client, db_session, pv):
    a = pv.session_t1
    a_bill = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    base = f"/api/restaurants/{pv.r.slug}"
    assert (await settle(client, pv.r.slug, a_bill)).status_code == 200
    assert (await client.post(f"{base}/tables/{pv.t1.id}/clear")).status_code == 200

    b = await new_session(db_session, pv)
    b_bill = await bill_id_of(db_session, await place(client, b, [(pv.naan, 2)]))
    guest(client, b)
    b_claim = await client.post(PAY, json={"method": "raast", "reference": "B-1"})
    assert b_claim.status_code == 200, b_claim.text

    guest(client, a)
    seen = await client.get("/api/guest/bill")
    # A still sees its own paid bill, never B's.
    assert seen.status_code == 200
    assert (seen.json()["status"], seen.json()["subtotal"]) == ("settled", "2340.00")
    assert (await client.post(PAY, json={"method": "cash"})).status_code == 409
    assert (await client.post("/api/guest/bill-request")).status_code == 404
    order = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(pv.naan.id), "quantity": 1}],
        },
    )
    assert (order.status_code, order.json()["detail"]) == (409, VISIT_ENDED)
    call = await client.post("/api/guest/service-calls", json={"reason": "help"})
    assert (call.status_code, call.json()["detail"]) == (409, VISIT_ENDED)

    bill = (await db_session.execute(select(Bill).where(Bill.id == b_bill))).scalar_one()
    assert (bill.claimed_method, bill.claimed_reference, bill.status) == ("raast", "B-1", "open")
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Order).where(Order.bill_id == b_bill)
        )
        == 1
    )

    # B's family member scanned after the clear and has not ordered: sees and pays B's bill.
    c = await new_session(db_session, pv)
    guest(client, c)
    mine = (await client.get("/api/guest/bill")).json()
    assert (mine["subtotal"], mine["claim"]["reference"]) == ("120.00", "B-1")
    paid = await client.post(PAY, json={"method": "card"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["claim"]["total"] == "130.00"


async def test_session_with_order_on_open_bill_stays_current(client, db_session, pv):
    a = pv.session_t1
    await order_2340(client, pv)
    # A reset older than the open bill (e.g. a previous party's settle) does not end A's visit.
    pv.t1.cleared_at = await db_session.scalar(select(func.clock_timestamp()))
    await db_session.flush()
    guest(client, a)
    assert (await client.get("/api/guest/bill")).json()["status"] == "open"
    assert (await client.post(PAY, json={"method": "cash"})).status_code == 200
    await place(client, a, [(pv.naan, 1)])


# --- Concurrency: committed data, two parallel identical taps ---


@pytest.mark.timeout(60)
async def test_parallel_identical_claims():
    rid, tid, iid, sid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with async_session_factory() as s:
        s.add(
            Restaurant(
                id=rid,
                name="Parallel Claims",
                slug=f"pay-par-{uuid.uuid4().hex[:8]}",
                currency="PKR",
                timezone="Asia/Karachi",
                languages=["en"],
                default_language="en",
                tax_jurisdiction="PB",
            )
        )
        await s.flush()
        s.add(DiningTable(id=tid, restaurant_id=rid, label="P1", qr_token=uuid.uuid4().hex))
        s.add(
            MenuItem(
                id=iid,
                restaurant_id=rid,
                category="breads",
                price=Decimal("60.00"),
                unit_cost=Decimal("9.00"),
                allergen_verified=True,
            )
        )
        await s.flush()
        s.add(MenuTranslation(menu_item_id=iid, language="en", name="Naan"))
        s.add(
            GuestSession(
                id=sid,
                restaurant_id=rid,
                table_id=tid,
                language="en",
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            )
        )
        await s.commit()
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={GUEST_COOKIE_NAME: sign_value(str(sid))},
        ) as c:
            await seat_table(tid)
            placed = await c.post(
                "/api/orders",
                json={
                    "idempotency_key": uuid.uuid4().hex,
                    "items": [{"menu_item_id": str(iid), "quantity": 2}],
                    "acknowledge_allergen_risk": True,
                },
            )
            assert placed.status_code == 201, placed.text
            await approve_order(placed.json()["id"])
            body = {"method": "wallet", "reference": "JC-555"}
            a, b = await asyncio.gather(c.post(PAY, json=body), c.post(PAY, json=body))
        assert (a.status_code, b.status_code) == (200, 200), (a.text, b.text)
        assert a.json()["claim"]["claimed_at"] == b.json()["claim"]["claimed_at"]
        async with async_session_factory() as s:
            bills = list((await s.execute(select(Bill).where(Bill.restaurant_id == rid))).scalars())
            audits = (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.restaurant_id == rid, AuditLog.event_type == "payment_claimed"
                    )
                )
            ).all()
        assert len(bills) == 1
        assert (bills[0].claimed_method, bills[0].claimed_reference, bills[0].claimed_total) == (
            "wallet",
            "JC-555",
            Decimal("130.00"),  # 120 + 8% = 9.6 -> 10
        )
        assert len(audits) == 1
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override
        async with async_session_factory() as s:
            await s.execute(delete(AuditLog).where(AuditLog.restaurant_id == rid))
            await s.execute(delete(Order).where(Order.restaurant_id == rid))
            await s.execute(delete(Bill).where(Bill.restaurant_id == rid))
            await s.execute(delete(GuestSession).where(GuestSession.restaurant_id == rid))
            await s.execute(delete(MenuTranslation).where(MenuTranslation.menu_item_id == iid))
            await s.execute(delete(MenuItem).where(MenuItem.restaurant_id == rid))
            await s.execute(delete(DiningTable).where(DiningTable.restaurant_id == rid))
            await s.execute(delete(Restaurant).where(Restaurant.id == rid))
            await s.commit()
