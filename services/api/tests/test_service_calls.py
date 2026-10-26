"""Guest calls a waiter; staff resolve. One open call per table, 60 s between calls."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from tests import test_floor_api
from tests.helpers import as_member
from tests.test_floor_api import (
    floor,
    guest,
    new_restaurant,
    new_table,
    record_events,
    seat,
    tile,
)

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.database import async_session_factory, get_db
from src.main import app
from src.models.dining_table import DiningTable
from src.models.restaurant import Restaurant
from src.models.service_call import ServiceCall
from src.models.session import GuestSession

fv = test_floor_api.fv  # shared fixture

CALLS = "/api/guest/service-calls"


async def test_call_resolve_and_cooldown(client, db_session, fv, monkeypatch):
    events = record_events(
        monkeypatch, "src.routers.guest.publish_event", "src.routers.floor.publish_event"
    )
    s1 = await seat(db_session, fv, fv.t1)
    guest(client, s1)
    assert (await client.get(f"{CALLS}/current")).json() == {"call": None}

    first = await client.post(CALLS, json={"reason": "water"})
    assert first.status_code == 201, first.text
    call = first.json()
    assert {"id", "reason", "created_at"} <= call.keys()
    assert (call["reason"], call["reason_label"], call["resolved_at"]) == (
        "water",
        "Water, please",
        None,
    )

    again = await client.post(CALLS, json={"reason": "help"})
    assert again.status_code == 409
    assert again.json()["detail"] == "A waiter is already on the way"
    assert (await client.get(f"{CALLS}/current")).json()["call"]["id"] == call["id"]

    await as_member(client, db_session, fv.r.id, "staff")
    t1 = tile(await floor(client, fv), "T1")
    assert (t1["state"], t1["level"], t1["reason"], t1["reason_label"], t1["call_id"]) == (
        "called",
        "red",
        "water",
        "Water, please",
        call["id"],
    )

    resolve_url = f"/api/restaurants/{fv.r.slug}/service-calls/{call['id']}/resolve"
    resolved = await client.post(resolve_url)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_at"] is not None
    assert (await client.post(resolve_url)).status_code == 409
    stored = await db_session.get(ServiceCall, uuid.UUID(call["id"]))
    assert stored.resolved_by is not None

    assert (await client.get(f"{CALLS}/current")).json() == {"call": None}
    cooling = await client.post(CALLS, json={"reason": "extra"})
    assert cooling.status_code == 429
    assert 1 <= int(cooling.headers["Retry-After"]) <= 60

    await db_session.execute(
        update(ServiceCall)
        .where(ServiceCall.id == uuid.UUID(call["id"]))
        .values(created_at=ServiceCall.created_at - timedelta(seconds=61))
    )
    later = await client.post(CALLS, json={"reason": "extra"})
    assert later.status_code == 201, later.text
    assert later.json()["reason_label"] == "More naan / roti"

    assert [e["event"] for e in events] == [
        "service_call_opened",
        "service_call_resolved",
        "service_call_opened",
    ]
    assert events[0] == {
        "event": "service_call_opened",
        "call_id": call["id"],
        "table_id": str(fv.t1.id),
    }


async def test_call_refusals(client, db_session, fv):
    counter_session = await seat(db_session, fv, fv.counter)
    guest(client, counter_session)
    assert (await client.post(CALLS, json={"reason": "help"})).status_code == 422
    assert (await client.get(f"{CALLS}/current")).json() == {"call": None}

    s2 = await seat(db_session, fv, fv.t2)
    guest(client, s2)
    assert (await client.post(CALLS, json={"reason": "pizza"})).status_code == 422
    assert (await client.post(CALLS, json={})).status_code == 422

    client.cookies.clear()
    assert (await client.post(CALLS, json={"reason": "help"})).status_code == 401


async def test_resolving_another_venues_call_is_404(client, db_session, fv):
    other = new_restaurant("Other Venue")
    db_session.add(other)
    await db_session.flush()
    table = new_table(other.id, "T1")
    db_session.add(table)
    await db_session.flush()
    foreign = ServiceCall(restaurant_id=other.id, table_id=table.id, reason="help")
    db_session.add(foreign)
    await db_session.flush()

    await as_member(client, db_session, fv.r.id, "owner")
    resp = await client.post(f"/api/restaurants/{fv.r.slug}/service-calls/{foreign.id}/resolve")
    assert resp.status_code == 404
    await db_session.refresh(foreign)
    assert foreign.resolved_at is None


async def test_expired_guest_session_is_401(client, db_session, fv):
    expired = GuestSession(
        restaurant_id=fv.r.id,
        table_id=fv.t1.id,
        language="en",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.add(expired)
    await db_session.flush()
    guest(client, expired)
    assert (await client.post(CALLS, json={"reason": "help"})).status_code == 401
    assert (await client.get(f"{CALLS}/current")).status_code == 401


async def test_calls_stay_in_their_own_venue(client, db_session, fv):
    other = new_restaurant("Venue B")
    db_session.add(other)
    await db_session.flush()
    db_session.add(new_table(other.id, "T1"))
    await db_session.flush()

    guest(client, await seat(db_session, fv, fv.t1))
    resp = await client.post(CALLS, json={"reason": "help"})
    assert resp.status_code == 201
    stored = await db_session.get(ServiceCall, uuid.UUID(resp.json()["id"]))
    assert (stored.restaurant_id, stored.table_id) == (fv.r.id, fv.t1.id)

    await as_member(client, db_session, other.id, "staff")
    b_floor = (await client.get(f"/api/restaurants/{other.slug}/floor")).json()
    assert [(t["label"], t["state"], t["call_id"]) for t in b_floor["tiles"]] == [
        ("T1", "free", None)
    ]
    resolve = await client.post(f"/api/restaurants/{other.slug}/service-calls/{stored.id}/resolve")
    assert resolve.status_code == 404


TABLES = 5


@pytest_asyncio.fixture
async def committed_tables():
    """Committed venue with TABLES tables and two guest sessions on each."""
    restaurant_id = uuid.uuid4()
    pairs = []
    async with async_session_factory() as s:
        s.add(
            Restaurant(
                id=restaurant_id,
                name="Parallel Calls",
                slug=f"calls-par-{uuid.uuid4().hex[:8]}",
                currency="PKR",
                timezone="Asia/Karachi",
                languages=["en"],
                default_language="en",
            )
        )
        await s.flush()
        for n in range(TABLES):
            table_id = uuid.uuid4()
            s.add(
                DiningTable(
                    id=table_id,
                    restaurant_id=restaurant_id,
                    label=f"P{n}",
                    qr_token=uuid.uuid4().hex,
                )
            )
            await s.flush()
            session_ids = [uuid.uuid4(), uuid.uuid4()]
            s.add_all(
                GuestSession(
                    id=sid,
                    restaurant_id=restaurant_id,
                    table_id=table_id,
                    language="en",
                    expires_at=datetime.now(UTC) + timedelta(hours=2),
                )
                for sid in session_ids
            )
            pairs.append((table_id, session_ids))
        await s.commit()
    try:
        yield pairs
    finally:
        async with async_session_factory() as s:
            await s.execute(delete(ServiceCall).where(ServiceCall.restaurant_id == restaurant_id))
            await s.execute(delete(GuestSession).where(GuestSession.restaurant_id == restaurant_id))
            await s.execute(delete(DiningTable).where(DiningTable.restaurant_id == restaurant_id))
            await s.execute(delete(Restaurant).where(Restaurant.id == restaurant_id))
            await s.commit()


def _guest_client(session_id: uuid.UUID) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={GUEST_COOKIE_NAME: sign_value(str(session_id))},
    )


@pytest.mark.timeout(120)
async def test_parallel_calls_on_one_table(committed_tables):
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        for table_id, (a, b) in committed_tables:
            async with _guest_client(a) as first, _guest_client(b) as second:
                results = await asyncio.gather(
                    first.post(CALLS, json={"reason": "help"}),
                    second.post(CALLS, json={"reason": "water"}),
                )
            codes = sorted(r.status_code for r in results)
            assert codes == [201, 409], [r.text for r in results]
            async with async_session_factory() as s:
                open_calls = (
                    await s.scalars(
                        select(ServiceCall.id).where(
                            ServiceCall.table_id == table_id, ServiceCall.resolved_at.is_(None)
                        )
                    )
                ).all()
            assert len(open_calls) == 1
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override
