"""Guest calls a waiter; staff resolve. One open call per table, 60 s between calls."""

import uuid
from datetime import timedelta

from sqlalchemy import update
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

from src.models.service_call import ServiceCall

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
    assert (await client.post(CALLS, json={"reason": "extra"})).status_code == 429

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
