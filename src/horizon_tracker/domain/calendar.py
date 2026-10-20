"""Decides whether a date is a working day: calendar answer first, Monday-Friday as fallback.

The production calendar (isdayoff.ru behind the ``WorkingDayCalendar`` port) answers
``True``/``False``, or ``None`` when it could not be reached. A ``None`` falls back to
the weekday rule, and the verdict names which of the two decided, so the notification
can say so.
"""
# beadloom:domain=domain

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

_FIRST_WEEKEND_DAY = 5  # date.weekday(): Monday is 0, Saturday is 5


class VerdictSource(StrEnum):
    """Which rule produced a working-day verdict."""

    CALENDAR = "calendar"
    WEEKDAY_FALLBACK = "weekday_fallback"


@dataclass(frozen=True)
class WorkingDayVerdict:
    """Whether a day is a working day, and which rule said so."""

    is_working: bool
    source: VerdictSource


def weekday_rule(day: date) -> bool:
    """Return ``True`` for Monday to Friday, the fallback when the calendar is unreachable."""
    return day.weekday() < _FIRST_WEEKEND_DAY


def resolve(calendar_answer: bool | None, day: date) -> WorkingDayVerdict:
    """Turn the calendar's answer for ``day`` into a verdict, falling back on ``None``."""
    if calendar_answer is None:
        return WorkingDayVerdict(weekday_rule(day), VerdictSource.WEEKDAY_FALLBACK)
    return WorkingDayVerdict(calendar_answer, VerdictSource.CALENDAR)
