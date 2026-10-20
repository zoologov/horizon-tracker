"""Tests for the run window and the run / retry / skip decision."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.domain.calendar import VerdictSource, WorkingDayVerdict
from horizon_tracker.domain.schedule import (
    Decision,
    RetryPolicy,
    RunKind,
    Window,
    decide,
)

CHECKIN_WINDOW = Window(start=time(7, 55), end=time(8, 0))
POLICY = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=30))
WORKING = WorkingDayVerdict(is_working=True, source=VerdictSource.CALENDAR)
HOLIDAY = WorkingDayVerdict(is_working=False, source=VerdictSource.CALENDAR)
FALLBACK_WEEKEND = WorkingDayVerdict(is_working=False, source=VerdictSource.WEEKDAY_FALLBACK)
FALLBACK_WEEKDAY = WorkingDayVerdict(is_working=True, source=VerdictSource.WEEKDAY_FALLBACK)


def at(hour: int, minute: int, second: int = 0, microsecond: int = 0) -> datetime:
    return datetime(2026, 10, 21, hour, minute, second, microsecond)


# --- Window ------------------------------------------------------------------


def test_window_rejects_an_end_before_its_start() -> None:
    with pytest.raises(ValueError, match="start"):
        Window(start=time(8, 0), end=time(7, 55))


def test_window_rejects_an_empty_span() -> None:
    with pytest.raises(ValueError, match="start"):
        Window(start=time(8, 0), end=time(8, 0))


@pytest.mark.parametrize(
    ("moment", "inside"),
    [
        (time(7, 54, 59), False),
        (time(7, 55, 0), True),
        (time(7, 57, 30), True),
        (time(8, 0, 0), True),
        (time(8, 0, 0, 1), False),
        (time(8, 0, 1), False),
    ],
)
def test_window_contains_both_of_its_ends(moment: time, inside: bool) -> None:
    assert CHECKIN_WINDOW.contains(moment) is inside


# --- RetryPolicy -------------------------------------------------------------


def test_retry_policy_needs_at_least_one_attempt() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0, backoff=timedelta(seconds=30))


def test_retry_policy_accepts_a_single_attempt() -> None:
    assert RetryPolicy(max_attempts=1, backoff=timedelta(0)).max_attempts == 1


def test_retry_policy_rejects_a_negative_backoff() -> None:
    with pytest.raises(ValueError, match="backoff"):
        RetryPolicy(max_attempts=3, backoff=timedelta(seconds=-1))


# --- RunKind -----------------------------------------------------------------


def test_run_kinds_are_named_after_the_cli_commands() -> None:
    assert [kind.value for kind in RunKind] == ["checkin", "checkout"]


# --- decide: window boundaries -------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(7, 54, 59), Decision.SKIP_EARLY),
        (at(7, 55, 0), Decision.RUN),
        (at(8, 0, 0), Decision.RUN),
        (at(8, 0, 1), Decision.SKIP_LATE),
        (at(11, 0), Decision.SKIP_LATE),
    ],
)
def test_first_attempt_runs_only_inside_the_window(now: datetime, expected: Decision) -> None:
    assert decide(now, CHECKIN_WINDOW, WORKING, attempt=1, policy=POLICY) is expected


def test_a_fraction_of_a_second_past_the_end_is_late() -> None:
    now = at(8, 0, 0, 500_000)

    assert decide(now, CHECKIN_WINDOW, WORKING, attempt=1, policy=POLICY) is Decision.SKIP_LATE


def test_window_is_read_on_the_wall_time_the_clock_hands_in() -> None:
    moscow_now = datetime(2026, 10, 21, 7, 56, tzinfo=ZoneInfo("Europe/Moscow"))

    assert decide(moscow_now, CHECKIN_WINDOW, WORKING, attempt=1, policy=POLICY) is Decision.RUN


# --- decide: attempts ----------------------------------------------------------


@pytest.mark.parametrize("attempt", [2, 3])
def test_a_later_attempt_inside_the_window_is_a_retry(attempt: int) -> None:
    decision = decide(at(7, 57), CHECKIN_WINDOW, WORKING, attempt=attempt, policy=POLICY)

    assert decision is Decision.RETRY


def test_attempts_beyond_the_policy_give_up() -> None:
    decision = decide(at(7, 57), CHECKIN_WINDOW, WORKING, attempt=4, policy=POLICY)

    assert decision is Decision.GIVE_UP


def test_a_retry_after_the_window_closed_is_late() -> None:
    decision = decide(at(8, 0, 1), CHECKIN_WINDOW, WORKING, attempt=2, policy=POLICY)

    assert decision is Decision.SKIP_LATE


def test_exhausted_attempts_give_up_even_after_the_window_closed() -> None:
    decision = decide(at(8, 1), CHECKIN_WINDOW, WORKING, attempt=4, policy=POLICY)

    assert decision is Decision.GIVE_UP


def test_a_single_attempt_policy_never_retries() -> None:
    single = RetryPolicy(max_attempts=1, backoff=timedelta(0))

    assert decide(at(7, 56), CHECKIN_WINDOW, WORKING, attempt=1, policy=single) is Decision.RUN
    assert decide(at(7, 56), CHECKIN_WINDOW, WORKING, attempt=2, policy=single) is Decision.GIVE_UP


@pytest.mark.parametrize("attempt", [0, -1])
def test_attempts_are_counted_from_one(attempt: int) -> None:
    with pytest.raises(ValueError, match="attempt"):
        decide(at(7, 56), CHECKIN_WINDOW, WORKING, attempt=attempt, policy=POLICY)


# --- decide: calendar verdict --------------------------------------------------


def test_a_holiday_is_skipped_inside_the_window() -> None:
    decision = decide(at(7, 55), CHECKIN_WINDOW, HOLIDAY, attempt=1, policy=POLICY)

    assert decision is Decision.SKIP_NON_WORKING_DAY


def test_a_holiday_is_reported_as_such_even_outside_the_window() -> None:
    decision = decide(at(11, 0), CHECKIN_WINDOW, HOLIDAY, attempt=1, policy=POLICY)

    assert decision is Decision.SKIP_NON_WORKING_DAY


def test_a_fallback_weekend_is_skipped() -> None:
    decision = decide(at(7, 55), CHECKIN_WINDOW, FALLBACK_WEEKEND, attempt=1, policy=POLICY)

    assert decision is Decision.SKIP_NON_WORKING_DAY


def test_a_fallback_weekday_runs() -> None:
    decision = decide(at(7, 55), CHECKIN_WINDOW, FALLBACK_WEEKDAY, attempt=1, policy=POLICY)

    assert decision is Decision.RUN
