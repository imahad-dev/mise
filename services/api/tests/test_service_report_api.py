"""Service report API: one local day of sittings, read from recorded timestamps."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, settle
from tests.test_floor_api import fv, guest, new_restaurant, order, seat  # noqa: F401

from src.inference.client import InferenceClient
from src.main import app
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.order import Order
from src.models.session import GuestSession
from src.models.sitting import TableSitting
from src.routers import owner as owner_router

DAY = "2026-10-20"
NOON = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)  # 12:00 in Asia/Karachi
M = timedelta(minutes=1)


def url(venue) -> str:
    return f"/api/restaurants/{venue.r.slug}/service-report"


class FakeRedis:
    """In-memory stand-in for the router's Redis: records each write's TTL."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int | None] = {}
        self.down = False

    async def get(self, key):
        if self.down:
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if self.down:
            raise ConnectionError("redis down")
        self.store[key], self.ttl[key] = value, ex


@pytest.fixture(autouse=True)
def cache(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(owner_router, "redis_client", fake)
    return fake


@pytest.fixture
def narrate_calls(monkeypatch) -> list:
    calls: list = []
    real = owner_router.narrate

    async def spy(*args, **kwargs):
        calls.append(args)
        return await real(*args, **kwargs)

    monkeypatch.setattr(owner_router, "narrate", spy)
    return calls


async def test_a_served_table_shows_in_todays_report(client, db_session, fv):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "owner")
    s1 = await seat(db_session, fv, fv.t1)
    opened = await client.post(f"/api/restaurants/{fv.r.slug}/tables/{fv.t1.id}/sitting")
    assert opened.status_code == 201, opened.text
    order_id = await order(client, s1, fv.naan)
    bump = await client.post(f"/api/restaurants/{fv.r.slug}/kitchen/orders/{order_id}/bump")
    assert bump.status_code == 200, bump.text
    guest(client, s1)
    assert (await client.post("/api/guest/bill-request")).status_code == 200
    floor = (await client.get(f"/api/restaurants/{fv.r.slug}/floor")).json()
    bill_id = next(t for t in floor["tiles"] if t["label"] == "T1")["bill_id"]
    assert (await settle(client, fv.r.slug, bill_id)).status_code == 200

    resp = await client.get(url(fv))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables_served"] == 1
    assert body["closed_without_bill"] == 0
    assert body["simulated_sittings"] == 0
    assert body["average_table_seconds"] is not None
    assert all(v is not None for v in body["average_wait_seconds"].values())
    assert body["busiest_hour"] is not None
    assert body["summary_source"] == "template"  # no model attached in tests


async def _session(db: AsyncSession, venue, table) -> GuestSession:
    s = GuestSession(
        restaurant_id=venue.r.id,
        table_id=table.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    return s


async def _sitting(db, table, opened, closed, reason) -> TableSitting:
    s = TableSitting(table_id=table.id, opened_at=opened, closed_at=closed, close_reason=reason)
    db.add(s)
    await db.flush()
    return s


async def _bill(db, venue, table, no, requested, settled) -> Bill:
    b = Bill(
        restaurant_id=venue.r.id,
        table_id=table.id,
        bill_no=no,
        status="settled",
        bill_requested_at=requested,
        settled_at=settled,
        payment_method="cash",
        total=Decimal("60.00"),
    )
    db.add(b)
    await db.flush()
    return b


async def _order(db, venue, table, sitting, bill, placed, bumped, approved=None) -> Order:
    gs = await _session(db, venue, table)
    o = Order(
        guest_session_id=gs.id,
        restaurant_id=venue.r.id,
        table_id=table.id,
        sitting_id=sitting.id,
        bill_id=bill.id,
        status="bumped",
        total=Decimal("60.00"),
        idempotency_key=uuid.uuid4().hex,
        payload_hash="x",
        placed_at=placed,
        bumped_at=bumped,
    )
    db.add(o)
    await db.flush()
    if approved is not None:
        db.add(
            AuditLog(
                restaurant_id=venue.r.id,
                event_type="order_approved",
                actor="user:test",
                payload={"order_id": str(o.id), "bill_id": str(bill.id)},
                created_at=approved,
            )
        )
        await db.flush()
    return o


@pytest_asyncio.fixture
async def day(db_session: AsyncSession, fv):  # noqa: F811
    """On DAY, T1 seats a party 12:00-12:50 local; the day before, T1 had a slow-paying party
    on another bill; T3 was opened and closed unused; a T2 party ran past local midnight."""
    s = await _sitting(db_session, fv.t1, NOON, NOON + 50 * M, "settled")
    bill = await _bill(db_session, fv, fv.t1, 1, NOON + 40 * M, NOON + 44 * M)
    await _order(db_session, fv, fv.t1, s, bill, NOON + 4 * M, NOON + 15 * M, approved=NOON + 5 * M)
    # Yesterday, same table, another bill: never joined to today's sitting.
    y = NOON - timedelta(days=1)
    old = await _sitting(db_session, fv.t1, y, y + 90 * M, "settled")
    old_bill = await _bill(db_session, fv, fv.t1, 2, y + 10 * M, y + 80 * M)
    await _order(db_session, fv, fv.t1, old, old_bill, y + M, y + 5 * M)
    await _sitting(db_session, fv.t3, NOON - 120 * M, NOON - 90 * M, "staff_closed")
    # Opened 23:30 local DAY, closed 00:20 local the next day: tomorrow's report.
    late = NOON + 11 * 60 * M + 30 * M
    await _sitting(db_session, fv.t2, late, late + 50 * M, "cancelled")
    await db_session.flush()


async def test_report_numbers_for_a_day(client, db_session, fv, day):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "owner")
    resp = await client.get(url(fv), params={"day": DAY})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["day"] == DAY
    assert body["tables_served"] == 1
    assert body["closed_without_bill"] == 1
    assert body["simulated_sittings"] == 0
    assert body["average_table_seconds"] == 50 * 60
    assert body["average_wait_seconds"] == {
        "first_order": 4 * 60,
        "approval": 60,
        "kitchen": 10 * 60,
        "bill": 4 * 60,  # this sitting's bill, not yesterday's 70-minute one on the same table
    }
    assert body["busiest_hour"] == 12
    assert body["slowest_hour"] is None  # no hour had two tables
    assert body["alerts"] == {
        "seated_no_order": 1,  # T3 sat 30 minutes without an order
        "approval_needed": 0,
        "order_no_bump": 0,
        "bill_not_settled": 0,
    }
    assert body["summary"] == (
        f"On {DAY}, 1 table was served, averaging 50 minutes per table, busiest at 12:00, "
        "with 1 red alert."
    )

    tomorrow = (await client.get(url(fv), params={"day": "2026-10-21"})).json()
    assert tomorrow["tables_served"] == 1  # the party that ran past midnight
    assert tomorrow["busiest_hour"] == 23


async def test_an_empty_day_is_zeros_not_an_error(client, db_session, fv):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "owner")
    resp = await client.get(url(fv), params={"day": "2020-01-01"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables_served"] == 0 and body["closed_without_bill"] == 0
    assert body["average_table_seconds"] is None
    assert set(body["average_wait_seconds"].values()) == {None}
    assert body["busiest_hour"] is None and body["slowest_hour"] is None
    assert set(body["alerts"].values()) == {0}
    assert body["summary"] == "No tables were served on 2020-01-01."


async def test_bad_day_is_422(client, db_session, fv):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "owner")
    assert (await client.get(url(fv), params={"day": "2026-13-40"})).status_code == 422


async def test_non_member_gets_404(client, db_session, fv):  # noqa: F811
    other = new_restaurant("Other Venue")
    db_session.add(other)
    await db_session.flush()
    await as_member(client, db_session, other.id, "owner")
    assert (await client.get(url(fv))).status_code == 404


async def test_staff_gets_403_like_the_brief(client, db_session, fv):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "staff")
    assert (await client.get(url(fv))).status_code == 403
    assert (await client.get(f"/api/restaurants/{fv.r.slug}/ai/brief")).status_code == 403


async def test_report_is_cached_per_day(client, db_session, fv, day, cache, narrate_calls):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "owner")
    first = await client.get(url(fv), params={"day": DAY})
    again = await client.get(url(fv), params={"day": DAY})
    assert first.json() == again.json()
    assert len(narrate_calls) == 1  # the second call never reached the model
    await client.get(url(fv), params={"day": "2026-10-21"})
    assert len(narrate_calls) == 2  # another day is another entry

    # A past day is final; today can still change.
    today = (await client.get(url(fv))).json()["day"]
    ttl = {k.rsplit(":", 1)[1]: v for k, v in cache.ttl.items()}
    assert ttl[DAY] == ttl["2026-10-21"] == 7 * 24 * 3600
    assert ttl[today] == 5 * 60
    assert all(str(fv.r.id) in k for k in cache.ttl)


async def test_redis_down_fails_open(client, db_session, fv, day, cache, narrate_calls):  # noqa: F811
    await as_member(client, db_session, fv.r.id, "owner")
    cache.down = True
    resp = await client.get(url(fv), params={"day": DAY})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tables_served"] == 1
    await client.get(url(fv), params={"day": DAY})
    assert len(narrate_calls) == 2


async def test_each_same_day_sitting_uses_its_own_bill(client, db_session, fv):  # noqa: F811
    """Two parties at T2 on one day, each with its own bill: 2- and 10-minute bill waits."""
    first = await _sitting(db_session, fv.t2, NOON, NOON + 30 * M, "settled")
    early = await _bill(db_session, fv, fv.t2, 3, NOON + 20 * M, NOON + 22 * M)
    await _order(db_session, fv, fv.t2, first, early, NOON + 2 * M, NOON + 10 * M)
    second = await _sitting(db_session, fv.t2, NOON + 60 * M, NOON + 100 * M, "settled")
    late = await _bill(db_session, fv, fv.t2, 4, NOON + 80 * M, NOON + 90 * M)
    await _order(db_session, fv, fv.t2, second, late, NOON + 62 * M, NOON + 70 * M)
    await as_member(client, db_session, fv.r.id, "owner")
    body = (await client.get(url(fv), params={"day": DAY})).json()
    assert body["tables_served"] == 2
    # One bill for both would give 2 or 10 minutes and 0 or 2 red bill alerts.
    assert body["average_wait_seconds"]["bill"] == 6 * 60
    assert body["alerts"]["bill_not_settled"] == 1


@pytest.fixture
def model_says():
    """Attach a mock-provider inference client that replies with the given summary."""
    sent: list[dict] = []
    reply: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"summary": reply["text"]})}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock/v1")
    app.state.inference_client = InferenceClient(llm_client=mock, vlm_client=mock)
    yield reply, sent
    del app.state.inference_client


async def test_summary_from_the_model_must_pass_the_number_check(
    client,
    db_session,
    fv,  # noqa: F811
    day,
    model_says,
    cache,
):
    reply, sent = model_says
    await as_member(client, db_session, fv.r.id, "owner")

    reply["text"] = "One table was served, staying 50 minutes, busiest at 12:00."
    body = (await client.get(url(fv), params={"day": DAY})).json()
    assert (body["summary"], body["summary_source"]) == (reply["text"], "llm")

    reply["text"] = "3 tables were served in 44 minutes."
    cache.store.clear()
    body = (await client.get(url(fv), params={"day": DAY})).json()
    assert body["summary_source"] == "template"
    assert body["summary"].startswith(f"On {DAY}, 1 table was served")

    # The day is not a fact: its digits (2026, 10, 20) ground nothing.
    reply["text"] = "20 tables were served."
    cache.store.clear()
    body = (await client.get(url(fv), params={"day": DAY})).json()
    assert body["summary_source"] == "template"

    # The model sees only the report's numbers: no table, guest, order or bill identifiers.
    facts = sent[-1]["messages"][-1]["content"]
    for secret in (fv.t1.label, str(fv.t1.id), fv.r.slug, "allerg", "session"):
        assert secret not in facts
