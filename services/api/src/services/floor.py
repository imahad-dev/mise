"""Floor view: one table's state from facts the system already records. Pure."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

State = Literal["free", "seated", "ordered", "served", "paying", "needs_clearing", "called"]
Level = Literal["none", "amber", "red"]
MIN = timedelta(minutes=1)
# Research: docs/research/2026-10-25-floor-view-notes.md (greet ~1 min, entrée 10-15 min,
# turn within 2 min); seated red at 5 min follows the reel that inspired the feature.
THRESHOLDS: dict[str, tuple[timedelta, timedelta]] = {
    "seated": (3 * MIN, 5 * MIN),
    "ordered": (12 * MIN, 18 * MIN),
    "paying": (3 * MIN, 5 * MIN),
    "needs_clearing": (2 * MIN, 5 * MIN),
}


@dataclass(frozen=True)
class TableFacts:
    table_id: str
    label: str
    kind: str
    cleared_at: datetime | None
    last_session_at: datetime | None
    open_bill: bool
    paying_since: datetime | None
    oldest_placed_at: datetime | None
    has_active_orders: bool
    last_settled_at: datetime | None
    call_reason: str | None
    call_since: datetime | None
    running_total: object | None


@dataclass(frozen=True)
class TileState:
    state: State
    since: datetime | None
    level: Level
    reason: str | None = None


def _level(state: str, since: datetime | None, now: datetime) -> Level:
    if since is None or state not in THRESHOLDS:
        return "none"
    amber, red = THRESHOLDS[state]
    age = now - since
    return "red" if age >= red else "amber" if age >= amber else "none"


def _after(a: datetime | None, b: datetime | None) -> bool:
    return a is not None and (b is None or a > b)


def table_state(f: TableFacts, now: datetime) -> TileState | None:
    if f.kind != "table":
        return None
    if f.call_reason is not None:
        return TileState("called", f.call_since, "red", f.call_reason)
    if f.open_bill:
        if f.paying_since is not None:
            return TileState("paying", f.paying_since, _level("paying", f.paying_since, now))
        if f.oldest_placed_at is not None:
            return TileState(
                "ordered", f.oldest_placed_at, _level("ordered", f.oldest_placed_at, now)
            )
        if f.has_active_orders:
            return TileState("served", None, "none")
    reset = max((t for t in (f.cleared_at, f.last_settled_at) if t is not None), default=None)
    if _after(f.last_session_at, reset):
        return TileState("seated", f.last_session_at, _level("seated", f.last_session_at, now))
    if _after(f.last_settled_at, f.cleared_at):
        return TileState(
            "needs_clearing", f.last_settled_at, _level("needs_clearing", f.last_settled_at, now)
        )
    return TileState("free", None, "none")
