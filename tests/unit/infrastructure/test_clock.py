"""Tests for the system clock: aware time in the configured zone, and a real wait."""

import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.infrastructure.clock import SystemClock

MOSCOW = ZoneInfo("Europe/Moscow")
TOKYO = ZoneInfo("Asia/Tokyo")
TOLERANCE = timedelta(seconds=5)
SHORT_WAIT = 0.05


@pytest.mark.parametrize(("zone", "offset_hours"), [(MOSCOW, 3), (TOKYO, 9)])
def test_now_is_aware_and_in_the_configured_zone(zone: ZoneInfo, offset_hours: int) -> None:
    now = SystemClock(zone).now()

    assert now.tzinfo is zone
    assert now.utcoffset() == timedelta(hours=offset_hours)


def test_now_is_the_current_instant() -> None:
    before = datetime.now(UTC)
    now = SystemClock(MOSCOW).now()
    after = datetime.now(UTC)

    assert before <= now <= after


def test_two_zones_read_the_same_instant_as_different_wall_times() -> None:
    moscow = SystemClock(MOSCOW).now()
    tokyo = SystemClock(TOKYO).now()

    assert abs(tokyo - moscow) < TOLERANCE
    assert tokyo.replace(tzinfo=None) - moscow.replace(tzinfo=None) > timedelta(hours=5)


def test_sleep_waits_at_least_the_given_seconds() -> None:
    started = time.monotonic()

    SystemClock(MOSCOW).sleep(SHORT_WAIT)

    assert time.monotonic() - started >= SHORT_WAIT


def test_sleep_refuses_a_negative_wait() -> None:
    with pytest.raises(ValueError, match="negative"):
        SystemClock(MOSCOW).sleep(-1)
