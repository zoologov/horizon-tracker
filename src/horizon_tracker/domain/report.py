"""The run report as a value, and the notification text rendered from it in a language.

A report carries no free text at all: the outcome and the reason come from closed
vocabularies, the time is a ``datetime``, the planned moment a ``time``, and the
screenshot is a path the notifier attaches beside the text. There is no field a
password could travel in, so the rendered message cannot leak one -- and the report
refuses a value of the wrong type at construction rather than trusting the caller.

The words of the text come from the message catalogue (``domain.messages``) in the
language the caller names; this module only decides which lines a report has. A skip for
the day itself (a non-working day, an absence) states no time: nothing was going to run.
"""

# beadloom:domain=domain

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from horizon_tracker.domain.absence import Absence, AbsenceKind
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.messages import Language, text
from horizon_tracker.domain.schedule import RunKind


class Outcome(StrEnum):
    """How a run ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Reason(StrEnum):
    """Why a run failed or was skipped; a closed vocabulary, never an exception message."""

    NON_WORKING_DAY = "non_working_day"
    TOO_EARLY = "too_early"
    WINDOW_MISSED = "window_missed"
    ALREADY_LOGGED_OFF = "already_logged_off"
    PORTAL_UNREACHABLE = "portal_unreachable"
    LOGIN_REJECTED = "login_rejected"
    DESKTOP_NOT_FOUND = "desktop_not_found"
    DESKTOP_DID_NOT_OPEN = "desktop_did_not_open"
    LOGOFF_NOT_CONFIRMED = "logoff_not_confirmed"
    UNEXPECTED = "unexpected"
    ON_VACATION = "on_vacation"
    ON_SICK_LEAVE = "on_sick_leave"
    ON_DAY_OFF = "on_day_off"


ABSENCE_REASONS: Final[Mapping[AbsenceKind, Reason]] = MappingProxyType(
    {
        AbsenceKind.VACATION: Reason.ON_VACATION,
        AbsenceKind.SICK_LEAVE: Reason.ON_SICK_LEAVE,
        AbsenceKind.DAY_OFF: Reason.ON_DAY_OFF,
    }
)

# A skip for the day itself, not for the moment the run started: its notice has no time line.
_DAY_LEVEL_REASONS = frozenset({Reason.NON_WORKING_DAY, *ABSENCE_REASONS.values()})

# The calendar line of a --force run, which asks no calendar and so has no VerdictSource.
_NOT_ASKED = "not_asked"

_TIME_FORMAT = "%d.%m.%Y %H:%M:%S %Z"
_PLANNED_FORMAT = "%H:%M"
_DAY_FORMAT = "%d.%m"  # an absence's days: the year is the reader's, not the notice's
_SPAN_DASH = "\u2013"  # an en dash between the first and the last day, as in 03.11–14.11


def absence_reason(kind: AbsenceKind) -> Reason:
    """The reason a run on a day of an absence of ``kind`` is skipped with."""
    return ABSENCE_REASONS[kind]


def _require(value: object, expected: type | tuple[type, ...], field: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"RunReport.{field} has the wrong type: {type(value).__name__}")


@dataclass(frozen=True)
class RunReport:
    """What one run did, when, on whose working-day verdict, and why if it did not succeed.

    ``verdict_source`` is ``None`` when the calendar was not asked (a ``--force`` run).
    ``screenshot`` is sent as an attachment and never appears in the text.
    ``planned_at`` is the drawn moment the run was due at, local wall time (set whether or
    not the run reached its window); ``None`` when there was none (a ``--force`` run).
    ``absence`` is the absence a skip was for, set with an absence reason and only then;
    such a skip asked no calendar, so its ``verdict_source`` is ``None``.
    """

    kind: RunKind
    outcome: Outcome
    at: datetime
    verdict_source: VerdictSource | None
    reason: Reason | None = None
    screenshot: Path | None = None
    planned_at: time | None = None
    absence: Absence | None = None

    def __post_init__(self) -> None:
        _require(self.kind, RunKind, "kind")
        _require(self.outcome, Outcome, "outcome")
        _require(self.at, datetime, "at")
        _require(self.verdict_source, (VerdictSource, type(None)), "verdict_source")
        _require(self.reason, (Reason, type(None)), "reason")
        _require(self.screenshot, (Path, type(None)), "screenshot")
        _require(self.planned_at, (time, type(None)), "planned_at")
        _require(self.absence, (Absence, type(None)), "absence")
        if self.at.utcoffset() is None:
            raise ValueError("RunReport.at must carry a time zone")
        if (self.outcome is Outcome.SUCCEEDED) != (self.reason is None):
            raise ValueError("RunReport.reason is required for a failure or a skip, and only then")
        if (self.absence is None) == (self.reason in ABSENCE_REASONS.values()):
            raise ValueError("RunReport.absence is required for an absence reason, and only then")
        if self.absence is not None:
            self._check_absence(self.absence)

    def _check_absence(self, absence: Absence) -> None:
        if self.reason is not absence_reason(absence.kind):
            raise ValueError("RunReport.reason does not name the kind of its absence")
        if self.outcome is not Outcome.SKIPPED:
            raise ValueError("RunReport.outcome of an absence must be skipped")
        if self.verdict_source is not None:
            raise ValueError(
                "RunReport.verdict_source of an absence must be None: no calendar is asked"
            )

    @property
    def is_day_level_skip(self) -> bool:
        """Whether the run was skipped for the day itself: a non-working day or an absence."""
        return self.outcome is Outcome.SKIPPED and self.reason in _DAY_LEVEL_REASONS


def render(report: RunReport, language: Language) -> str:
    """The notification text for one run in ``language``: headline, time, calendar, reason.

    A day-level skip has no time line, and an absence skip no calendar line either: the
    calendar was not asked. Every word comes from the message catalogue; only the formatted
    times and days are the report's own, so a field could not carry a password into the
    text even if it held one.
    """
    lines = [text(f"report.{report.kind}.{report.outcome}", language)]
    if not report.is_day_level_skip:
        lines.append(_time_line(report, language))
    if report.absence is None:
        source = report.verdict_source or _NOT_ASKED
        lines.append(text(f"report.calendar.{source}", language))
    if report.reason is not None:
        lines.append(_reason_line(report.reason, report.absence, language))
    return "\n".join(lines)


def _time_line(report: RunReport, language: Language) -> str:
    at = report.at.strftime(_TIME_FORMAT)
    if report.planned_at is None:
        return text("report.time", language, at=at)
    planned = report.planned_at.strftime(_PLANNED_FORMAT)
    return text("report.time_planned", language, at=at, planned=planned)


def _reason_line(reason: Reason, absence: Absence | None, language: Language) -> str:
    said = text(f"reason.{reason}", language)
    if absence is None:
        return text("report.reason", language, reason=said)
    return text("report.reason_span", language, reason=said, span=_span(absence))


def _span(absence: Absence) -> str:
    first = absence.first_day.strftime(_DAY_FORMAT)
    if absence.last_day == absence.first_day:
        return first
    return f"{first}{_SPAN_DASH}{absence.last_day.strftime(_DAY_FORMAT)}"
