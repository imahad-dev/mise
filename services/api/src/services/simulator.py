"""Synthetic order generator for demos and tests. Every order and bill it writes has
source='simulated'.

Assumptions are documented in docs/analytics.md and exposed as `SimAssumptions` fields; a venue
profile (`restaurant.onboarding["simulation"]`, written by the seed) overrides the defaults and
carries per-item weights. Generation (`generate_orders`) is pure and seeded;
`persist_simulation` writes the result through the same snapshot code as live orders.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import selectinload

from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.forecast import ForecastRun
from src.models.menu import MenuItem
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.order_snapshot import line_total, snapshot_order_item
from src.services.tax import PAYMENT_METHODS, TaxRate, TaxRateError, default_rates, tax_for

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DAYPARTS = ("lunch", "dinner")
PROMOTION_EVENT = "promotion"
# Seeded menu ids: uuid5(ns, "slug:item_key") and uuid5(ns, "slug:item_key:option_label").
SEED_ITEM_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d")
# Keys of a stored venue profile that are per-item data, not SimAssumptions fields.
PROFILE_DATA_KEYS = frozenset({"weights", "option_weights"})
CENTS = Decimal("0.01")


@dataclass(frozen=True)
class SimAssumptions:
    days: int = 56
    seed: int = 42
    # Mean tables (orders) per daypart, Monday..Sunday
    lunch_rate: tuple[float, ...] = (7, 8, 8, 9, 11, 15, 13)
    dinner_rate: tuple[float, ...] = (10, 11, 12, 14, 22, 26, 16)
    # Local service windows [start, end) in hours
    lunch_hours: tuple[int, int] = (12, 15)
    dinner_hours: tuple[int, int] = (19, 23)
    # Party size distribution: sizes 1..6
    party_size_weights: tuple[float, ...] = (0.10, 0.45, 0.15, 0.22, 0.04, 0.04)
    # Mean dishes per guest (Poisson, at least one per guest)
    dishes_per_guest: float = 1.4
    # Day-level multiplicative noise: exp(N(0, noise_sd))
    noise_sd: float = 0.12
    # Optional promotion: item index in popularity order, window and demand multiplier
    promo_item_rank: int | None = 6
    promo_start_offset: int = 21
    promo_days: int = 7
    promo_uplift: float = 1.8
    # Payment method shares (an assumption, see docs/analytics.md) and minutes to settle
    payment_mix: tuple[tuple[str, float], ...] = (
        ("cash", 0.6),
        ("card", 0.2),
        ("wallet", 0.15),
        ("raast", 0.05),
    )
    settle_minutes: tuple[int, int] = (45, 75)

    def __post_init__(self) -> None:
        for method, share in self.payment_mix:
            if method not in PAYMENT_METHODS or share < 0:
                raise ValueError(f"Bad payment_mix entry {(method, share)!r}")
        if sum(share for _, share in self.payment_mix) <= 0:
            raise ValueError("payment_mix shares must sum to more than 0")
        lo, hi = self.settle_minutes
        if not 0 <= lo <= hi:
            raise ValueError(f"Bad settle_minutes {self.settle_minutes!r}")

    @classmethod
    def from_profile(cls, profile: dict) -> SimAssumptions:
        """Assumptions from a venue profile (a seed `simulation` block); lists become tuples.

        Per-item `weights` / `option_weights` are ignored here; any other unknown key raises.
        """
        values = {k: v for k, v in profile.items() if k not in PROFILE_DATA_KEYS}
        unknown = set(values) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown simulation keys: {sorted(unknown)}")
        for k, v in values.items():
            if isinstance(v, list):
                values[k] = tuple(tuple(x) if isinstance(x, list) else x for x in v)
        return cls(**values)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimItem:
    id: uuid.UUID
    weight: float = 1.0
    # (option id, weight) in menu order; an item with options always gets one of them
    options: tuple[tuple[uuid.UUID, float], ...] = ()


LineKey = tuple[uuid.UUID, uuid.UUID | None]  # (menu item id, option id)


@dataclass
class SimOrder:
    placed_at: datetime  # UTC
    lines: dict[LineKey, int] = field(default_factory=dict)
    payment_method: str = "cash"
    settle_after: int = 0  # minutes from placement to bill settlement


def popularity_ranking(items: list[SimItem]) -> list[uuid.UUID]:
    """Item ids by descending weight (rank 0 = most popular), ties broken by id."""
    return [i.id for i in sorted(items, key=lambda i: (-i.weight, i.id))]


def _probabilities(weights: list[float]) -> np.ndarray:
    w = np.asarray(weights, dtype=float)
    if (w < 0).any() or w.sum() <= 0:
        raise ValueError(f"Weights must be >= 0 with a positive sum: {weights!r}")
    return w / w.sum()


def promo_window(a: SimAssumptions, start: date) -> tuple[date, date] | None:
    """Inclusive promotion date range, or None when no promotion is configured."""
    if a.promo_item_rank is None or a.promo_days <= 0:
        return None
    first = start + timedelta(days=a.promo_start_offset)
    return first, first + timedelta(days=a.promo_days - 1)


def generate_orders(
    items: list[SimItem],
    start: date,
    a: SimAssumptions,
    tz: ZoneInfo,
) -> list[SimOrder]:
    """Generate `a.days` days of orders starting at local date `start`. Pure and seeded.

    Arrival times, party sizes and dishes come from `default_rng(seed)`; option, payment and
    settle-time draws come from a second generator seeded `[seed, 1]`, so options or the
    payment mix never shift the order stream itself.
    """
    if not items:
        return []
    rng = np.random.default_rng(a.seed)
    extra = np.random.default_rng([a.seed, 1])
    by_id = {i.id: i for i in items}
    ranked = [by_id[i] for i in popularity_ranking(items)]
    base_weights = _probabilities([i.weight for i in ranked])
    option_p = {i.id: _probabilities([w for _, w in i.options]) for i in ranked if i.options}
    sizes = np.arange(1, len(a.party_size_weights) + 1)
    size_p = np.asarray(a.party_size_weights) / sum(a.party_size_weights)
    methods = [m for m, _ in a.payment_mix]
    method_p = _probabilities([share for _, share in a.payment_mix])
    settle_lo, settle_hi = a.settle_minutes
    window = promo_window(a, start)
    promo_idx = min(a.promo_item_rank, len(ranked) - 1) if window else None

    orders: list[SimOrder] = []
    for d in range(a.days):
        day = start + timedelta(days=d)
        weights = base_weights.copy()
        if window and window[0] <= day <= window[1]:
            weights[promo_idx] *= a.promo_uplift
        p = weights / weights.sum()
        day_factor = float(np.exp(rng.normal(0.0, a.noise_sd)))

        for daypart in DAYPARTS:
            rate = (a.lunch_rate if daypart == "lunch" else a.dinner_rate)[day.weekday()]
            h0, h1 = a.lunch_hours if daypart == "lunch" else a.dinner_hours
            for _ in range(int(rng.poisson(rate * day_factor))):
                minute = int(rng.integers(0, (h1 - h0) * 60))
                local = datetime.combine(day, time(h0), tzinfo=tz) + timedelta(minutes=minute)
                party = int(rng.choice(sizes, p=size_p))
                n_dishes = max(party, int(rng.poisson(a.dishes_per_guest * party)))
                order = SimOrder(placed_at=local.astimezone(UTC))
                for idx in rng.choice(len(ranked), size=n_dishes, p=p):
                    item = ranked[int(idx)]
                    option_id = None
                    if item.options:
                        pick = int(extra.choice(len(item.options), p=option_p[item.id]))
                        option_id = item.options[pick][0]
                    key = (item.id, option_id)
                    order.lines[key] = min(20, order.lines.get(key, 0) + 1)
                order.payment_method = methods[int(extra.choice(len(methods), p=method_p))]
                order.settle_after = int(extra.integers(settle_lo, settle_hi + 1))
                orders.append(order)
    return orders


def sim_items(restaurant: Restaurant, items: list[MenuItem]) -> list[SimItem]:
    """SimItems from menu items (options eager-loaded) and the venue profile's weights.

    Weights are keyed by seed item key; an item without a weight gets 1, and option weights
    that do not match the item's current options (count) fall back to equal weights.
    """
    profile = (restaurant.onboarding or {}).get("simulation", {})

    def item_id(key: str) -> uuid.UUID:
        return uuid.uuid5(SEED_ITEM_NAMESPACE, f"{restaurant.slug}:{key}")

    weights = {item_id(k): float(w) for k, w in profile.get("weights", {}).items()}
    option_weights = {item_id(k): ws for k, ws in profile.get("option_weights", {}).items()}
    out = []
    for item in items:
        ow = option_weights.get(item.id)
        if ow is None or len(ow) != len(item.options):
            ow = [1.0] * len(item.options)
        out.append(
            SimItem(
                id=item.id,
                weight=weights.get(item.id, 1.0),
                options=tuple((o.id, float(w)) for o, w in zip(item.options, ow, strict=True)),
            )
        )
    return out


async def clear_simulated(db: AsyncSession, restaurant_id: uuid.UUID) -> None:
    """Delete previously simulated orders (items cascade), their bills and sessions, promo events
    and the restaurant's stored forecasts (they were fitted on the data being replaced)."""
    sess_ids = list(
        (
            await db.execute(
                select(Order.guest_session_id)
                .where(Order.restaurant_id == restaurant_id, Order.source == "simulated")
                .distinct()
            )
        ).scalars()
    )
    await db.execute(
        delete(Order).where(Order.restaurant_id == restaurant_id, Order.source == "simulated")
    )
    await db.execute(
        delete(Bill).where(Bill.restaurant_id == restaurant_id, Bill.source == "simulated")
    )
    if sess_ids:
        # Only sessions left without any order: a session that also holds a live order stays.
        await db.execute(
            delete(GuestSession).where(
                GuestSession.id.in_(sess_ids),
                ~exists().where(Order.guest_session_id == GuestSession.id),
            )
        )
    await db.execute(
        delete(AuditLog).where(
            AuditLog.restaurant_id == restaurant_id,
            AuditLog.event_type == PROMOTION_EVENT,
            AuditLog.payload["source"].astext == "simulated",
        )
    )
    await db.execute(delete(ForecastRun).where(ForecastRun.restaurant_id == restaurant_id))


def _simulated_bill(
    restaurant: Restaurant,
    so: SimOrder,
    subtotal: Decimal,
    tz: ZoneInfo,
    rates: tuple[TaxRate, ...],
) -> Bill | None:
    """A settled simulated bill for one party, or None when no tax rate is in force then
    (no jurisdiction, or a date before the first configured rate)."""
    settled_at = so.placed_at + timedelta(minutes=so.settle_after)
    try:
        rate, tax = tax_for(
            restaurant.tax_jurisdiction or "",
            so.payment_method,
            settled_at.astimezone(tz).date(),
            subtotal,
            rates,
        )
    except TaxRateError:
        return None
    tax = tax.quantize(CENTS)
    return Bill(
        id=uuid.uuid4(),
        restaurant_id=restaurant.id,
        table_id=None,
        bill_no=None,
        status="settled",
        source="simulated",
        payment_method=so.payment_method,
        subtotal=subtotal,
        tax_jurisdiction=restaurant.tax_jurisdiction,
        tax_rate=rate,
        tax_amount=tax,
        total=subtotal + tax,
        opened_at=so.placed_at,
        settled_at=settled_at,
        created_at=so.placed_at,
    )


async def persist_simulation(
    db: AsyncSession,
    restaurant: Restaurant,
    a: SimAssumptions,
    today: date | None = None,
) -> dict:
    """Replace this restaurant's simulated orders and bills with a fresh seeded run ending
    yesterday. Each simulated order is one party with its own settled bill.

    Does not commit; the caller owns the transaction. Concurrent runs for the same restaurant
    are serialized by a row lock held until that transaction ends, so the second run replaces
    the first instead of adding to it. FOR NO KEY UPDATE does not block live order inserts.
    """
    await db.execute(
        select(Restaurant.id).where(Restaurant.id == restaurant.id).with_for_update(key_share=True)
    )
    tz = ZoneInfo(restaurant.timezone)
    today = today or datetime.now(tz).date()
    start = today - timedelta(days=a.days)

    await clear_simulated(db, restaurant.id)

    items = list(
        (
            await db.execute(
                select(MenuItem)
                .options(selectinload(MenuItem.translations), selectinload(MenuItem.options))
                .where(
                    MenuItem.restaurant_id == restaurant.id,
                    MenuItem.deleted_at.is_(None),
                    MenuItem.available.is_(True),
                )
            )
        ).scalars()
    )
    by_id = {i.id: i for i in items}
    options = {o.id: o for i in items for o in i.options}
    simulated_items = sim_items(restaurant, items)
    sim_orders = generate_orders(simulated_items, start, a, tz)

    # One synthetic, already-expired session holds all simulated orders (no guest data).
    session = GuestSession(
        id=uuid.uuid4(),
        restaurant_id=restaurant.id,
        language=restaurant.default_language,
        expires_at=datetime.now(UTC),
    )
    db.add(session)
    await db.flush()

    # Loaded once, outside the per-bill try: a missing or invalid tax file must raise.
    rates = default_rates()
    orders: list[Order] = []
    bills: list[Bill] = []
    for n, so in enumerate(sim_orders):
        lines = sorted(so.lines.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))
        snaps = [
            snapshot_order_item(
                by_id[item_id],
                quantity=qty,
                notes=None,
                guest_language=restaurant.default_language,
                default_language=restaurant.default_language,
                guest_allergens_to_avoid=[],
                option=options[option_id] if option_id else None,
            )
            for (item_id, option_id), qty in lines
        ]
        canonical = json.dumps(
            [[str(i), str(o) if o else None, q] for (i, o), q in lines], separators=(",", ":")
        )
        total = sum((line_total(s) for s in snaps), Decimal("0.00"))
        bill = _simulated_bill(restaurant, so, total, tz, rates)
        if bill is not None:
            bills.append(bill)
        orders.append(
            Order(
                guest_session_id=session.id,
                restaurant_id=restaurant.id,
                status="bumped",
                source="simulated",
                total=total,
                bill_id=bill.id if bill else None,
                idempotency_key=f"sim:{a.seed}:{n}",
                payload_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                placed_at=so.placed_at,
                bumped_at=so.placed_at + timedelta(minutes=12),
                created_at=so.placed_at,
                items=snaps,
            )
        )
    # Bills first: orders reference them and there is no ORM relationship to order the inserts.
    db.add_all(bills)
    await db.flush()
    db.add_all(orders)

    window = promo_window(a, start)
    if window and items:
        ranked = popularity_ranking(simulated_items)
        promo_item = ranked[min(a.promo_item_rank, len(ranked) - 1)]
        db.add(
            AuditLog(
                restaurant_id=restaurant.id,
                event_type=PROMOTION_EVENT,
                actor="simulator",
                payload={
                    "source": "simulated",
                    "menu_item_id": str(promo_item),
                    "start_date": window[0].isoformat(),
                    "end_date": window[1].isoformat(),
                },
            )
        )

    db.add(
        AuditLog(
            restaurant_id=restaurant.id,
            event_type="demo_orders_simulated",
            actor="simulator",
            payload={
                "orders": len(sim_orders),
                "bills": len(bills),
                "assumptions": a.to_dict(),
            },
        )
    )
    await db.flush()
    return {
        "orders_created": len(sim_orders),
        "bills_created": len(bills),
        "start_date": start.isoformat(),
        "end_date": (today - timedelta(days=1)).isoformat(),
        "assumptions": a.to_dict(),
    }
