"""Tests for the working-day verdict: calendar answer first, weekday rule as fallback."""

from datetime import date

import pytest

from horizon_tracker.domain.calendar import (
    VerdictSource,
    WorkingDayVerdict,
    resolve,
    weekday_rule,
)

MONDAY = date(2026, 10, 19)
WEDNESDAY = date(2026, 10, 21)
FRIDAY = date(2026, 10, 23)
SATURDAY = date(2026, 10, 24)
SUNDAY = date(2026, 10, 25)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (MONDAY, True),
        (date(2026, 10, 20), True),
        (WEDNESDAY, True),
        (date(2026, 10, 22), True),
        (FRIDAY, True),
        (SATURDAY, False),
        (SUNDAY, False),
    ],
)
def test_weekday_rule_counts_monday_to_friday_as_working(day: date, expected: bool) -> None:
    assert weekday_rule(day) is expected


def test_calendar_holiday_on_a_weekday_is_not_a_working_day() -> None:
    verdict = resolve(False, WEDNESDAY)

    assert verdict == WorkingDayVerdict(is_working=False, source=VerdictSource.CALENDAR)


def test_calendar_working_saturday_overrides_the_weekday_rule() -> None:
    verdict = resolve(True, SATURDAY)

    assert verdict == WorkingDayVerdict(is_working=True, source=VerdictSource.CALENDAR)


def test_calendar_working_weekday_is_a_working_day() -> None:
    assert resolve(True, MONDAY) == WorkingDayVerdict(
        is_working=True, source=VerdictSource.CALENDAR
    )


def test_calendar_weekend_is_not_a_working_day() -> None:
    assert resolve(False, SUNDAY) == WorkingDayVerdict(
        is_working=False, source=VerdictSource.CALENDAR
    )


def test_unreachable_calendar_falls_back_to_weekday_rule_on_a_weekday() -> None:
    verdict = resolve(None, FRIDAY)

    assert verdict == WorkingDayVerdict(is_working=True, source=VerdictSource.WEEKDAY_FALLBACK)


def test_unreachable_calendar_falls_back_to_weekday_rule_on_a_weekend() -> None:
    verdict = resolve(None, SATURDAY)

    assert verdict == WorkingDayVerdict(is_working=False, source=VerdictSource.WEEKDAY_FALLBACK)


def test_verdict_is_immutable() -> None:
    verdict = resolve(True, MONDAY)

    with pytest.raises(AttributeError):
        verdict.is_working = False  # type: ignore[misc]  # asserting frozen dataclass rejects it
