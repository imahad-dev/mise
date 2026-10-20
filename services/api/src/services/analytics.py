"""Sales analytics from order_item snapshots. SQL aggregates plus pure post-processing; no LLM.

All dates and hours are in the restaurant's local timezone. Cancelled orders are excluded.
Daypart: local hour < 16 is lunch, otherwise dinner.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import text

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

LUNCH_END_HOUR = 16
MIN_PAIR_ORDERS = 5  # co-occurrences below this are too noisy to report

_LOCAL = "(o.placed_at AT TIME ZONE :tz)"
_SCOPE = (
    "o.restaurant_id = :rid AND o.status <> 'cancelled' "
    "AND o.placed_at >= :start AND o.placed_at < :end"
)


@dataclass(frozen=True)
class Window:
    restaurant_id: uuid.UUID
    tz: str
    start: date  # inclusive, local
    end: date  # exclusive, local

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def params(self) -> dict:
        zone = ZoneInfo(self.tz)
        return {
            "rid": self.restaurant_id,
            "tz": self.tz,
            "start": datetime.combine(self.start, time(0), tzinfo=zone).astimezone(UTC),
            "end": datetime.combine(self.end, time(0), tzinfo=zone).astimezone(UTC),
        }


async def order_counts_by_source(db: AsyncSession, w: Window) -> dict[str, int]:
    rows = await db.execute(
        text(f"SELECT o.source, count(*) FROM orders o WHERE {_SCOPE} GROUP BY o.source"),
        w.params(),
    )
    counts = {"live": 0, "simulated": 0}
    counts.update({src: int(n) for src, n in rows.all()})
    return counts


async def kpis(db: AsyncSession, w: Window) -> dict:
    """Revenue, orders, AOV and contribution margin from order_item snapshots."""
    row = (
        await db.execute(
            text(
                "SELECT count(DISTINCT o.id), "
                "coalesce(sum(oi.quantity * oi.unit_price), 0), "
                "coalesce(sum(oi.quantity * (oi.unit_price - oi.unit_cost)), 0) "
                f"FROM orders o JOIN order_item oi ON oi.order_id = o.id WHERE {_SCOPE}"
            ),
            w.params(),
        )
    ).one()
    orders, revenue, margin = int(row[0]), float(row[1]), float(row[2])
    return {
        "orders": orders,
        "revenue_eur": round(revenue, 2),
        "aov_eur": round(revenue / orders, 2) if orders else 0.0,
        "contribution_margin_eur": round(margin, 2),
        "margin_pct": round(100 * margin / revenue, 1) if revenue else 0.0,
    }


async def daily_item_sales(db: AsyncSession, w: Window) -> list[dict]:
    """Units, revenue and cost per item per local day per daypart."""
    rows = await db.execute(
        text(
            f"SELECT oi.menu_item_id, CAST({_LOCAL} AS date) AS d, "
            f"CASE WHEN extract(hour FROM {_LOCAL}) < {LUNCH_END_HOUR} "
            "THEN 'lunch' ELSE 'dinner' END AS daypart, "
            "sum(oi.quantity), sum(oi.quantity * oi.unit_price), "
            "sum(oi.quantity * oi.unit_cost) "
            f"FROM orders o JOIN order_item oi ON oi.order_id = o.id WHERE {_SCOPE} "
            "GROUP BY 1, 2, 3 ORDER BY 2, 1, 3"
        ),
        w.params(),
    )
    return [
        {
            "item_id": str(item_id),
            "date": d,
            "daypart": daypart,
            "units": int(units),
            "revenue": float(revenue),
            "cost": float(cost),
        }
        for item_id, d, daypart, units, revenue, cost in rows.all()
    ]


async def top_pairings(db: AsyncSession, w: Window, limit: int = 5) -> list[dict]:
    """Item pairs ordered together, ranked by lift = P(A and B) / (P(A) * P(B))."""
    rows = await db.execute(
        text(
            "WITH b AS (SELECT DISTINCT o.id AS order_id, oi.menu_item_id AS item "
            f"FROM orders o JOIN order_item oi ON oi.order_id = o.id WHERE {_SCOPE}), "
            "n AS (SELECT count(DISTINCT order_id)::float AS n FROM b), "
            "s AS (SELECT item, count(*) AS c FROM b GROUP BY item), "
            "p AS (SELECT x.item AS a, y.item AS b, count(*) AS c FROM b x "
            "JOIN b y ON x.order_id = y.order_id AND x.item < y.item GROUP BY 1, 2) "
            "SELECT p.a, p.b, p.c, p.c * n.n / (sa.c * sb.c) AS lift "
            "FROM p JOIN s sa ON sa.item = p.a JOIN s sb ON sb.item = p.b CROSS JOIN n "
            "WHERE p.c >= :min_c ORDER BY lift DESC, p.c DESC LIMIT :limit"
        ),
        {**w.params(), "min_c": MIN_PAIR_ORDERS, "limit": limit},
    )
    return [
        {"a": str(a), "b": str(b), "orders_together": int(c), "lift": round(float(lift), 2)}
        for a, b, c, lift in rows.all()
    ]


async def peak_hours(db: AsyncSession, w: Window, limit: int = 3) -> list[dict]:
    """Busiest local hours by average orders per day over the window."""
    rows = await db.execute(
        text(
            f"SELECT extract(hour FROM {_LOCAL})::int AS h, count(*), coalesce(sum(o.total), 0) "
            f"FROM orders o WHERE {_SCOPE} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT :limit"
        ),
        {**w.params(), "limit": limit},
    )
    days = max(w.days, 1)
    return [
        {
            "hour": int(h),
            "avg_orders_per_day": round(int(n) / days, 1),
            "avg_revenue_per_day_eur": round(float(rev) / days, 2),
        }
        for h, n, rev in rows.all()
    ]


async def promotions(db: AsyncSession, restaurant_id: uuid.UUID) -> list[tuple[str, date, date]]:
    """Promotion windows recorded as audit_log 'promotion' events (item_id, start, end)."""
    rows = await db.execute(
        text(
            "SELECT payload->>'menu_item_id', payload->>'start_date', payload->>'end_date' "
            "FROM audit_log WHERE restaurant_id = :rid AND event_type = 'promotion'"
        ),
        {"rid": restaurant_id},
    )
    return [
        (item, date.fromisoformat(s), date.fromisoformat(e))
        for item, s, e in rows.all()
        if item and s and e
    ]


def item_totals(daily: list[dict], weeks: float) -> dict[str, dict]:
    """Per item units, revenue, contribution, unit margin and weekly units."""
    out: dict[str, dict] = {}
    for r in daily:
        t = out.setdefault(r["item_id"], {"units": 0, "revenue": 0.0, "cost": 0.0})
        t["units"] += r["units"]
        t["revenue"] += r["revenue"]
        t["cost"] += r["cost"]
    for t in out.values():
        t["contribution"] = round(t["revenue"] - t["cost"], 2)
        t["unit_margin"] = round(t["contribution"] / t["units"], 2) if t["units"] else 0.0
        t["weekly_units"] = round(t["units"] / weeks, 2) if weeks else 0.0
        t["revenue"] = round(t["revenue"], 2)
        t["cost"] = round(t["cost"], 2)
    return out


def classify_menu(totals: dict[str, dict]) -> tuple[dict[str, str], dict]:
    """Menu-engineering class per item by median popularity (units) and median unit margin.

    star: high popularity, high margin; plowhorse: high popularity, low margin;
    puzzle: low popularity, high margin; dog: low on both. Values equal to the median
    count as high.
    """
    if not totals:
        return {}, {"median_units": 0, "median_unit_margin_eur": 0.0}
    med_units = statistics.median(t["units"] for t in totals.values())
    med_margin = statistics.median(t["unit_margin"] for t in totals.values())
    classes = {}
    for item_id, t in totals.items():
        popular = t["units"] >= med_units
        profitable = t["unit_margin"] >= med_margin
        classes[item_id] = (
            ("star" if profitable else "plowhorse")
            if popular
            else ("puzzle" if profitable else "dog")
        )
    return classes, {"median_units": med_units, "median_unit_margin_eur": round(med_margin, 2)}
