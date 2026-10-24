"""Sales analytics from order_item snapshots. SQL aggregates plus pure post-processing; no LLM.

All dates and hours are in the restaurant's local timezone. Cancelled orders are excluded.
Daypart: local hour < 18 is lunch (daytime), otherwise dinner (evening).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import text

from src.services.tax import TaxRateError, payment_class, tax_for

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.restaurant import Restaurant

LUNCH_END_HOUR = 18
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
        "revenue": round(revenue, 2),
        "aov": round(revenue / orders, 2) if orders else 0.0,
        "contribution_margin": round(margin, 2),
        "margin_pct": round(100 * margin / revenue, 1) if revenue else 0.0,
    }


def row_key(item_id: str, option_id: str | None) -> str:
    """Menu-engineering row id: the item id, plus the option id for a portion/size row."""
    return item_id if option_id is None else f"{item_id}:{option_id}"


async def daily_item_sales(db: AsyncSession, w: Window) -> list[dict]:
    """Units, revenue and cost per (item, option) per local day per daypart."""
    rows = await db.execute(
        text(
            f"SELECT oi.menu_item_id, oi.option_id, max(oi.option_label), "
            f"CAST({_LOCAL} AS date) AS d, "
            f"CASE WHEN extract(hour FROM {_LOCAL}) < {LUNCH_END_HOUR} "
            "THEN 'lunch' ELSE 'dinner' END AS daypart, "
            "sum(oi.quantity), sum(oi.quantity * oi.unit_price), "
            "sum(oi.quantity * oi.unit_cost) "
            f"FROM orders o JOIN order_item oi ON oi.order_id = o.id WHERE {_SCOPE} "
            "GROUP BY 1, 2, 4, 5 ORDER BY 4, 1, 2, 5"
        ),
        w.params(),
    )
    return [
        {
            "item_id": str(item_id),
            "option_id": str(option_id) if option_id else None,
            "option_label": label,
            "date": d,
            "daypart": daypart,
            "units": int(units),
            "revenue": float(revenue),
            "cost": float(cost),
        }
        for item_id, option_id, label, d, daypart, units, revenue, cost in rows.all()
    ]


_SHARE = Decimal("0.0001")
_CENTS = Decimal("0.01")


async def payment_mix(db: AsyncSession, w: Window, restaurant: Restaurant) -> dict:
    """Bills settled in the window (live and simulated, like orders) by payment class.

    Revenue is the pre-tax subtotal. digital_tax_saving = sum over digital bills of
    (tax at the standard rate in force on the settle date - tax actually charged).
    """
    rows = await db.execute(
        text(
            "SELECT b.payment_method, b.subtotal, b.tax_rate, b.tax_amount, b.tax_jurisdiction, "
            "CAST(b.settled_at AT TIME ZONE :tz AS date) FROM bills b "
            "WHERE b.restaurant_id = :rid AND b.status = 'settled' "
            "AND b.settled_at >= :start AND b.settled_at < :end"
        ),
        w.params(),
    )
    bills = {"standard": 0, "digital": 0}
    revenue = {"standard": Decimal(0), "digital": Decimal(0)}
    tax_by_rate: dict[Decimal, Decimal] = {}
    saving = Decimal(0)
    for method, subtotal, rate, tax, jur, settled in rows.all():
        cls = payment_class(method)
        bills[cls] += 1
        revenue[cls] += subtotal
        tax_by_rate[rate] = tax_by_rate.get(rate, Decimal(0)) + tax
        if cls == "digital":
            try:
                _, cash_tax = tax_for(
                    jur or restaurant.tax_jurisdiction or "", "cash", settled, subtotal
                )
            except TaxRateError:
                continue  # no standard rate on file for that date: no saving to claim
            saving += cash_tax - tax
    total = revenue["standard"] + revenue["digital"]
    return {
        "bills": bills,
        "revenue_share": {
            c: float((v / total).quantize(_SHARE)) if total else 0.0 for c, v in revenue.items()
        },
        "tax_by_rate": [
            {"rate": r.normalize(), "tax": t.quantize(_CENTS)}
            for r, t in sorted(tax_by_rate.items())
        ],
        "digital_tax_saving": saving.quantize(_CENTS),
    }


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
            "avg_revenue_per_day": round(float(rev) / days, 2),
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
    """Per (item, option) row: units, revenue, contribution, unit margin and weekly units."""
    out: dict[str, dict] = {}
    for r in daily:
        option_id = r.get("option_id")
        t = out.setdefault(
            row_key(r["item_id"], option_id),
            {
                "item_id": r["item_id"],
                "option_id": option_id,
                "option_label": r.get("option_label"),
                "units": 0,
                "revenue": 0.0,
                "cost": 0.0,
            },
        )
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
        return {}, {"median_units": 0, "median_unit_margin": 0.0}
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
    return classes, {"median_units": med_units, "median_unit_margin": round(med_margin, 2)}
