"""Settle safeguards: expected total, midnight rate change, reused references, voids,
device labels, the clear safeguard, and the money races between them."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, settle, sign_in
from tests.test_bills import (
    bill_id_of,
    committed_venue,  # noqa: F401 - fixture
    guest,
    place,
)
from tests.test_payment_claims import PAY, _venue, order_2340

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.bills import VISIT_ENDED, local_date, reference_key, session_is_current
from src.services.tax import tax_for


@pytest_asyncio.fixture
async def pv(db_session: AsyncSession):
    return await _venue(db_session, "Safeguard Venue")


def url(v, suffix: str) -> str:
    return f"/api/restaurants/{v.r.slug}{suffix}"


async def detail(client: AsyncClient, v, bill_id) -> dict:
    resp = await client.get(url(v, f"/bills/{bill_id}"))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def new_party(db: AsyncSession, v, table) -> GuestSession:
    s = GuestSession(
        restaurant_id=v.r.id,
        table_id=table.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        created_at=await db.scalar(select(func.clock_timestamp())),
    )
    db.add(s)
    await db.flush()
    return s


# --- Expected total and method ---


async def test_settle_requires_expectations(client, db_session, pv):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    staff = await as_member(client, db_session, pv.r.id, "staff")
    settle_url = url(pv, f"/bills/{bill_id}/settle")

    missing = await client.post(settle_url, json={"payment_method": "cash"})
    assert missing.status_code == 422
    other_method = await client.post(
        settle_url,
        json={"payment_method": "cash", "expected_method": "card", "expected_total": "2527.00"},
    )
    assert other_method.status_code == 422

    seen = await detail(client, pv, bill_id)
    assert seen["preview_standard"]["total"] == "2714.00"
    await place(client, pv.session_t1, [(pv.naan, 1)])  # a new order after staff looked
    stale = await client.post(
        settle_url,
        json={"payment_method": "cash", "expected_method": "cash", "expected_total": "2714.00"},
    )
    assert stale.status_code == 409, stale.text
    body = stale.json()
    assert body["detail"] == "Bill changed"
    assert (body["bill"]["status"], body["bill"]["subtotal"]) == ("open", "2400.00")
    assert body["bill"]["preview_standard"]["total"] == "2784.00"
    assert (await detail(client, pv, bill_id))["status"] == "open"

    ok = await client.post(
        settle_url,
        json={"payment_method": "cash", "expected_method": "cash", "expected_total": "2784.00"},
    )
    assert ok.status_code == 200, ok.text
    d = ok.json()
    assert (d["status"], d["total"], d["settled_by_name"]) == ("settled", "2784.00", "Test user")
    stored = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    assert stored.settled_by == staff.id
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.restaurant_id == pv.r.id, AuditLog.event_type == "bill_settled"
            )
        )
    ).scalar_one()
    assert audit.actor == f"user:{staff.id}"
    assert audit.payload["bill_id"] == str(bill_id)
    assert audit.payload["total"] == "2784.00"


async def test_claim_changed_after_staff_loaded_does_not_block(client, db_session, pv):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    cash_total = (await detail(client, pv, bill_id))["preview_standard"]["total"]
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "raast", "reference": "R9"})).status_code == 200
    resp = await client.post(
        url(pv, f"/bills/{bill_id}/settle"),
        json={"payment_method": "cash", "expected_method": "cash", "expected_total": cash_total},
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["payment_method"], resp.json()["total"]) == ("cash", "2714.00")


async def test_midnight_rate_change_refuses_the_old_total(client, db_session, pv, monkeypatch):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    today = {"d": date(2026, 6, 30)}

    def fake_local_date(restaurant, at):
        return today["d"]

    monkeypatch.setattr("src.services.bills.local_date", fake_local_date)
    monkeypatch.setattr("src.routers.bills.local_date", fake_local_date)

    before = (await detail(client, pv, bill_id))["preview_digital"]
    assert (before["tax_rate"], before["total"]) == ("0.05", "2457.00")  # 2340 + 117
    today["d"] = date(2026, 7, 1)
    body = {"payment_method": "card", "expected_method": "card", "expected_total": "2457.00"}
    stale = await client.post(url(pv, f"/bills/{bill_id}/settle"), json=body)
    assert stale.status_code == 409, stale.text
    fresh = stale.json()["bill"]["preview_digital"]
    assert (fresh["tax_rate"], fresh["total"]) == ("0.08", "2527.00")
    ok = await client.post(
        url(pv, f"/bills/{bill_id}/settle"), json={**body, "expected_total": fresh["total"]}
    )
    assert ok.status_code == 200, ok.text
    assert (Decimal(ok.json()["tax_rate"]), ok.json()["total"]) == (Decimal("0.08"), "2527.00")


# --- Claims: amount still due and reused references ---


async def test_amount_due_after_claim_follows_the_bill(client, db_session, pv):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "raast", "reference": "R1"})).status_code == 200
    await as_member(client, db_session, pv.r.id, "staff")
    d = await detail(client, pv, bill_id)
    assert (d["claim"]["method"], d["claim"]["total"]) == ("raast", "2527.00")
    assert d["amount_due_after_claim"] == "0.00"

    chai = await place(client, pv.session_t1, [(pv.naan, 1)])
    d = await detail(client, pv, bill_id)
    assert d["amount_due_after_claim"] == "65.00"  # 2400 + 8% = 2592; guest sent 2527

    void = await client.post(url(pv, f"/orders/{chai}/void"), json={"reason": "Not ordered"})
    assert void.status_code == 200, void.text
    assert void.json()["amount_due_after_claim"] == "0.00"


async def test_reused_reference_needs_acknowledgement(client, db_session, pv):
    a_bill = await bill_id_of(db_session, await order_2340(client, pv))
    b_bill = await bill_id_of(db_session, await place(client, pv.session_t2, [(pv.naan, 2)]))
    await as_member(client, db_session, pv.r.id, "staff")
    a = await settle(client, pv.r.slug, a_bill, "raast", payment_reference="TX1")
    assert a.status_code == 200, a.text
    a_no = a.json()["bill_no"]

    guest(client, pv.session_t2)
    assert (await client.post(PAY, json={"method": "raast", "reference": "tx1"})).status_code == 200
    d = await detail(client, pv, b_bill)
    assert d["reused_reference_bill_no"] == a_no

    refused = await settle(client, pv.r.slug, b_bill, "raast", payment_reference="TX1")
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"Reference already used on Bill {a_no:04d}"
    assert (await detail(client, pv, b_bill))["status"] == "open"
    ok = await settle(
        client,
        pv.r.slug,
        b_bill,
        "raast",
        payment_reference="TX1",
        acknowledge_reused_reference=True,
    )
    assert ok.status_code == 200, ok.text


async def test_reused_reference_only_same_venue_last_7_days(client, db_session, pv):
    a_bill = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    assert (await settle(client, pv.r.slug, a_bill, "raast", payment_reference="OLD1")).is_success
    await db_session.execute(
        update(Bill)
        .where(Bill.id == a_bill)
        .values(settled_at=func.clock_timestamp() - timedelta(days=8))
    )
    other = await _venue(db_session, "Other Venue")
    o_bill = await bill_id_of(db_session, await place(client, other.session_t1, [(other.naan, 1)]))
    await as_member(client, db_session, other.r.id, "staff")
    assert (
        await settle(client, other.r.slug, o_bill, "raast", payment_reference="NEW1")
    ).is_success

    b_party = await new_party(db_session, pv, pv.t2)
    b_bill = await bill_id_of(db_session, await place(client, b_party, [(pv.naan, 1)]))
    await as_member(client, db_session, pv.r.id, "staff")
    for ref in ("OLD1", "NEW1"):
        guest(client, b_party)
        assert (await client.post(PAY, json={"method": "raast", "reference": ref})).is_success
        assert (await detail(client, pv, b_bill))["reused_reference_bill_no"] is None
    assert (await settle(client, pv.r.slug, b_bill, "raast", payment_reference="OLD1")).is_success


# --- Voids ---


async def test_void_takes_an_order_off_the_bill(client, db_session, pv, monkeypatch):
    events: list[str] = []

    async def fake_publish(channel: str, message: str) -> None:
        events.append(message)

    monkeypatch.setattr("src.routers.bills.publish_event", fake_publish)
    keep = await order_2340(client, pv)
    wrong = await place(client, pv.session_t1, [(pv.naan, 2)])
    staff = await as_member(client, db_session, pv.r.id, "staff")
    void_url = url(pv, f"/orders/{wrong}/void")

    for reason in ("", "   ", "x" * 201):
        assert (await client.post(void_url, json={"reason": reason})).status_code == 422
    assert (await client.post(void_url, json={})).status_code == 422

    resp = await client.post(void_url, json={"reason": "  Wrong table  "})
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert (d["subtotal"], d["order_count"]) == ("2340.00", 1)
    voided = next(o for o in d["orders"] if o["order_id"] == str(wrong))
    assert (voided["voided"], voided["void_reason"], voided["status"]) == (
        True,
        "Wrong table",
        "cancelled",
    )
    stored = (await db_session.execute(select(Order).where(Order.id == wrong))).scalar_one()
    assert (stored.status, stored.voided_by, stored.void_reason) == (
        "cancelled",
        staff.id,
        "Wrong table",
    )
    assert stored.voided_at is not None
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.restaurant_id == pv.r.id, AuditLog.event_type == "order_voided"
            )
        )
    ).scalar_one()
    assert audit.actor == f"user:{staff.id}"
    assert audit.payload["order_id"] == str(wrong)
    assert any('"order_voided"' in e for e in events)

    kitchen = (await client.get(url(pv, "/kitchen/orders"))).json()["orders"]
    assert str(wrong) not in [o["id"] for o in kitchen]
    assert str(keep) in [o["id"] for o in kitchen]

    guest(client, pv.session_t1)
    g = (await client.get("/api/guest/bill")).json()
    assert g["voided"] == [{"name": "Naan", "option_label": None, "quantity": 2}]
    assert g["subtotal"] == "2340.00"

    await as_member(client, db_session, pv.r.id, "staff")
    assert (await client.post(void_url, json={"reason": "again"})).status_code == 409


async def test_void_refusals(client, db_session, pv):
    only = await order_2340(client, pv)
    bill_id = await bill_id_of(db_session, only)
    other = await _venue(db_session, "Other Venue")
    theirs = await place(client, other.session_t1, [(other.naan, 1)])
    await as_member(client, db_session, pv.r.id, "staff")
    assert (
        await client.post(url(pv, f"/orders/{theirs}/void"), json={"reason": "x"})
    ).status_code == 404
    assert (
        await client.post(url(pv, f"/orders/{uuid.uuid4()}/void"), json={"reason": "x"})
    ).status_code == 404

    # Voiding the last active order cancels the bill: nothing is left to settle.
    last = await client.post(url(pv, f"/orders/{only}/void"), json={"reason": "Walked out"})
    assert (last.status_code, last.json()["status"]) == (200, "cancelled")
    empty = await settle(client, pv.r.slug, bill_id)
    assert (empty.status_code, empty.json()["detail"]) == (409, "Bill is not open")

    second = await bill_id_of(db_session, await place(client, pv.session_t2, [(pv.naan, 1)]))
    assert (await settle(client, pv.r.slug, second)).status_code == 200
    settled_order = (
        await db_session.execute(select(Order.id).where(Order.bill_id == second))
    ).scalar_one()
    late = await client.post(url(pv, f"/orders/{settled_order}/void"), json={"reason": "x"})
    assert (late.status_code, late.json()["detail"]) == (409, "Bill is not open")


# --- Device labels ---


async def test_device_labels_and_joined_late(client, db_session, pv):
    s1 = pv.session_t1
    s2 = await new_party(db_session, pv, pv.t1)
    s3 = await new_party(db_session, pv, pv.t1)
    o1 = await place(client, s1, [(pv.naan, 1)])
    o2 = await place(client, s2, [(pv.naan, 1)])
    o3 = await place(client, s1, [(pv.naan, 1)])
    o4 = await place(client, s3, [(pv.naan, 1)])
    bill_id = await bill_id_of(db_session, o1)
    opened = await db_session.scalar(select(Bill.opened_at).where(Bill.id == bill_id))
    # One test transaction gives every order the same now(): set the real sequence.
    for oid, minutes in ((o1, 1), (o2, 4), (o3, 10), (o4, 25)):
        await db_session.execute(
            update(Order)
            .where(Order.id == oid)
            .values(placed_at=opened + timedelta(minutes=minutes))
        )
    await as_member(client, db_session, pv.r.id, "staff")
    d = await detail(client, pv, bill_id)
    assert [(o["order_id"], o["device_label"], o["joined_late"]) for o in d["orders"]] == [
        (str(o1), "Phone 1", False),
        (str(o2), "Phone 2", False),
        (str(o3), "Phone 1", False),
        (str(o4), "Phone 3", True),
    ]
    assert d["orders"][0]["lines"][0]["name"] == "Naan"
    # A void keeps everyone's number.
    assert (
        await client.post(url(pv, f"/orders/{o2}/void"), json={"reason": "Duplicate"})
    ).status_code == 200
    d = await detail(client, pv, bill_id)
    assert [o["device_label"] for o in d["orders"]] == ["Phone 1", "Phone 2", "Phone 1", "Phone 3"]


# --- Clear safeguard ---


async def test_clear_refuses_when_new_guests_are_seated(client, db_session, pv):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    assert (await settle(client, pv.r.slug, bill_id)).status_code == 200
    clear_url = url(pv, f"/tables/{pv.t1.id}/clear")

    await new_party(db_session, pv, pv.t1)  # scanned after the settle
    refused = await client.post(clear_url)
    assert (refused.status_code, refused.json()["detail"]) == (409, "New guests are already seated")
    assert (await client.post(clear_url, json={"force": False})).status_code == 409
    forced = await client.post(clear_url, json={"force": True})
    assert forced.status_code == 200, forced.text
    # Everyone seated before that clear: a second clear needs no force.
    assert (await client.post(clear_url)).status_code == 200
    audits = (
        await db_session.scalars(
            select(AuditLog.payload).where(
                AuditLog.restaurant_id == pv.r.id, AuditLog.event_type == "table_cleared"
            )
        )
    ).all()
    assert sorted(a["force"] for a in audits) == [False, True]


async def test_clear_ignores_expired_scans(client, db_session, pv):
    # T2's fixture session is the only scan; once it expires, clearing needs no force.
    await as_member(client, db_session, pv.r.id, "staff")
    clear_url = url(pv, f"/tables/{pv.t2.id}/clear")
    assert (await client.post(clear_url)).status_code == 409
    pv.session_t2.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()
    assert (await client.post(clear_url)).status_code == 200


# --- Concurrency: committed data, parallel clients ---


def _order_body(item_id) -> dict:
    return {
        "idempotency_key": uuid.uuid4().hex,
        "items": [{"menu_item_id": str(item_id), "quantity": 1}],
        "acknowledge_allergen_risk": True,
    }


async def _new_committed_party(restaurant_id, table_id) -> uuid.UUID:
    async with async_session_factory() as s:
        party = GuestSession(
            restaurant_id=restaurant_id,
            table_id=table_id,
            language="en",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        s.add(party)
        await s.commit()
        return party.id


async def _bill_of(order_id: str) -> uuid.UUID:
    async with async_session_factory() as s:
        return await s.scalar(select(Order.bill_id).where(Order.id == uuid.UUID(order_id)))


class _Clients:
    """Real database sessions per request (no test transaction), guest + staff clients."""

    def __init__(self, staff):
        self.staff_user = staff

    async def __aenter__(self):
        self.saved = app.dependency_overrides.pop(get_db, None)
        self.guest = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.staff = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        sign_in(self.staff, self.staff_user)
        return self

    async def __aexit__(self, *exc):
        await self.guest.aclose()
        await self.staff.aclose()
        if self.saved is not None:
            app.dependency_overrides[get_db] = self.saved


async def _table_of(session_id) -> uuid.UUID:
    async with async_session_factory() as s:
        return await s.scalar(select(GuestSession.table_id).where(GuestSession.id == session_id))


def _cash(subtotal: Decimal, on: date) -> Decimal:
    return subtotal + tax_for("PB", "cash", on, subtotal)[1]


@pytest.mark.timeout(120)
async def test_two_staff_settle_one_bill(committed_venue):  # noqa: F811 - the imported fixture
    restaurant_id, slug, item_id, session_id, staff = committed_venue
    table_id = await _table_of(session_id)
    async with _Clients(staff) as c:
        for _ in range(5):
            party = await _new_committed_party(restaurant_id, table_id)
            c.guest.cookies.set(GUEST_COOKIE_NAME, sign_value(str(party)))
            first = await c.guest.post("/api/orders", json=_order_body(item_id))
            assert first.status_code == 201, first.text
            bill_id = await _bill_of(first.json()["id"])
            body = {"payment_method": "cash", "expected_method": "cash", "expected_total": "70.00"}
            a, b = await asyncio.gather(
                c.staff.post(f"/api/restaurants/{slug}/bills/{bill_id}/settle", json=body),
                c.staff.post(f"/api/restaurants/{slug}/bills/{bill_id}/settle", json=body),
            )
            assert sorted([a.status_code, b.status_code]) == [200, 409], (a.text, b.text)
    async with async_session_factory() as s:
        audits = await s.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.restaurant_id == restaurant_id, AuditLog.event_type == "bill_settled")
        )
    assert audits == 5


ROUNDS = 20


@pytest.mark.timeout(240)
async def test_claim_order_settle_rounds(committed_venue):  # noqa: F811 - the imported fixture
    restaurant_id, slug, item_id, session_id, staff = committed_venue
    table_id = await _table_of(session_id)
    async with _Clients(staff) as c:
        for n in range(ROUNDS):
            party = await _new_committed_party(restaurant_id, table_id)
            c.guest.cookies.set(GUEST_COOKIE_NAME, sign_value(str(party)))
            first = await c.guest.post("/api/orders", json=_order_body(item_id))
            assert first.status_code == 201, first.text
            bill_id = await _bill_of(first.json()["id"])
            base = f"/api/restaurants/{slug}/bills/{bill_id}"
            seen = (await c.staff.get(base)).json()["preview_standard"]["total"]
            reqs = [
                c.guest.post(PAY, json={"method": "raast", "reference": f"R-{n}"}),
                c.guest.post("/api/orders", json=_order_body(item_id)),
                c.staff.post(
                    f"{base}/settle",
                    json={
                        "payment_method": "cash",
                        "expected_method": "cash",
                        "expected_total": seen,
                    },
                ),
            ]
            if n % 2:
                reqs.reverse()
            results = await asyncio.gather(*reqs)
            if n % 2:
                results.reverse()
            claim, racing, settled = results
            assert claim.status_code in (200, 409), claim.text
            assert racing.status_code in (201, 409), racing.text
            if racing.status_code == 409:
                assert racing.json()["detail"] == VISIT_ENDED
            if settled.status_code == 409:
                fresh = settled.json()["bill"]
                assert settled.json()["detail"] == "Bill changed"
                assert (fresh["status"], fresh["subtotal"]) == ("open", "120.00")
                settled = await c.staff.post(
                    f"{base}/settle",
                    json={
                        "payment_method": "cash",
                        "expected_method": "cash",
                        "expected_total": fresh["preview_standard"]["total"],
                    },
                )
            assert settled.status_code == 200, settled.text

    async with async_session_factory() as s:
        restaurant = await s.get(Restaurant, restaurant_id)
        bills = list(
            (await s.scalars(select(Bill).where(Bill.restaurant_id == restaurant_id))).all()
        )
        orders = list(
            (await s.scalars(select(Order).where(Order.restaurant_id == restaurant_id))).all()
        )
    assert len(bills) == ROUNDS
    for bill in bills:
        assert bill.status == "settled"
        mine = [o for o in orders if o.bill_id == bill.id]
        active = [o for o in mine if o.status != "cancelled"]
        assert bill.subtotal == sum(o.total for o in active)
        assert bill.total == _cash(bill.subtotal, local_date(restaurant, bill.settled_at))
        assert all(o.placed_at <= bill.settled_at for o in mine)
    assert all(o.bill_id is not None for o in orders)


async def _after(delay: float, request):
    await asyncio.sleep(delay)
    return await request


@pytest.mark.timeout(120)
async def test_void_racing_settle(committed_venue):  # noqa: F811 - the imported fixture
    restaurant_id, slug, item_id, session_id, staff = committed_venue
    table_id = await _table_of(session_id)
    outcomes = set()
    async with _Clients(staff) as c:
        for n in range(8):
            party = await _new_committed_party(restaurant_id, table_id)
            c.guest.cookies.set(GUEST_COOKIE_NAME, sign_value(str(party)))
            first = await c.guest.post("/api/orders", json=_order_body(item_id))
            second = await c.guest.post("/api/orders", json=_order_body(item_id))
            assert (first.status_code, second.status_code) == (201, 201)
            bill_id = await _bill_of(first.json()["id"])
            base = f"/api/restaurants/{slug}"
            body = {"payment_method": "cash", "expected_method": "cash", "expected_total": "139.00"}
            # Both requests in flight together; alternate which one starts 50 ms late so
            # both orders of arrival are exercised.
            void, settled = await asyncio.gather(
                _after(
                    0.05 * (n % 2),
                    c.staff.post(
                        f"{base}/orders/{second.json()['id']}/void", json={"reason": "Duplicate"}
                    ),
                ),
                _after(
                    0.05 * (1 - n % 2), c.staff.post(f"{base}/bills/{bill_id}/settle", json=body)
                ),
            )
            if void.status_code == 200:
                # Void first: the stale total is refused; the fresh one settles without it.
                assert settled.status_code == 409, settled.text
                assert settled.json()["bill"]["subtotal"] == "60.00"
                again = await c.staff.post(
                    f"{base}/bills/{bill_id}/settle", json={**body, "expected_total": "70.00"}
                )
                assert again.status_code == 200, again.text
                outcomes.add("voided")
            else:
                assert (void.status_code, void.json()["detail"]) == (409, "Bill is not open")
                assert settled.status_code == 200, settled.text
                outcomes.add("settled")

    async with async_session_factory() as s:
        bills = list(
            (await s.scalars(select(Bill).where(Bill.restaurant_id == restaurant_id))).all()
        )
        orders = list(
            (await s.scalars(select(Order).where(Order.restaurant_id == restaurant_id))).all()
        )
    assert outcomes == {"voided", "settled"}
    for bill in bills:
        mine = [o for o in orders if o.bill_id == bill.id]
        assert bill.status == "settled"
        assert bill.subtotal == sum(o.total for o in mine if o.voided_at is None)
        assert bill.subtotal == sum(o.total for o in mine if o.status != "cancelled")


# --- Review follow-ups: claimed references, reference keys, emptied bills, kitchen races ---


async def test_claimed_reference_is_checked_without_a_staff_reference(client, db_session, pv):
    a_bill = await bill_id_of(db_session, await order_2340(client, pv))
    b_bill = await bill_id_of(db_session, await place(client, pv.session_t2, [(pv.naan, 2)]))
    await as_member(client, db_session, pv.r.id, "staff")
    a = await settle(client, pv.r.slug, a_bill, "raast", payment_reference="TX_77")
    assert a.status_code == 200, a.text
    guest(client, pv.session_t2)
    assert (await client.post(PAY, json={"method": "raast", "reference": "tx 77"})).is_success
    refused = await settle(client, pv.r.slug, b_bill, "raast")  # staff type no reference
    assert refused.status_code == 409
    a_no = a.json()["bill_no"]
    assert refused.json()["detail"] == f"Reference already used on Bill {a_no:04d}"
    ok = await settle(client, pv.r.slug, b_bill, "raast", acknowledge_reused_reference=True)
    assert ok.status_code == 200, ok.text


def test_reference_key_is_one_normal_form():
    assert reference_key("TX 1") == reference_key("tx-1") == reference_key("t.x/1#") == "TX1"
    assert reference_key("TX_1") == "TX1"
    assert reference_key(None) == reference_key("  - ") == ""


async def test_staff_reference_follows_the_guest_rule(client, db_session, pv):
    bill_id = await bill_id_of(db_session, await order_2340(client, pv))
    await as_member(client, db_session, pv.r.id, "staff")
    for bad in ("TX\u00a01", "TX\u200b1", "TX\uff11", "TX\t1", "TX\n1", "<b>", "x" * 65):
        resp = await settle(client, pv.r.slug, bill_id, "raast", payment_reference=bad)
        assert resp.status_code == 422, bad
    ok = await settle(client, pv.r.slug, bill_id, "raast", payment_reference="  TX 9  ")
    assert ok.status_code == 200, ok.text
    assert ok.json()["payment_reference"] == "TX 9"


async def test_same_claim_on_two_open_bills_is_flagged(client, db_session, pv):
    a_bill = await bill_id_of(db_session, await order_2340(client, pv))
    b_bill = await bill_id_of(db_session, await place(client, pv.session_t2, [(pv.naan, 2)]))
    for session, ref in ((pv.session_t1, "R-5"), (pv.session_t2, "r 5")):
        guest(client, session)
        assert (await client.post(PAY, json={"method": "raast", "reference": ref})).is_success
    await as_member(client, db_session, pv.r.id, "staff")
    a, b = await detail(client, pv, a_bill), await detail(client, pv, b_bill)
    assert a["reused_reference_open_bill_no"] == b["bill_no"]
    assert b["reused_reference_open_bill_no"] == a["bill_no"]
    assert a["reused_reference_bill_no"] is None
    assert {m["method"]: m["total"] for m in a["methods"]} == {
        "cash": "2714.00",
        "card": "2527.00",
        "wallet": "2527.00",
        "raast": "2527.00",
        "bank_transfer": "2714.00",
    }


async def test_void_of_the_last_order_cancels_the_bill(client, db_session, pv):
    only = await place(client, pv.session_t1, [(pv.naan, 2)])
    old_bill = await bill_id_of(db_session, only)
    old_no = await db_session.scalar(select(Bill.bill_no).where(Bill.id == old_bill))
    staff = await as_member(client, db_session, pv.r.id, "staff")
    resp = await client.post(url(pv, f"/orders/{only}/void"), json={"reason": "Wrong table"})
    assert resp.status_code == 200, resp.text
    stored = (await db_session.execute(select(Bill).where(Bill.id == old_bill))).scalar_one()
    assert (stored.status, stored.cancelled_by, stored.cancel_reason) == (
        "cancelled",
        staff.id,
        "All orders voided",
    )
    assert stored.cancelled_at is not None
    assert await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.restaurant_id == pv.r.id, AuditLog.event_type == "bill_cancelled")
    )
    tiles = (await client.get(url(pv, "/floor"))).json()["tiles"]
    t1 = next(t for t in tiles if t["label"] == "T1")
    assert t1["state"] not in ("paying", "ordered")
    assert t1["bill_id"] is None

    # The next party never sees the old bill or its removed lines, and gets a new bill.
    nxt = await new_party(db_session, pv, pv.t1)
    guest(client, nxt)
    assert (await client.get("/api/guest/bill")).status_code == 404
    new_bill = await bill_id_of(db_session, await place(client, nxt, [(pv.naan, 1)]))
    assert new_bill != old_bill
    assert await db_session.scalar(select(Bill.bill_no).where(Bill.id == new_bill)) == old_no + 1
    guest(client, nxt)
    mine = (await client.get("/api/guest/bill")).json()
    assert (mine["status"], mine["subtotal"], mine["voided"]) == ("open", "60.00", [])


async def test_kitchen_cannot_bump_or_recall_a_voided_order(client, db_session, pv):
    keep = await order_2340(client, pv)
    gone = await place(client, pv.session_t1, [(pv.naan, 1)])
    await as_member(client, db_session, pv.r.id, "staff")
    kitchen = url(pv, "/kitchen/orders")
    assert (await client.post(f"{kitchen}/{keep}/bump")).status_code == 200
    assert (await client.post(url(pv, f"/orders/{gone}/void"), json={"reason": "x"})).is_success
    bump = await client.post(f"{kitchen}/{gone}/bump")
    assert (bump.status_code, bump.json()["detail"]) == (409, "Order was cancelled")
    assert (await client.post(f"{kitchen}/{gone}/recall")).status_code == 409


@pytest.mark.timeout(120)
async def test_bump_and_recall_racing_a_void(committed_venue):  # noqa: F811 - the imported fixture
    restaurant_id, slug, item_id, session_id, staff = committed_venue
    table_id = await _table_of(session_id)
    base = f"/api/restaurants/{slug}"
    async with _Clients(staff) as c:
        for n in range(6):
            party = await _new_committed_party(restaurant_id, table_id)
            c.guest.cookies.set(GUEST_COOKIE_NAME, sign_value(str(party)))
            first = await c.guest.post("/api/orders", json=_order_body(item_id))
            second = (await c.guest.post("/api/orders", json=_order_body(item_id))).json()["id"]
            if n % 2:  # recall race: bumped first
                assert (await c.staff.post(f"{base}/kitchen/orders/{second}/bump")).is_success
                kitchen = f"{base}/kitchen/orders/{second}/recall"
            else:
                kitchen = f"{base}/kitchen/orders/{second}/bump"
            k, v = await asyncio.gather(
                c.staff.post(kitchen),
                c.staff.post(f"{base}/orders/{second}/void", json={"reason": "x"}),
            )
            assert k.status_code in (200, 409), k.text
            assert v.status_code == 200, v.text
            async with async_session_factory() as s:
                order = await s.get(Order, uuid.UUID(second))
                assert (order.status, order.voided_at is not None) == ("cancelled", True)
            bill_id = await _bill_of(first.json()["id"])
            assert (await settle(c.staff, slug, bill_id)).status_code == 200


@pytest.mark.timeout(120)
async def test_same_reference_settled_on_two_bills_at_once(committed_venue):  # noqa: F811
    restaurant_id, slug, item_id, session_id, staff = committed_venue
    first_table = await _table_of(session_id)
    async with async_session_factory() as s:
        second = DiningTable(restaurant_id=restaurant_id, label="P2", qr_token=uuid.uuid4().hex)
        s.add(second)
        await s.commit()
        second_table = second.id
    async with _Clients(staff) as c:
        for n in range(4):
            bills = []
            for table, ref in ((first_table, f"SAME-{n}"), (second_table, f"same {n}")):
                party = await _new_committed_party(restaurant_id, table)
                c.guest.cookies.set(GUEST_COOKIE_NAME, sign_value(str(party)))
                placed = await c.guest.post("/api/orders", json=_order_body(item_id))
                assert placed.status_code == 201, placed.text
                claim = await c.guest.post(PAY, json={"method": "raast", "reference": ref})
                assert claim.status_code == 200, claim.text
                bills.append(await _bill_of(placed.json()["id"]))
            body = {
                "payment_method": "raast",
                "expected_method": "raast",
                "expected_total": "65.00",
            }
            results = await asyncio.gather(
                *(
                    c.staff.post(f"/api/restaurants/{slug}/bills/{b}/settle", json=body)
                    for b in bills
                )
            )
            codes = [r.status_code for r in results]
            assert sorted(codes) == [200, 409], [r.text for r in results]
            refused = results[codes.index(409)]
            assert refused.json()["detail"].startswith("Reference already used on Bill ")
            ok = await c.staff.post(
                f"/api/restaurants/{slug}/bills/{bills[codes.index(409)]}/settle",
                json={**body, "acknowledge_reused_reference": True},
            )
            assert ok.status_code == 200, ok.text


# --- Voiding a bill the guest says they paid; cancelled bills stay visible ---


async def test_void_emptying_a_claimed_bill_needs_confirmation(client, db_session, pv):
    only = await order_2340(client, pv)
    bill_id = await bill_id_of(db_session, only)
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "raast", "reference": "TX-4471"})).is_success
    staff = await as_member(client, db_session, pv.r.id, "staff")
    void_url = url(pv, f"/orders/{only}/void")

    refused = await client.post(void_url, json={"reason": "Walked out"})
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["detail"] == (
        "Guest says they paid by Raast QR (Rs 2527.00) — any refund happens outside Mise. "
        "Confirm to void and cancel the bill."
    )
    assert (body["claim"]["method"], body["claim"]["total"]) == ("raast", "2527.00")
    stored = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    order = (await db_session.execute(select(Order).where(Order.id == only))).scalar_one()
    assert (stored.status, order.status, order.voided_at) == ("open", "placed", None)

    ok = await client.post(void_url, json={"reason": "Walked out", "acknowledge_claim": True})
    assert (ok.status_code, ok.json()["status"]) == (200, "cancelled")
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.restaurant_id == pv.r.id, AuditLog.event_type == "bill_cancelled"
            )
        )
    ).scalar_one()
    assert audit.actor == f"user:{staff.id}"
    assert {k: audit.payload[k] for k in ("claimed_method", "claimed_total")} == {
        "claimed_method": "raast",
        "claimed_total": "2527.00",
    }
    assert audit.payload["claimed_reference_last4"] == "4471"


async def test_void_of_one_of_several_orders_needs_no_confirmation(client, db_session, pv):
    await order_2340(client, pv)
    extra = await place(client, pv.session_t1, [(pv.naan, 1)])
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "cash"})).is_success
    await as_member(client, db_session, pv.r.id, "staff")
    resp = await client.post(url(pv, f"/orders/{extra}/void"), json={"reason": "Duplicate"})
    assert (resp.status_code, resp.json()["status"]) == (200, "open")


async def test_cancelled_bills_are_listed_and_readable(client, db_session, pv):
    only = await order_2340(client, pv)
    bill_id = await bill_id_of(db_session, only)
    guest(client, pv.session_t1)
    assert (await client.post(PAY, json={"method": "cash"})).is_success
    await as_member(client, db_session, pv.r.id, "owner")
    resp = await client.post(
        url(pv, f"/orders/{only}/void"), json={"reason": "Wrong table", "acknowledge_claim": True}
    )
    assert resp.status_code == 200, resp.text

    listed = await client.get(url(pv, "/bills?status=cancelled"))
    assert listed.status_code == 200, listed.text
    [row] = listed.json()["bills"]
    assert (row["id"], row["status"], row["cancel_reason"]) == (
        str(bill_id),
        "cancelled",
        "All orders voided",
    )
    assert row["cancelled_at"] is not None
    assert (row["claim"]["method"], row["claim"]["total"]) == ("cash", "2714.00")
    assert (await client.get(url(pv, "/bills?status=open"))).json()["bills"] == []

    d = await detail(client, pv, bill_id)
    assert (d["status"], d["cancel_reason"], d["cancelled_by_name"]) == (
        "cancelled",
        "All orders voided",
        "Test user",
    )
    assert d["claim"]["method"] == "cash"
    assert d["orders"][0]["voided"] is True


async def test_cancelled_bill_resets_the_table(client, db_session, pv):
    only = await place(client, pv.session_t1, [(pv.naan, 1)])
    await as_member(client, db_session, pv.r.id, "staff")
    assert (await client.post(url(pv, f"/orders/{only}/void"), json={"reason": "x"})).is_success
    # The cancel alone ends the voided party's visit, before any clear.
    assert not await session_is_current(db_session, pv.session_t1)
    # Nobody scanned since the cancel, so clearing needs no force.
    cleared = await client.post(url(pv, f"/tables/{pv.t1.id}/clear"))
    assert cleared.status_code == 200, cleared.text

    # Its phone cannot start a new bill.
    guest(client, pv.session_t1)
    again = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(pv.naan.id), "quantity": 1}],
        },
    )
    assert (again.status_code, again.json()["detail"]) == (409, VISIT_ENDED)
