"""The run report as a value, and the notification text rendered from it.

A report carries no free text at all: the outcome and the reason come from closed
vocabularies, the time is a ``datetime`` and the screenshot is a path the notifier
attaches beside the text. There is no field a password could travel in, so the
rendered message cannot leak one -- and the report refuses a value of the wrong
type at construction rather than trusting the caller.
"""

# beadloom:domain=domain

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.schedule import RunKind


class Outcome(StrEnum):
    """How a run ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Reason(StrEnum):
    """Why a run failed or was skipped; a closed vocabulary, never an exception message."""

    NON_WORKING_DAY = "non_working_day"
    WINDOW_MISSED = "window_missed"
    ALREADY_LOGGED_OFF = "already_logged_off"
    PORTAL_UNREACHABLE = "portal_unreachable"
    LOGIN_REJECTED = "login_rejected"
    DESKTOP_NOT_FOUND = "desktop_not_found"
    DESKTOP_DID_NOT_OPEN = "desktop_did_not_open"
    LOGOFF_NOT_CONFIRMED = "logoff_not_confirmed"
    UNEXPECTED = "unexpected"


_KIND_TEXT = {RunKind.CHECKIN: "Вход", RunKind.CHECKOUT: "Выход"}

_OUTCOME_TEXT = {
    Outcome.SUCCEEDED: "выполнен",
    Outcome.FAILED: "не удался",
    Outcome.SKIPPED: "пропущен",
}

_SOURCE_TEXT = {
    VerdictSource.CALENDAR: "производственный календарь isdayoff.ru",
    VerdictSource.WEEKDAY_FALLBACK: "недоступен, решило правило пн-пт",
    None: "не спрашивали, ручной прогон --force",
}

_REASON_TEXT = {
    Reason.NON_WORKING_DAY: "выходной",
    Reason.WINDOW_MISSED: "прогон начался после своего окна",
    Reason.ALREADY_LOGGED_OFF: "сессии на столе уже нет, выходить не из чего",
    Reason.PORTAL_UNREACHABLE: "портал Horizon недоступен",
    Reason.LOGIN_REJECTED: "портал отклонил вход",
    Reason.DESKTOP_NOT_FOUND: "рабочий стол не найден среди доступных",
    Reason.DESKTOP_DID_NOT_OPEN: "рабочий стол не открылся",
    Reason.LOGOFF_NOT_CONFIRMED: "выход из Windows не подтвердился",
    Reason.UNEXPECTED: "непредвиденная ошибка, подробности в журнале",
}

_TIME_FORMAT = "%d.%m.%Y %H:%M:%S %Z"


def _require(value: object, expected: type | tuple[type, ...], field: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"RunReport.{field} has the wrong type: {type(value).__name__}")


@dataclass(frozen=True)
class RunReport:
    """What one run did, when, on whose working-day verdict, and why if it did not succeed.

    ``verdict_source`` is ``None`` when the calendar was not asked (a ``--force`` run).
    ``screenshot`` is sent as an attachment and never appears in the text.
    """

    kind: RunKind
    outcome: Outcome
    at: datetime
    verdict_source: VerdictSource | None
    reason: Reason | None = None
    screenshot: Path | None = None

    def __post_init__(self) -> None:
        _require(self.kind, RunKind, "kind")
        _require(self.outcome, Outcome, "outcome")
        _require(self.at, datetime, "at")
        _require(self.verdict_source, (VerdictSource, type(None)), "verdict_source")
        _require(self.reason, (Reason, type(None)), "reason")
        _require(self.screenshot, (Path, type(None)), "screenshot")
        if self.at.utcoffset() is None:
            raise ValueError("RunReport.at must carry a time zone")
        if (self.outcome is Outcome.SUCCEEDED) != (self.reason is None):
            raise ValueError("RunReport.reason is required for a failure or a skip, and only then")


def render(report: RunReport) -> str:
    """The notification text for one run: headline, time, calendar source, reason."""
    lines = [
        f"{_KIND_TEXT[report.kind]} {_OUTCOME_TEXT[report.outcome]}",
        f"Время: {report.at.strftime(_TIME_FORMAT)}",
        f"Календарь: {_SOURCE_TEXT[report.verdict_source]}",
    ]
    if report.reason is not None:
        lines.append(f"Причина: {_REASON_TEXT[report.reason]}")
    return "\n".join(lines)
