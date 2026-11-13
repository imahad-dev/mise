"""Tikka Town's real seed bills as the UK checks in test_global_bills.py say."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import select
from tests.helpers import as_member, settle
from tests.test_bills import bill_id_of
from tests.test_global_bills import _order

from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.simulator import SEED_ITEM_NAMESPACE

SLUG = "tikka-town"


async def _guest_at(db, r, label):
    t = (
        await db.execute(
            select(DiningTable).where(DiningTable.restaurant_id == r.id, DiningTable.label == label)
        )
    ).scalar_one()
    s = GuestSession(
        restaurant_id=r.id,
        table_id=t.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    return s


@pytest_asyncio.fixture
async def tikka(db_session):
    """What test_global_bills' `uk` returns, from data/seed/tikka_town.json."""
    await seed_data(load_seed_data("data/seed/tikka_town.json"), db_session)
    r = (await db_session.execute(select(Restaurant).where(Restaurant.slug == SLUG))).scalar_one()

    async def dish(key):
        item_id = uuid.uuid5(SEED_ITEM_NAMESPACE, f"{SLUG}:{key}")
        return (
            await db_session.execute(select(MenuItem).where(MenuItem.id == item_id))
        ).scalar_one()

    pie, naan = await dish("chicken_tikka_pie"), await dish("plain_naan")
    # The arithmetic below is for these seeded prices.
    assert (pie.price, naan.price) == (Decimal("14.95"), Decimal("3.50"))
    s = await _guest_at(db_session, r, "T1")
    t = (
        await db_session.execute(select(DiningTable).where(DiningTable.id == s.table_id))
    ).scalar_one()
    return r, t, pie, naan, s


async def test_tikka_bill_is_gbp_with_vat_included_and_service_on_its_own_line(
    client, db_session, tikka
):
    r, _, dish, side, s = tikka
    assert r.currency == "GBP"
    o = await _order(client, s, [(dish, 1), (side, 2)])  # 14.95 + 7.00 = 21.95
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    d = (await client.get(f"/api/restaurants/{r.slug}/bills/{bill_id}")).json()
    assert [m["method"] for m in d["methods"]] == ["cash", "card"]
    card = next(m for m in d["methods"] if m["method"] == "card")
    # VAT inside the price: 21.95 / 6 = 3.66. Service: 10% of 21.95 = 2.20, outside tax.
    assert (card["total"], card["tax_amount"], card["tax_included"]) == ("21.95", "3.66", True)
    assert (d["service_charge_rate"], d["service_charge_amount"]) == ("0.1000", "2.20")


async def test_tikka_settles_in_gbp_with_and_without_service(client, db_session, tikka):
    r, _, dish, side, s = tikka

    # With service (test_uk_settle_with_service).
    o = await _order(client, s, [(dish, 1), (side, 2)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await settle(client, r.slug, bill_id, "card", service_included=True)
    assert resp.status_code == 200, resp.text
    b = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    await db_session.refresh(b)
    assert (b.tax_pricing, b.tax_amount, b.service_charge_amount, b.total) == (
        "included",
        Decimal("3.66"),
        Decimal("2.20"),
        Decimal("24.15"),
    )

    # Without service (test_uk_settle_without_service), at T2: settling closed T1.
    o = await _order(client, await _guest_at(db_session, r, "T2"), [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await settle(client, r.slug, bill_id, "cash")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == "14.95"
    assert resp.json()["service_charge_amount"] == "0.00"


async def test_tikka_refuses_a_method_the_uk_does_not_list(client, db_session, tikka):
    r, _, dish, _, s = tikka
    o = await _order(client, s, [(dish, 1)])
    bill_id = await bill_id_of(db_session, o)
    await as_member(client, db_session, r.id, "staff")
    resp = await client.post(
        f"/api/restaurants/{r.slug}/bills/{bill_id}/settle",
        json={
            "payment_method": "raast",
            "expected_method": "raast",
            "expected_total": "14.95",
            "payment_reference": "R1",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Payment method not accepted here"
    status = await db_session.scalar(select(Bill.status).where(Bill.id == bill_id))
    assert status == "open"
