"""Tests for services/sitting.py: pure idle/code logic, no DB."""

from datetime import UTC, datetime, timedelta

from src.services.sitting import IDLE_TIMEOUT, generate_code, is_idle

NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)


def test_not_idle_just_opened():
    assert is_idle(opened_at=NOW, last_activity_at=None, now=NOW) is False


def test_idle_after_90_minutes_of_silence():
    opened = NOW - timedelta(minutes=95)
    assert is_idle(opened_at=opened, last_activity_at=None, now=NOW) is True


def test_not_idle_with_recent_activity_even_if_opened_long_ago():
    opened = NOW - timedelta(hours=3)
    recent = NOW - timedelta(minutes=10)
    assert is_idle(opened_at=opened, last_activity_at=recent, now=NOW) is False


def test_idle_timeout_is_90_minutes():
    assert timedelta(minutes=90) == IDLE_TIMEOUT


def test_generate_code_is_four_digits():
    code = generate_code()
    assert len(code) == 4
    assert code.isdigit()
