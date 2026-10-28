"""Money agreement: an independent rate oracle, the tax function, the guest's per-method
preview and the staff preview agree for every bill; the shared UI vectors match the server;
and on real bills the guest's preview is what settles and what analytics counts."""

import json
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, settle
from tests.test_bills import bill_id_of, guest, place
from tests.test_payment_claims import _venue

from src.models.bill import Bill
from src.models.order import Order
from src.models.session import GuestSession
from src.services import analytics
from src.services.analytics import Window
from src.services.bills import method_previews, previews
from src.services.tax import PAYMENT_METHODS, payment_class, tax_for

CASES = 2000

# Independent oracle, written out by hand from the law (not read from data/tax_rates.json):
# (jurisdiction, class) -> [(effective from, rate)], latest applicable entry wins.
ORACLE_RATES = {
    ("PB", "standard"): [(date(2025, 7, 1), "0.16")],
    ("PB", "digital"): [(date(2025, 7, 1), "0.05"), (date(2026, 7, 1), "0.08")],
    ("ICT", "standard"): [(date(2023, 7, 1), "0.15")],
    ("ICT", "digital"): [(date(2023, 7, 1), "0.05")],
}
ORACLE_DIGITAL = {"card", "wallet", "raast"}


def oracle(jurisdiction: str, method: str, on: date, subtotal: Decimal) -> tuple[Decimal, Decimal]:
    cls = "digital" if method in ORACLE_DIGITAL else "standard"
    rate = Decimal([r for start, r in ORACLE_RATES[(jurisdiction, cls)] if start <= on][-1])
    return rate, (subtotal * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _vectors_file() -> Path:
    # /app/data in the container, <repo>/data in a checkout.
    for base in Path(__file__).resolve().parents:
        candidate = base / "data" / "test-vectors" / "tax_vectors.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("data/test-vectors/tax_vectors.json")


def test_guest_preview_tax_function_and_staff_preview_agree():
    rng = random.Random(1234)
    for _ in range(CASES):
        subtotal = Decimal(rng.randint(0, 200_000)).quantize(Decimal("0.01"))
        method = rng.choice(PAYMENT_METHODS)
        jurisdiction = rng.choice(["PB", "ICT"])
        on = date(2026, 6, 25) + timedelta(days=rng.randint(0, 10))
        case = (jurisdiction, method, on, subtotal)

        guest = {p.method: p for p in method_previews(jurisdiction, subtotal, on)}[method]
        rate, tax = tax_for(jurisdiction, method, on, subtotal)
        standard, digital = previews(jurisdiction, subtotal, on)
        staff = digital if payment_class(method) == "digital" else standard

        assert (rate, tax) == oracle(jurisdiction, method, on, subtotal), case
        assert guest.tax_rate == rate == staff.tax_rate, case
        assert guest.tax_amount == tax == staff.tax_amount, case
        assert guest.total == subtotal + tax == staff.total, case
        assert guest.payment_class == staff.payment_class == payment_class(method), case
        assert tax == tax.to_integral_value(), case  # whole rupees


def test_exact_edges():
    card, cash = "card", "cash"
    # Half a rupee rounds up.
    assert tax_for("ICT", card, date(2026, 7, 1), Decimal("10.00"))[1] == Decimal("1")
    assert tax_for("ICT", cash, date(2026, 7, 1), Decimal("30.00"))[1] == Decimal("5")
    # Punjab card tax moves from 5% to 8% on 1 July 2026; cash stays 16%.
    assert tax_for("PB", card, date(2026, 6, 30), Decimal("2340.00")) == (
        Decimal("0.05"),
        Decimal("117"),
    )
    assert tax_for("PB", card, date(2026, 7, 1), Decimal("2340.00")) == (
        Decimal("0.08"),
        Decimal("187"),
    )
    assert tax_for("PB", cash, date(2026, 6, 30), Decimal("2340.00"))[1] == Decimal("374")


def test_shared_ui_vectors_match_the_server():
    doc = json.loads(_vectors_file().read_text(encoding="utf-8"))
    vectors = doc["vectors"]
    assert len(vectors) == 50
    for v in vectors:
        expected = next(
            p
            for p in method_previews(
                v["jurisdiction"], Decimal(v["subtotal"]), date.fromisoformat(v["date"])
            )
            if p.method == v["method"]
        )
        got = {k: v[k] for k in expected.model_dump(mode="json")}
        assert got == expected.model_dump(mode="json"), v


# --- Database-backed sample: guest preview = settled total; analytics revenue = settled ---

BILLS = 30
WINDOW_DAY = date(2026, 5, 10)


@pytest_asyncio.fixture
async def mv(db_session: AsyncSession):
    return await _venue(db_session, "Money Venue")


async def test_sample_bills_agree_from_guest_to_analytics(client, db_session, mv):
    rng = random.Random(1234)
    await as_member(client, db_session, mv.r.id, "staff")
    settled = []
    voided = 0
    for i in range(BILLS):
        party = GuestSession(
            restaurant_id=mv.r.id,
            table_id=mv.t1.id,
            language="en",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
            created_at=await db_session.scalar(select(func.clock_timestamp())),
        )
        db_session.add(party)
        await db_session.flush()
        orders = []
        for _ in range(rng.randint(1, 3)):
            lines = [(mv.naan, rng.randint(1, 4))]
            if rng.random() < 0.5:
                lines.append((mv.karahi, 1, rng.choice([mv.half, mv.full])))
            orders.append(await place(client, party, lines))
        if len(orders) > 1 and rng.random() < 0.4:
            void = await client.post(
                f"/api/restaurants/{mv.r.slug}/orders/{orders[0]}/void", json={"reason": "Test"}
            )
            assert void.status_code == 200, void.text
            voided += 1
        method = rng.choice(PAYMENT_METHODS)
        guest(client, party)
        shown = (await client.get("/api/guest/bill")).json()
        guest_total = next(m["total"] for m in shown["methods"] if m["method"] == method)
        bill_id = await bill_id_of(db_session, orders[-1])
        resp = await settle(client, mv.r.slug, bill_id, method, payment_reference=f"S-{i}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == guest_total
        settled.append(bill_id)
    assert voided > 0

    # Move the sample into one past local day so the analytics window holds exactly these bills.
    noon = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)  # 12:00 in Karachi
    for n, bill_id in enumerate(settled):
        at = noon + timedelta(minutes=n)
        await db_session.execute(update(Bill).where(Bill.id == bill_id).values(settled_at=at))
        await db_session.execute(update(Order).where(Order.bill_id == bill_id).values(placed_at=at))
    bills = (await db_session.scalars(select(Bill).where(Bill.id.in_(settled)))).all()
    active = await db_session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.bill_id.in_(settled), Order.status != "cancelled")
    )
    w = Window(mv.r.id, "Asia/Karachi", WINDOW_DAY, WINDOW_DAY + timedelta(days=1))
    kpis = await analytics.kpis(db_session, w)
    assert Decimal(str(kpis["revenue"])) == sum(b.subtotal for b in bills)
    assert kpis["orders"] == active  # voided orders are not revenue
    mix = await analytics.payment_mix(db_session, w, mv.r)
    assert sum(mix["bills"].values()) == BILLS


async def test_revenue_counts_only_settled_bills(client, db_session, mv):
    """An order on a still-open bill is not revenue; it counts once the bill settles; a voided
    order and a cancelled bill never count."""
    await as_member(client, db_session, mv.r.id, "staff")
    parties = []
    for table in (mv.t1, mv.t2):
        party = GuestSession(
            restaurant_id=mv.r.id,
            table_id=table.id,
            language="en",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
            created_at=await db_session.scalar(select(func.clock_timestamp())),
        )
        db_session.add(party)
        parties.append(party)
    await db_session.flush()
    kept = await place(client, parties[0], [(mv.naan, 2)])
    voided = await place(client, parties[0], [(mv.naan, 1)])
    cancelled = await place(client, parties[1], [(mv.naan, 3)])
    await as_member(client, db_session, mv.r.id, "staff")
    for order in (voided, cancelled):  # voiding the only order cancels the second bill
        void = await client.post(
            f"/api/restaurants/{mv.r.slug}/orders/{order}/void", json={"reason": "Test"}
        )
        assert void.status_code == 200, void.text
    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Karachi")).date()
    w = Window(mv.r.id, "Asia/Karachi", today, today + timedelta(days=1))

    before = await analytics.kpis(db_session, w)
    assert (before["orders"], Decimal(str(before["revenue"]))) == (0, 0)

    bill_id = await bill_id_of(db_session, kept)
    assert (await settle(client, mv.r.slug, bill_id, "cash")).status_code == 200
    subtotal = await db_session.scalar(select(Bill.subtotal).where(Bill.id == bill_id))
    after = await analytics.kpis(db_session, w)
    assert (after["orders"], Decimal(str(after["revenue"]))) == (1, subtotal)
    assert await analytics.order_counts_by_source(db_session, w) == {"live": 1, "simulated": 0}
