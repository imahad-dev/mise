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
