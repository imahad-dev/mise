"""Daily service report: pure aggregation over one day's recorded sitting and order timestamps.

Scope (the router selects the rows): sittings of one restaurant that closed on the chosen local
day. `settled`/`cancelled` closes are tables served; `staff_closed`/`idle_timeout` closes are
only counted (closed without a bill) and kept out of every average. Simulated sittings are
counted apart and kept out of everything else.

Stage waits (averages over the served sittings that have both timestamps):
- first_order: sitting opened -> its earliest order placed.
- approval: that first order placed -> its `order_approved` audit time.
- kitchen: per order that reached the kitchen and was bumped, bumped_at minus the time the
  kitchen first saw it (approval time when it waited for approval, else placement).
- bill: bill requested -> settled.

Hours are local hours of opening. Red alerts replay services/floor.py THRESHOLDS per sitting
(every closed sitting, served or not); a wait that never ended runs to its end: the voiding of
the order, else the sitting's close. The order-no-bump clock starts at placement, as the
Floor tile's "ordered" clock does.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from src.services.floor import THRESHOLDS

if TYPE_CHECKING:
    from datetime import datetime, timedelta

SERVED = ("settled", "cancelled")
STAGES = ("first_order", "approval", "kitchen", "bill")
ALERTS = ("seated_no_order", "approval_needed", "order_no_bump", "bill_not_settled")
MIN_SITTINGS_FOR_SLOWEST_HOUR = 2


@dataclass(frozen=True)
class OrderRecord:
    placed_at: datetime
    approved_at: datetime | None  # the order_approved audit time; None if it never waited
    bumped_at: datetime | None
    voided_at: datetime | None
    on_bill: bool  # reached the kitchen (pending orders are never on a bill)


@dataclass(frozen=True)
class SittingRecord:
    opened_at: datetime
    closed_at: datetime
    close_reason: str
    orders: tuple[OrderRecord, ...]
    bill_requested_at: datetime | None
    settled_at: datetime | None
    simulated: bool


@dataclass(frozen=True)
class SlowestHour:
    hour: int
    average_table_seconds: int
    slowest_stage: str | None


@dataclass(frozen=True)
class ServiceReport:
    tables_served: int
    closed_without_bill: int
    simulated_sittings: int
    average_table_seconds: int | None
    average_wait_seconds: dict[str, int | None]
    busiest_hour: int | None
    slowest_hour: SlowestHour | None
    alerts: dict[str, int]


def _avg(values: list[timedelta]) -> int | None:
    if not values:
        return None
    return round(sum(v.total_seconds() for v in values) / len(values))


def _first(s: SittingRecord) -> OrderRecord | None:
    return min(s.orders, key=lambda o: o.placed_at, default=None)


def _stage_waits(sittings: list[SittingRecord]) -> dict[str, list[timedelta]]:
    waits: dict[str, list[timedelta]] = {k: [] for k in STAGES}
    for s in sittings:
        first = _first(s)
        if first is not None:
            waits["first_order"].append(first.placed_at - s.opened_at)
            if first.approved_at is not None:
                waits["approval"].append(first.approved_at - first.placed_at)
        for o in s.orders:
            if o.on_bill and o.bumped_at is not None:
                waits["kitchen"].append(o.bumped_at - (o.approved_at or o.placed_at))
        if s.bill_requested_at is not None and s.settled_at is not None:
            waits["bill"].append(s.settled_at - s.bill_requested_at)
    return waits


def _red(state: str, start: datetime, end: datetime) -> bool:
    return end - start >= THRESHOLDS[state][1]


def _alerts(s: SittingRecord) -> set[str]:
    out = set()
    first = _first(s)
    if _red("seated", s.opened_at, first.placed_at if first else s.closed_at):
        out.add("seated_no_order")
    if first is not None and _red(
        "approval_needed",
        first.placed_at,
        first.approved_at or first.voided_at or s.closed_at,
    ):
        out.add("approval_needed")
    if any(
        _red("ordered", o.placed_at, o.bumped_at or o.voided_at or s.closed_at)
        for o in s.orders
        if o.on_bill
    ):
        out.add("order_no_bump")
    if s.bill_requested_at is not None and _red(
        "paying", s.bill_requested_at, s.settled_at or s.closed_at
    ):
        out.add("bill_not_settled")
    return out


def build_report(sittings: list[SittingRecord], tz: str) -> ServiceReport:
    zone = ZoneInfo(tz)
    live = [s for s in sittings if not s.simulated]
    served = [s for s in live if s.close_reason in SERVED]

    by_hour: dict[int, list[SittingRecord]] = defaultdict(list)
    for s in served:
        by_hour[s.opened_at.astimezone(zone).hour].append(s)
    busiest = min(by_hour, key=lambda h: (-len(by_hour[h]), h), default=None)

    slowest = None
    eligible = {h: g for h, g in by_hour.items() if len(g) >= MIN_SITTINGS_FOR_SLOWEST_HOUR}
    if eligible:
        hour_avg = {h: _avg([s.closed_at - s.opened_at for s in g]) for h, g in eligible.items()}
        hour = min(hour_avg, key=lambda h: (-hour_avg[h], h))
        stage_avg = {k: _avg(v) for k, v in _stage_waits(eligible[hour]).items() if v}
        slowest = SlowestHour(
            hour=hour,
            average_table_seconds=hour_avg[hour],
            slowest_stage=max(stage_avg, key=stage_avg.get, default=None),
        )

    alerts = dict.fromkeys(ALERTS, 0)
    for s in live:
        for a in _alerts(s):
            alerts[a] += 1

    return ServiceReport(
        tables_served=len(served),
        closed_without_bill=len(live) - len(served),
        simulated_sittings=len(sittings) - len(live),
        average_table_seconds=_avg([s.closed_at - s.opened_at for s in served]),
        average_wait_seconds={k: _avg(v) for k, v in _stage_waits(served).items()},
        busiest_hour=busiest,
        slowest_hour=slowest,
        alerts=alerts,
    )


_STAGE_WORDS = {
    "first_order": "to order",
    "approval": "for order approval",
    "kitchen": "for the kitchen",
    "bill": "to settle the bill",
}


def _minutes(seconds: int | None) -> int | None:
    return None if seconds is None else round(seconds / 60)


def _clock(hour: int | None) -> str | None:
    return None if hour is None else f"{hour:02d}:00"


def summary_facts(report: ServiceReport, day: str) -> dict:
    """The only facts the model sees: report numbers in whole minutes, no tables or guests."""
    slow = report.slowest_hour
    return {
        "day": day,
        "tables_served": report.tables_served,
        "closed_without_bill": report.closed_without_bill,
        "average_table_minutes": _minutes(report.average_table_seconds),
        "average_wait_minutes": {
            _STAGE_WORDS[k]: _minutes(v) for k, v in report.average_wait_seconds.items()
        },
        "busiest_hour": _clock(report.busiest_hour),
        "slowest_hour": _clock(slow.hour if slow else None),
        "slowest_hour_waiting_most": (
            _STAGE_WORDS[slow.slowest_stage] if slow and slow.slowest_stage else None
        ),
        "red_alerts": report.alerts,
        "red_alerts_total": sum(report.alerts.values()),
    }


def template_summary(f: dict) -> str:
    """One sentence from the facts only; used when the model is unavailable or rejected."""
    if not f["tables_served"]:
        return f"No tables were served on {f['day']}."
    n = f["tables_served"]
    text = (
        f"On {f['day']}, {n} {'table was' if n == 1 else 'tables were'} served, averaging "
        f"{f['average_table_minutes']} minutes per table"
    )
    if f["busiest_hour"]:
        text += f", busiest at {f['busiest_hour']}"
    if f["slowest_hour"]:
        text += f", slowest at {f['slowest_hour']}"
        if f["slowest_hour_waiting_most"]:
            text += f" with guests waiting longest {f['slowest_hour_waiting_most']}"
    alerts = f["red_alerts_total"]
    return text + f", with {alerts} red {'alert' if alerts == 1 else 'alerts'}."
