"""Floor view: one table's state from facts the system already records. Pure."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

State = Literal[
    "free",
    "seated",
    "ordered",
    "served",
    "paying",
    "needs_clearing",
    "called",
    "approval_needed",
]
Level = Literal["none", "amber", "red"]
MIN = timedelta(minutes=1)
# Research: docs/research/2026-10-25-floor-view-notes.md (greet ~1 min, entrée 10-15 min,
# turn within 2 min); seated red at 5 min follows the reel that inspired the feature.
THRESHOLDS: dict[str, tuple[timedelta, timedelta]] = {
    "seated": (3 * MIN, 5 * MIN),
    "ordered": (12 * MIN, 18 * MIN),
    "paying": (3 * MIN, 5 * MIN),
    "needs_clearing": (2 * MIN, 5 * MIN),
    "approval_needed": (1 * MIN, 2 * MIN),
    "guests_waiting": (1 * MIN, 3 * MIN),
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
    last_cancelled_at: datetime | None
    call_reason: str | None
    call_since: datetime | None
    running_total: Decimal | None
    # sitting_open defaults True (not False) so a caller/test that omits it keeps the pre-sitting
    # behaviour below unchanged — False means "known to be unopened", a fact only the router with
    # real sitting data should assert.
    sitting_open: bool = True
    sitting_opened_at: datetime | None = None
    approval_pending: datetime | None = None  # placed_at of the sitting's unapproved first order
    reset_at: datetime | None = None  # last clear, settle, cancel or closed table (any reason)


@dataclass(frozen=True)
class TileState:
    state: State
    since: datetime | None
    level: Level
    reason: str | None = None
    waiting_for_open: bool = False  # guests have scanned but no sitting is open yet


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
    if f.approval_pending is not None:
        return TileState(
            "approval_needed",
            f.approval_pending,
            _level("approval_needed", f.approval_pending, now),
        )
    if f.call_reason is not None:
        return TileState("called", f.call_since, "red", f.call_reason)
    if (
        not f.sitting_open
        and f.last_session_at is not None
        and not _after(
            max(
                (
                    t
                    for t in (f.last_settled_at, f.last_cancelled_at, f.cleared_at, f.reset_at)
                    if t is not None
                ),
                default=None,
            ),
            f.last_session_at,
        )
    ):
        # A guest has scanned (or ordering is otherwise expected) but staff haven't opened the
        # table yet, and nothing has reset that scan since.
        return TileState(
            "seated",
            f.last_session_at,
            _level("guests_waiting", f.last_session_at, now),
            waiting_for_open=True,
        )
    if f.open_bill:
        if f.paying_since is not None:
            return TileState("paying", f.paying_since, _level("paying", f.paying_since, now))
        if f.oldest_placed_at is not None:
            return TileState(
                "ordered", f.oldest_placed_at, _level("ordered", f.oldest_placed_at, now)
            )
        if f.has_active_orders:
            return TileState("served", None, "none")
    # A cancelled bill (every order voided) ends the party like a settle, as session_is_current.
    ended = max(
        (t for t in (f.last_settled_at, f.last_cancelled_at) if t is not None), default=None
    )
    reset = max((t for t in (f.cleared_at, ended, f.reset_at) if t is not None), default=None)
    # An open bill is never Free.
    if f.open_bill or _after(f.last_session_at, reset):
        seated_since = f.sitting_opened_at or f.last_session_at
        return TileState("seated", seated_since, _level("seated", seated_since, now))
    if _after(ended, f.cleared_at):
        return TileState("needs_clearing", ended, _level("needs_clearing", ended, now))
    return TileState("free", None, "none")


REASON_LABELS = {"help": "Need help", "water": "Water, please"}


def reason_label(reason: str | None, extra_label: str | None) -> str | None:
    if reason is None:
        return None
    return REASON_LABELS.get(reason) or extra_label or "Something else"
