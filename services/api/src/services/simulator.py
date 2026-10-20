"""Synthetic order generator for demos and tests. Every order it writes has source='simulated'.

Assumptions are documented in docs/analytics.md and exposed as `SimAssumptions` fields.
Generation (`generate_orders`) is pure and seeded; `persist_simulation` writes the result
through the same snapshot code as live orders.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.models.audit import AuditLog
from src.models.forecast import ForecastRun
from src.models.menu import MenuItem
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.order_snapshot import line_total, snapshot_order_item

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DAYPARTS = ("lunch", "dinner")
PROMOTION_EVENT = "promotion"


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
    # Zipf exponent for item popularity by rank
    zipf_s: float = 1.0
    # Day-level multiplicative noise: exp(N(0, noise_sd))
    noise_sd: float = 0.12
    # Optional promotion: item index in popularity order, window and demand multiplier
    promo_item_rank: int | None = 6
    promo_start_offset: int = 21
    promo_days: int = 7
    promo_uplift: float = 1.8

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SimOrder:
    placed_at: datetime  # UTC
    lines: dict[uuid.UUID, int] = field(default_factory=dict)


def popularity_ranking(item_ids: list[uuid.UUID], seed: int) -> list[uuid.UUID]:
    """Deterministic popularity order (rank 0 = most popular) from a seeded permutation."""
    rng = np.random.default_rng(seed)
    ordered = sorted(item_ids)
    return [ordered[i] for i in rng.permutation(len(ordered))]


def promo_window(a: SimAssumptions, start: date) -> tuple[date, date] | None:
    """Inclusive promotion date range, or None when no promotion is configured."""
    if a.promo_item_rank is None or a.promo_days <= 0:
        return None
    first = start + timedelta(days=a.promo_start_offset)
    return first, first + timedelta(days=a.promo_days - 1)


def generate_orders(
    item_ids: list[uuid.UUID],
    start: date,
    a: SimAssumptions,
    tz: ZoneInfo,
) -> list[SimOrder]:
    """Generate `a.days` days of orders starting at local date `start`. Pure and seeded."""
    if not item_ids:
        return []
    rng = np.random.default_rng(a.seed)
    ranked = popularity_ranking(item_ids, a.seed)
    base_weights = 1.0 / np.arange(1, len(ranked) + 1) ** a.zipf_s
    sizes = np.arange(1, len(a.party_size_weights) + 1)
    size_p = np.asarray(a.party_size_weights) / sum(a.party_size_weights)
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
                    item_id = ranked[int(idx)]
                    order.lines[item_id] = min(20, order.lines.get(item_id, 0) + 1)
                orders.append(order)
    return orders


async def clear_simulated(db: AsyncSession, restaurant_id: uuid.UUID) -> None:
    """Delete previously simulated orders (items cascade), their sessions, promo events and the
    restaurant's stored forecasts (they were fitted on the data being replaced)."""
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
    if sess_ids:
        await db.execute(delete(GuestSession).where(GuestSession.id.in_(sess_ids)))
    await db.execute(
        delete(AuditLog).where(
            AuditLog.restaurant_id == restaurant_id,
            AuditLog.event_type == PROMOTION_EVENT,
            AuditLog.payload["source"].astext == "simulated",
        )
    )
    await db.execute(delete(ForecastRun).where(ForecastRun.restaurant_id == restaurant_id))


async def persist_simulation(
    db: AsyncSession,
    restaurant: Restaurant,
    a: SimAssumptions,
    today: date | None = None,
) -> dict:
    """Replace this restaurant's simulated orders with a fresh seeded run ending yesterday.

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
                .options(selectinload(MenuItem.translations))
                .where(
                    MenuItem.restaurant_id == restaurant.id,
                    MenuItem.deleted_at.is_(None),
                    MenuItem.available.is_(True),
                )
            )
        ).scalars()
    )
    by_id = {i.id: i for i in items}
    sim_orders = generate_orders(list(by_id), start, a, tz)

    # One synthetic, already-expired session holds all simulated orders (no guest data).
    session = GuestSession(
        id=uuid.uuid4(),
        restaurant_id=restaurant.id,
        language=restaurant.default_language,
        expires_at=datetime.now(UTC),
    )
    db.add(session)
    await db.flush()

    for n, so in enumerate(sim_orders):
        snaps = [
            snapshot_order_item(
                by_id[item_id],
                quantity=qty,
                notes=None,
                guest_language=restaurant.default_language,
                default_language=restaurant.default_language,
                guest_allergens_to_avoid=[],
            )
            for item_id, qty in sorted(so.lines.items())
        ]
        canonical = json.dumps([[str(k), v] for k, v in sorted(so.lines.items())])
        db.add(
            Order(
                guest_session_id=session.id,
                restaurant_id=restaurant.id,
                status="bumped",
                source="simulated",
                total=sum((line_total(s) for s in snaps), Decimal("0.00")),
                idempotency_key=f"sim:{a.seed}:{n}",
                payload_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                placed_at=so.placed_at,
                bumped_at=so.placed_at + timedelta(minutes=12),
                created_at=so.placed_at,
                items=snaps,
            )
        )

    window = promo_window(a, start)
    if window and items:
        ranked = popularity_ranking(list(by_id), a.seed)
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
            payload={"orders": len(sim_orders), "assumptions": a.to_dict()},
        )
    )
    await db.flush()
    return {
        "orders_created": len(sim_orders),
        "start_date": start.isoformat(),
        "end_date": (today - timedelta(days=1)).isoformat(),
        "assumptions": a.to_dict(),
    }
