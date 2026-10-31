"""Daily service report: pure functions over constructed sitting and order records."""

from datetime import UTC, datetime, timedelta

import pytest

from src.services.floor import THRESHOLDS
from src.services.narrative import numbers_grounded
from src.services.service_report import (
    OrderRecord,
    SittingRecord,
    build_report,
    summary_facts,
    template_summary,
)

TZ = "Asia/Karachi"  # UTC+5, no DST
T0 = datetime(2026, 10, 31, 7, 0, tzinfo=UTC)  # 12:00 local
M = timedelta(minutes=1)


def order(placed, approved=None, bumped=None, voided=None, on_bill=True) -> OrderRecord:
    return OrderRecord(
        placed_at=T0 + placed * M,
        approved_at=None if approved is None else T0 + approved * M,
        bumped_at=None if bumped is None else T0 + bumped * M,
        voided_at=None if voided is None else T0 + voided * M,
        on_bill=on_bill,
    )


def sitting(
    opened=0,
    closed=60,
    orders=(),
    requested=None,
    settled=None,
    reason="settled",
    simulated=False,
) -> SittingRecord:
    return SittingRecord(
        opened_at=T0 + opened * M,
        closed_at=T0 + closed * M,
        close_reason=reason,
        orders=tuple(orders),
        bill_requested_at=None if requested is None else T0 + requested * M,
        settled_at=None if settled is None else T0 + settled * M,
        simulated=simulated,
    )


def test_empty_day_is_zeros_and_nulls():
    r = build_report([], TZ)
    assert r.tables_served == 0 and r.closed_without_bill == 0 and r.simulated_sittings == 0
    assert r.average_table_seconds is None
    assert r.average_wait_seconds == {
        "first_order": None,
        "approval": None,
        "kitchen": None,
        "bill": None,
    }
    assert r.busiest_hour is None and r.slowest_hour is None
    assert r.alerts == {
        "seated_no_order": 0,
        "approval_needed": 0,
        "order_no_bump": 0,
        "bill_not_settled": 0,
    }


def test_tables_served_and_average_table_time():
    r = build_report([sitting(0, 40), sitting(60, 120, reason="cancelled")], TZ)
    assert r.tables_served == 2
    assert r.average_table_seconds == 50 * 60


def test_closed_without_bill_counted_but_kept_out_of_averages():
    r = build_report(
        [
            sitting(0, 40),
            sitting(0, 200, reason="staff_closed"),
            sitting(0, 90, reason="idle_timeout"),
        ],
        TZ,
    )
    assert r.tables_served == 1
    assert r.closed_without_bill == 2
    assert r.average_table_seconds == 40 * 60


def test_simulated_sittings_counted_separately():
    r = build_report([sitting(0, 40), sitting(0, 100, simulated=True)], TZ)
    assert r.tables_served == 1
    assert r.simulated_sittings == 1
    assert r.average_table_seconds == 40 * 60


def test_stage_waits():
    a = sitting(
        0,
        60,
        orders=[order(4, approved=5, bumped=15), order(20, bumped=30)],  # 2nd skipped approval
        requested=50,
        settled=52,
    )
    b = sitting(0, 60, orders=[order(6, approved=9, bumped=21)])  # no bill request
    r = build_report([a, b], TZ)
    w = r.average_wait_seconds
    assert w["first_order"] == 5 * 60  # (4 + 6) / 2
    assert w["approval"] == 2 * 60  # (1 + 3) / 2
    # Kitchen clock starts when the kitchen saw the order: approval, else placement.
    assert w["kitchen"] == 10 * 60 + 40  # (10 + 10 + 12) / 3 min
    assert w["bill"] == 2 * 60


def test_stage_skips_sittings_without_the_timestamps():
    pending_declined = order(3, voided=8, on_bill=False)  # never approved, never in the kitchen
    r = build_report([sitting(0, 30, orders=[pending_declined]), sitting(0, 30)], TZ)
    w = r.average_wait_seconds
    assert w["first_order"] == 3 * 60  # the empty sitting has no first order
    assert w["approval"] is None
    assert w["kitchen"] is None
    assert w["bill"] is None
    assert r.tables_served == 2


def test_first_order_is_the_earliest_placed_and_unbumped_orders_skip_kitchen():
    r = build_report([sitting(0, 60, orders=[order(10, bumped=None), order(7, approved=8)])], TZ)
    assert r.average_wait_seconds["first_order"] == 7 * 60
    assert r.average_wait_seconds["approval"] == 60
    assert r.average_wait_seconds["kitchen"] is None


def test_durations_are_integer_seconds():
    r = build_report([sitting(0, 1), sitting(0, 2)], TZ)
    assert r.average_table_seconds == 90
    r = build_report([sitting(0, 0), sitting(0, 0), sitting(0, 1)], TZ)
    assert r.average_table_seconds == 20


def test_hours_are_local_and_bucketed_by_opening():
    # T0 is 12:00 in Karachi; a sitting opened at 23:50 local the day before, closed after
    # midnight, buckets in hour 23.
    late = sitting(-12 * 60 - 10, -11 * 60 - 20)
    r = build_report(
        [sitting(0, 30), sitting(10, 50), sitting(65, 85), late],
        TZ,
    )
    assert r.busiest_hour == 12
    assert late.opened_at.hour == 18  # 18:50 UTC
    hours = build_report([late], TZ)
    assert hours.busiest_hour == 23


def test_busiest_hour_tie_goes_to_the_earlier_hour():
    r = build_report([sitting(60, 70), sitting(0, 10)], TZ)
    assert r.busiest_hour == 12


def test_slowest_hour_needs_two_sittings_and_names_the_worst_stage():
    noon = [
        sitting(0, 40, orders=[order(2, approved=3, bumped=10)]),
        sitting(5, 45, orders=[order(7, approved=8, bumped=15)]),
    ]
    one_pm = [
        sitting(60, 150, orders=[order(75, approved=76, bumped=80)], requested=90, settled=100),
        sitting(70, 140, orders=[order(85, approved=86, bumped=90)], requested=100, settled=130),
    ]
    lonely = sitting(120, 400)  # 14:00, longest of all but alone in its hour
    r = build_report([*noon, *one_pm, lonely], TZ)
    assert r.slowest_hour is not None
    assert r.slowest_hour.hour == 13
    assert r.slowest_hour.average_table_seconds == 80 * 60
    # 13:00 waits: first order 15, approval 1, kitchen 4, bill 20 minutes.
    assert r.slowest_hour.slowest_stage == "bill"


def test_slowest_hour_none_without_two_sittings_in_any_hour():
    r = build_report([sitting(0, 30), sitting(60, 90)], TZ)
    assert r.slowest_hour is None


def test_slowest_hour_stage_none_when_no_stage_data():
    r = build_report([sitting(0, 30), sitting(0, 50)], TZ)
    assert r.slowest_hour.hour == 12
    assert r.slowest_hour.slowest_stage is None


def _red(state: str) -> int:
    return int(THRESHOLDS[state][1].total_seconds() // 60)


def test_alert_replay_at_exact_red_thresholds():
    seated, approval, ordered, paying = (
        _red("seated"),
        _red("approval_needed"),
        _red("ordered"),
        _red("paying"),
    )
    at = sitting(
        0,
        200,
        orders=[order(seated, approved=seated + approval, bumped=seated + ordered)],
        requested=100,
        settled=100 + paying,
    )
    r = build_report([at], TZ)
    assert r.alerts == {
        "seated_no_order": 1,
        "approval_needed": 1,
        "order_no_bump": 1,
        "bill_not_settled": 1,
    }
    # One second under each threshold: no alert.
    s = timedelta(seconds=1)
    under = SittingRecord(
        opened_at=T0,
        closed_at=T0 + 200 * M,
        close_reason="settled",
        orders=(
            OrderRecord(
                placed_at=T0 + seated * M - s,
                approved_at=T0 + (seated + approval) * M - 2 * s,
                bumped_at=T0 + (seated + ordered) * M - 2 * s,
                voided_at=None,
                on_bill=True,
            ),
        ),
        bill_requested_at=T0 + 100 * M,
        settled_at=T0 + (100 + paying) * M - s,
        simulated=False,
    )
    assert build_report([under], TZ).alerts == {
        "seated_no_order": 0,
        "approval_needed": 0,
        "order_no_bump": 0,
        "bill_not_settled": 0,
    }


def test_alert_replay_runs_to_the_close_when_the_wait_never_ended():
    # Seated and never ordered until an idle close; a first order declined after a long wait;
    # an order never bumped; a bill requested and the table cancelled.
    idle = sitting(0, 90, reason="idle_timeout")
    declined = sitting(0, 30, orders=[order(1, voided=10, on_bill=False)], reason="staff_closed")
    unbumped = sitting(0, 40, orders=[order(1, approved=2)], requested=10, reason="cancelled")
    r = build_report([idle, declined, unbumped], TZ)
    assert r.alerts == {
        "seated_no_order": 1,
        "approval_needed": 1,
        "order_no_bump": 1,
        "bill_not_settled": 1,
    }


def test_order_no_bump_alert_counts_from_placement_like_the_floor_tile():
    # The tile's "ordered" clock is placed_at, so a slow approval pushes the order red sooner.
    ordered = _red("ordered")
    r = build_report([sitting(0, 120, orders=[order(1, approved=10, bumped=1 + ordered)])], TZ)
    assert r.alerts["order_no_bump"] == 1
    assert r.average_wait_seconds["kitchen"] == (ordered - 9) * 60


def test_alerts_count_sittings_not_orders_and_skip_simulated():
    ordered = _red("ordered")
    slow = [order(1, approved=2, bumped=1 + ordered), order(3, bumped=3 + ordered)]
    r = build_report(
        [sitting(0, 120, orders=slow), sitting(0, 120, orders=slow, simulated=True)], TZ
    )
    assert r.alerts["order_no_bump"] == 1


@pytest.mark.parametrize(
    "records",
    [
        [],
        [
            sitting(0, 47, orders=[order(4, approved=5, bumped=19)], requested=40, settled=46),
            sitting(3, 71, orders=[order(9, approved=13, bumped=30)], requested=60, settled=66),
            sitting(0, 9, reason="staff_closed"),
        ],
    ],
)
def test_template_summary_is_one_sentence_grounded_in_the_facts(records):
    facts = summary_facts(build_report(records, TZ), "2026-10-31")
    text = template_summary(facts)
    assert numbers_grounded(text, facts)
    assert text.count(".") <= 1 and text.endswith(".")


def test_summary_facts_carry_only_report_numbers():
    report = build_report(
        [
            sitting(0, 47, orders=[order(4, approved=5, bumped=19)], requested=40, settled=46),
            sitting(3, 71, orders=[order(9, approved=13, bumped=30)], requested=60, settled=66),
        ],
        TZ,
    )
    facts = summary_facts(report, "2026-10-31")
    assert facts["tables_served"] == 2
    assert facts["average_table_minutes"] == 58  # (47 + 68) / 2 = 57.5, rounded half to even
    assert facts["busiest_hour"] == "12:00"
    assert facts["slowest_hour"] == "12:00"
    assert set(facts) == {
        "day",
        "tables_served",
        "closed_without_bill",
        "average_table_minutes",
        "average_wait_minutes",
        "busiest_hour",
        "slowest_hour",
        "slowest_hour_waiting_most",
        "red_alerts",
        "red_alerts_total",
    }
