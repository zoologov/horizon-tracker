"""Tests for the morning check-in: open, hold, disconnect, confirm, and one report."""

import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.checkin import MorningCheckin
from horizon_tracker.application.windowed_run import WindowedRun
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Outcome, Reason, RunReport, render
from horizon_tracker.domain.schedule import RetryPolicy, RunKind, Window
from horizon_tracker.domain.session import SessionState
from tests.support.fakes import FakeCalendar, FakeClock, FakeHorizonClient, FakeNotifier

MSK = ZoneInfo("Europe/Moscow")
WEDNESDAY = date(2026, 10, 21)
DESKTOP = "DEV desktop"
HOLD = timedelta(seconds=120)
BACKOFF = timedelta(seconds=20)
POLICY = RetryPolicy(max_attempts=3, backoff=BACKOFF)
SHOT = Path("/var/lib/horizon-tracker/shots/checkin.png")
PASSWORD = "Pa$$w0rd-never-shown"

ONE_CHECKIN = [
    "login",
    "open_desktop",
    "desktop_status",
    "disconnect",
    "login",
    "desktop_status",
]


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 21, hour, minute, second, tzinfo=MSK)


class Morning:
    """A morning check-in wired to fakes, the clock at ``start``."""

    def __init__(
        self,
        start: datetime | None = None,
        calendar_answer: bool | None = True,
        state: SessionState = SessionState.NO_SESSION,
    ) -> None:
        self.clock = FakeClock(at(7, 55) if start is None else start)
        self.calendar = FakeCalendar(calendar_answer)
        self.notifier = FakeNotifier()
        self.client = FakeHorizonClient(desktop=DESKTOP, state=state)
        runner = WindowedRun(
            calendar=self.calendar,
            clock=self.clock,
            notifier=self.notifier,
            window=Window(start=time(7, 55), end=time(8, 0)),
            policy=POLICY,
        )
        self.checkin = MorningCheckin(
            client=self.client, clock=self.clock, runner=runner, desktop=DESKTOP, hold=HOLD
        )

    def run(self, *, force: bool = False) -> RunReport:
        return self.checkin.run(force=force)

    @property
    def only_report(self) -> RunReport:
        assert len(self.notifier.sent) == 1, f"expected one notification, got {self.notifier.sent}"
        return self.notifier.sent[0]


# --- success -----------------------------------------------------------------------


def test_checkin_opens_the_desktop_holds_it_and_disconnects() -> None:
    morning = Morning()

    morning.run()

    assert morning.client.calls == ONE_CHECKIN
    assert morning.clock.sleeps == [HOLD.total_seconds()]
    assert morning.client.state is SessionState.DISCONNECTED


def test_checkin_never_logs_the_session_off() -> None:
    morning = Morning()

    morning.run()

    assert "log_off" not in morning.client.calls


def test_checkin_reports_success_once_with_the_time_the_desktop_opened() -> None:
    morning = Morning(start=at(7, 55, 10))

    report = morning.run()

    assert morning.only_report == report
    assert report.kind is RunKind.CHECKIN
    assert report.outcome is Outcome.SUCCEEDED
    assert report.at == at(7, 55, 10)
    assert report.verdict_source is VerdictSource.CALENDAR
    assert report.screenshot is None


def test_checkin_reattaches_to_a_session_left_disconnected() -> None:
    morning = Morning(state=SessionState.DISCONNECTED)

    assert morning.run().outcome is Outcome.SUCCEEDED


# --- what the broker shows decides, not what the client returned -------------------


def test_checkin_fails_when_the_session_did_not_survive_the_disconnect() -> None:
    morning = Morning()
    morning.client.disconnect_keeps_session = False

    report = morning.run()

    assert morning.client.calls == ONE_CHECKIN * POLICY.max_attempts
    assert morning.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.DESKTOP_DID_NOT_OPEN


def test_checkin_fails_when_the_broker_never_saw_the_desktop_connected() -> None:
    morning = Morning(state=SessionState.DISCONNECTED)
    morning.client.open_connects = False

    report = morning.run()

    assert morning.client.calls == ONE_CHECKIN * POLICY.max_attempts
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.DESKTOP_DID_NOT_OPEN


# --- retries -----------------------------------------------------------------------


def test_a_failed_open_is_retried_after_the_backoff_and_succeeds() -> None:
    morning = Morning()
    morning.client.fail_on("open_desktop", HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN, SHOT))

    report = morning.run()

    assert morning.clock.sleeps == [BACKOFF.total_seconds(), HOLD.total_seconds()]
    assert morning.only_report == report
    assert report.outcome is Outcome.SUCCEEDED


def test_a_failure_after_the_desktop_opened_still_disconnects_the_client() -> None:
    morning = Morning()
    morning.client.fail_on("desktop_status", HorizonClientError(Reason.UNEXPECTED), times=3)

    report = morning.run()

    assert morning.client.calls.count("disconnect") == POLICY.max_attempts
    assert morning.client.state is SessionState.DISCONNECTED
    assert report.outcome is Outcome.FAILED


def test_every_attempt_failing_reports_the_last_reason_and_screenshot() -> None:
    morning = Morning()
    morning.client.fail_on("login", HorizonClientError(Reason.PORTAL_UNREACHABLE), times=2)
    morning.client.fail_on("open_desktop", HorizonClientError(Reason.DESKTOP_NOT_FOUND, SHOT))

    report = morning.run()

    assert morning.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.DESKTOP_NOT_FOUND
    assert report.screenshot == SHOT


# --- skips -------------------------------------------------------------------------


def test_a_holiday_is_skipped_without_touching_the_portal() -> None:
    morning = Morning(calendar_answer=False)

    report = morning.run()

    assert morning.client.calls == []
    assert morning.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.NON_WORKING_DAY


def test_an_unreachable_calendar_on_a_weekday_checks_in_and_says_so() -> None:
    morning = Morning(calendar_answer=None)

    report = morning.run()

    assert morning.client.calls == ONE_CHECKIN
    assert report.outcome is Outcome.SUCCEEDED
    assert report.verdict_source is VerdictSource.WEEKDAY_FALLBACK


def test_a_late_start_is_skipped_without_touching_the_portal() -> None:
    morning = Morning(start=at(11, 0))

    report = morning.run()

    assert morning.client.calls == []
    assert morning.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.WINDOW_MISSED


def test_force_checks_in_outside_the_window_without_the_calendar() -> None:
    morning = Morning(start=at(11, 0), calendar_answer=False)

    report = morning.run(force=True)

    assert morning.calendar.asked == []
    assert morning.client.calls == ONE_CHECKIN
    assert report.outcome is Outcome.SUCCEEDED
    assert report.verdict_source is None


# --- the password ------------------------------------------------------------------


def test_a_password_in_an_adapter_error_reaches_neither_the_report_nor_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    morning = Morning()
    morning.client.fail_on("login", ValueError(f"typed {PASSWORD} into #password"), times=3)
    caplog.set_level(logging.DEBUG)

    report = morning.run()

    assert report.reason is Reason.UNEXPECTED
    assert PASSWORD not in render(report)
    assert PASSWORD not in repr(report)
    assert PASSWORD not in caplog.text


# --- what one attempt does, in words ---------------------------------------------------


def test_the_checkin_is_a_run_of_the_checkin_kind() -> None:
    assert Morning().checkin.kind is RunKind.CHECKIN


def test_the_checkin_names_the_steps_of_one_attempt_in_order() -> None:
    text = "\n".join(Morning().checkin.steps())

    assert text.index("log in") < text.index("open desktop") < text.index("hold")
    assert text.index("hold") < text.index("disconnect") < text.index("DISCONNECTED")
    assert repr(DESKTOP) in text
    assert "hold the desktop open for 120 s" in text
    assert "log off" not in text
