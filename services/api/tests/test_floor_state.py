from datetime import UTC, datetime, timedelta

from src.services.floor import TableFacts, table_state

T0 = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)


def m(n):
    return T0 + timedelta(minutes=n)


def facts(**kw):
    base = dict(
        table_id="t",
        label="T1",
        kind="table",
        cleared_at=None,
        last_session_at=None,
        open_bill=False,
        paying_since=None,
        oldest_placed_at=None,
        has_active_orders=False,
        last_settled_at=None,
        last_cancelled_at=None,
        call_reason=None,
        call_since=None,
        running_total=None,
    )
    base.update(kw)
    return TableFacts(**base)


def test_free():
    assert table_state(facts(), m(0)).state == "free"


def test_seated_levels():
    f = facts(last_session_at=m(0))
    assert table_state(f, m(2)).level == "none"
    assert table_state(f, m(3)).level == "amber"
    assert table_state(f, m(5)).level == "red"
    assert table_state(f, m(5)).state == "seated"


def test_session_before_clear_is_free():
    assert table_state(facts(last_session_at=m(0), cleared_at=m(1)), m(10)).state == "free"


def test_after_settle_is_needs_clearing_not_seated():
    f = facts(last_session_at=m(0), last_settled_at=m(40))
    s = table_state(f, m(42))
    assert (s.state, s.level) == ("needs_clearing", "amber")
    assert table_state(f, m(45)).level == "red"


def test_new_guests_after_settle_are_seated():
    assert table_state(facts(last_settled_at=m(40), last_session_at=m(41)), m(41)).state == "seated"


def test_ordered_from_oldest_placed():
    f = facts(open_bill=True, has_active_orders=True, oldest_placed_at=m(0))
    assert table_state(f, m(12)).level == "amber"
    assert table_state(f, m(18)).level == "red"


def test_served_has_timer_only():
    s = table_state(facts(open_bill=True, has_active_orders=True), m(60))
    assert (s.state, s.level) == ("served", "none")


def test_paying_outranks_ordered():
    f = facts(open_bill=True, has_active_orders=True, oldest_placed_at=m(0), paying_since=m(10))
    s = table_state(f, m(13))
    assert (s.state, s.level) == ("paying", "amber")


def test_dessert_after_paying_is_ordered():
    f = facts(last_settled_at=m(30), open_bill=True, has_active_orders=True, oldest_placed_at=m(35))
    assert table_state(f, m(36)).state == "ordered"


def test_call_overrides_everything_and_is_red():
    f = facts(open_bill=True, paying_since=m(0), call_reason="water", call_since=m(1))
    s = table_state(f, m(1))
    assert (s.state, s.level, s.reason) == ("called", "red", "water")


def test_counter_tables_are_not_tiles():
    assert table_state(facts(kind="counter"), m(0)) is None


def test_open_bill_with_no_active_orders_falls_through_to_seated():
    f = facts(open_bill=True, has_active_orders=False, last_session_at=m(0))
    assert table_state(f, m(1)).state == "seated"


def test_open_bill_is_never_free_even_after_clear():
    f = facts(open_bill=True, has_active_orders=False, cleared_at=m(5), last_session_at=m(0))
    assert table_state(f, m(6)).state == "seated"


def test_paying_stays_paying_when_all_orders_voided():
    f = facts(open_bill=True, has_active_orders=False, paying_since=m(0))
    assert table_state(f, m(1)).state == "paying"


def test_paying_and_clearing_thresholds_are_inclusive():
    paying = facts(open_bill=True, has_active_orders=True, paying_since=m(0))
    assert [table_state(paying, m(n)).level for n in (2, 3, 5)] == ["none", "amber", "red"]
    clearing = facts(last_settled_at=m(0))
    assert [table_state(clearing, m(n)).level for n in (1, 2, 5)] == ["none", "amber", "red"]


def test_cancelled_bill_resets_like_a_settle():
    # Every order voided: the bill is cancelled and the party's seat is over.
    f = facts(last_session_at=m(0), last_cancelled_at=m(20))
    s = table_state(f, m(22))
    assert (s.state, s.since, s.level) == ("needs_clearing", m(20), "amber")


def test_clear_after_a_cancel_is_free_and_new_guests_are_seated():
    assert table_state(facts(last_cancelled_at=m(20), cleared_at=m(21)), m(30)).state == "free"
    assert table_state(facts(last_cancelled_at=m(20), last_session_at=m(25)), m(26)).state == (
        "seated"
    )


def test_needs_clearing_runs_from_the_later_of_settle_and_cancel():
    s = table_state(facts(last_settled_at=m(10), last_cancelled_at=m(30)), m(31))
    assert (s.state, s.since) == ("needs_clearing", m(30))
    s = table_state(facts(last_settled_at=m(30), last_cancelled_at=m(10)), m(31))
    assert (s.state, s.since) == ("needs_clearing", m(30))


def test_guests_waiting_badge_before_table_opened():
    f = facts(last_session_at=m(0), sitting_open=False)
    result = table_state(f, m(2))
    assert result.state == "seated"
    assert result.waiting_for_open is True
    assert result.level == "amber"  # guests_waiting: amber at 1, red at 3


def test_approval_needed_outranks_everything_and_times_from_pending_order():
    f = facts(
        last_session_at=m(-100),
        open_bill=True,
        sitting_open=True,
        approval_pending=m(0),
    )
    result = table_state(f, m(2))
    assert result.state == "approval_needed"
    assert result.level == "red"  # approval_needed: amber at 1, red at 2


def test_seated_timer_starts_from_sitting_open_not_last_session():
    f = facts(
        last_session_at=m(-60),  # long ago, irrelevant once a sitting is open
        open_bill=True,
        sitting_open=True,
        sitting_opened_at=m(0),
    )
    result = table_state(f, m(6))
    assert result.state == "seated"
    assert result.since == m(0)
    assert result.level == "red"  # seated: amber at 3, red at 5 -> 6 minutes since open


def test_an_open_table_nobody_has_scanned_is_seated_from_the_open():
    s = table_state(facts(sitting_open=True, sitting_opened_at=m(0)), m(4))
    assert (s.state, s.since, s.level, s.waiting_for_open) == ("seated", m(0), "amber", False)


def test_a_table_opened_after_a_settle_is_seated_not_needs_clearing():
    f = facts(
        last_session_at=m(0), last_settled_at=m(40), sitting_open=True, sitting_opened_at=m(41)
    )
    s = table_state(f, m(42))
    assert (s.state, s.since) == ("seated", m(41))


def test_a_closed_table_with_a_scan_after_the_reset_is_still_waiting_for_open():
    f = facts(last_session_at=m(5), reset_at=m(4), sitting_open=False)
    s = table_state(f, m(6))
    assert (s.state, s.waiting_for_open) == ("seated", True)
