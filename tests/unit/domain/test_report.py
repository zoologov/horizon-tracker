"""Unit tests for the run report value and the notification text rendered from it."""

import dataclasses
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.report import Outcome, Reason, RunReport, render
from horizon_tracker.domain.schedule import RunKind

MOSCOW = ZoneInfo("Europe/Moscow")
MORNING = datetime(2026, 10, 20, 7, 56, 12, tzinfo=MOSCOW)
PASSWORD = "S3cr3t-Pa55w0rd!"

SUCCESS = RunReport(
    kind=RunKind.CHECKIN,
    outcome=Outcome.SUCCEEDED,
    at=MORNING,
    verdict_source=VerdictSource.CALENDAR,
)


def _failure(reason: Reason, screenshot: Path | None = None) -> RunReport:
    return dataclasses.replace(
        SUCCESS, outcome=Outcome.FAILED, reason=reason, screenshot=screenshot
    )


# --- the text -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "outcome", "reason", "headline"),
    [
        (RunKind.CHECKIN, Outcome.SUCCEEDED, None, "Вход выполнен"),
        (RunKind.CHECKOUT, Outcome.SUCCEEDED, None, "Выход выполнен"),
        (RunKind.CHECKIN, Outcome.FAILED, Reason.LOGIN_REJECTED, "Вход не удался"),
        (RunKind.CHECKOUT, Outcome.SKIPPED, Reason.ALREADY_LOGGED_OFF, "Выход пропущен"),
    ],
)
def test_render_opens_with_the_kind_and_the_outcome(
    kind: RunKind, outcome: Outcome, reason: Reason | None, headline: str
) -> None:
    report = dataclasses.replace(SUCCESS, kind=kind, outcome=outcome, reason=reason)

    assert render(report).splitlines()[0] == headline


def test_render_states_the_time_in_the_reports_own_time_zone() -> None:
    assert "Время: 20.10.2026 07:56:12 MSK" in render(SUCCESS).splitlines()


@pytest.mark.parametrize(
    ("source", "line"),
    [
        (VerdictSource.CALENDAR, "Календарь: производственный календарь isdayoff.ru"),
        (VerdictSource.WEEKDAY_FALLBACK, "Календарь: недоступен, решило правило пн-пт"),
        (None, "Календарь: не спрашивали, ручной прогон --force"),
    ],
)
def test_render_names_which_rule_decided_the_working_day(
    source: VerdictSource | None, line: str
) -> None:
    report = dataclasses.replace(SUCCESS, verdict_source=source)

    assert line in render(report).splitlines()


def test_a_success_carries_no_reason_line() -> None:
    assert not any(line.startswith("Причина:") for line in render(SUCCESS).splitlines())


def test_a_holiday_skip_says_it_is_a_day_off() -> None:
    report = dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.NON_WORKING_DAY)

    assert "Причина: выходной" in render(report).splitlines()


@pytest.mark.parametrize("reason", list(Reason))
def test_every_reason_renders_its_own_non_empty_line(reason: Reason) -> None:
    lines = [line for line in render(_failure(reason)).splitlines() if line.startswith("Причина:")]

    assert len(lines) == 1
    assert lines[0].removeprefix("Причина:").strip()


def test_every_reason_reads_differently() -> None:
    texts = {render(_failure(reason)) for reason in Reason}

    assert len(texts) == len(Reason)


# --- the value: well-formed by construction -------------------------------------


def test_report_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        SUCCESS.outcome = Outcome.FAILED  # type: ignore[misc]  # asserting the frozen dataclass rejects it


def test_report_keeps_the_screenshot_for_the_notifier() -> None:
    shot = Path("/var/lib/horizon/shots/checkin.png")

    assert _failure(Reason.DESKTOP_DID_NOT_OPEN, shot).screenshot == shot


def test_report_refuses_a_time_without_a_time_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        dataclasses.replace(SUCCESS, at=MORNING.replace(tzinfo=None))


def test_a_success_refuses_a_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        dataclasses.replace(SUCCESS, reason=Reason.UNEXPECTED)


@pytest.mark.parametrize("outcome", [Outcome.FAILED, Outcome.SKIPPED])
def test_a_failure_or_a_skip_requires_a_reason(outcome: Outcome) -> None:
    with pytest.raises(ValueError, match="reason"):
        dataclasses.replace(SUCCESS, outcome=outcome)


def test_report_refuses_free_text_as_a_reason() -> None:
    with pytest.raises(TypeError, match="reason"):
        _failure("login failed for user with password hunter2")  # type: ignore[arg-type]  # the runtime guard under test


# --- the password never reaches the notification ----------------------------------


def _with_field(field: str, value: object) -> RunReport | None:
    """The base failure report with one field replaced, or None when the report refuses it.

    A refusal must not echo the refused value either: its message goes to the journal.
    """
    try:
        # Deliberately ill-typed values: the runtime guard of the report is what is under test.
        return dataclasses.replace(_failure(Reason.LOGIN_REJECTED), **{field: value})  # type: ignore[arg-type]
    except (TypeError, ValueError) as refusal:
        assert PASSWORD not in str(refusal)
        return None


@pytest.mark.parametrize("field", [field.name for field in dataclasses.fields(RunReport)])
@pytest.mark.parametrize(
    "carrier",
    [PASSWORD, Path(PASSWORD), Path("/var/lib/horizon") / f"{PASSWORD}.png"],
    ids=["str", "bare-path", "nested-path"],
)
def test_a_password_passed_through_any_field_never_reaches_the_text(
    field: str, carrier: object
) -> None:
    report = _with_field(field, carrier)

    if report is not None:
        assert PASSWORD not in render(report)


def test_the_screenshot_travels_beside_the_text_not_inside_it() -> None:
    report = _failure(Reason.DESKTOP_DID_NOT_OPEN, Path(f"/var/lib/horizon/{PASSWORD}.png"))

    assert report.screenshot is not None
    assert PASSWORD not in render(report)
