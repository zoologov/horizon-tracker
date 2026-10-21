"""The run report as a value, and the notification text rendered from it in a language.

A report carries no free text at all: the outcome and the reason come from closed
vocabularies, the time is a ``datetime``, the planned moment a ``time``, and the
screenshot is a path the notifier attaches beside the text. There is no field a
password could travel in, so the rendered message cannot leak one -- and the report
refuses a value of the wrong type at construction rather than trusting the caller.

The words of the text come from the message catalogue (``domain.messages``) in the
language the caller names; this module only decides which lines a report has.
"""

# beadloom:domain=domain

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from pathlib import Path

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


# The calendar line of a --force run, which asks no calendar and so has no VerdictSource.
_NOT_ASKED = "not_asked"

_TIME_FORMAT = "%d.%m.%Y %H:%M:%S %Z"
_PLANNED_FORMAT = "%H:%M"


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
    """

    kind: RunKind
    outcome: Outcome
    at: datetime
    verdict_source: VerdictSource | None
    reason: Reason | None = None
    screenshot: Path | None = None
    planned_at: time | None = None

    def __post_init__(self) -> None:
        _require(self.kind, RunKind, "kind")
        _require(self.outcome, Outcome, "outcome")
        _require(self.at, datetime, "at")
        _require(self.verdict_source, (VerdictSource, type(None)), "verdict_source")
        _require(self.reason, (Reason, type(None)), "reason")
        _require(self.screenshot, (Path, type(None)), "screenshot")
        _require(self.planned_at, (time, type(None)), "planned_at")
        if self.at.utcoffset() is None:
            raise ValueError("RunReport.at must carry a time zone")
        if (self.outcome is Outcome.SUCCEEDED) != (self.reason is None):
            raise ValueError("RunReport.reason is required for a failure or a skip, and only then")


def render(report: RunReport, language: Language) -> str:
    """The notification text for one run in ``language``: headline, time, calendar, reason.

    Every word comes from the message catalogue; only the two formatted times are the
    report's own, so a field could not carry a password into the text even if it held one.
    """
    source = report.verdict_source or _NOT_ASKED
    lines = [
        text(f"report.{report.kind}.{report.outcome}", language),
        _time_line(report, language),
        text("report.calendar", language, source=text(f"report.source.{source}", language)),
    ]
    if report.reason is not None:
        reason = text(f"reason.{report.reason}", language)
        lines.append(text("report.reason", language, reason=reason))
    return "\n".join(lines)


def _time_line(report: RunReport, language: Language) -> str:
    at = report.at.strftime(_TIME_FORMAT)
    if report.planned_at is None:
        return text("report.time", language, at=at)
    planned = report.planned_at.strftime(_PLANNED_FORMAT)
    return text("report.time_planned", language, at=at, planned=planned)
