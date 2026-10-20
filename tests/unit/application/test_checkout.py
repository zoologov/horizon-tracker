"""Tests for the evening check-out: log off, confirm the session ended, one report."""

from collections.abc import Callable
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.checkout import EveningCheckout
from horizon_tracker.application.windowed_run import WindowedRun
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Outcome, Reason, RunReport
from horizon_tracker.domain.schedule import RetryPolicy, RunKind, Window
from horizon_tracker.domain.session import SessionState
from tests.support.fakes import FakeCalendar, FakeClock, FakeHorizonClient, FakeNotifier

MSK = ZoneInfo("Europe/Moscow")
DESKTOP = "DEV desktop"
BACKOFF = timedelta(seconds=20)
POLICY = RetryPolicy(max_attempts=3, backoff=BACKOFF)
SHOT = Path("/var/lib/horizon-tracker/shots/checkout.png")
LIST = Path("/var/lib/horizon-tracker/shots/checkout-launch-list.png")

ONE_CHECKOUT = ["login", "desktop_status", "log_off", "desktop_status"]


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 21, hour, minute, second, tzinfo=MSK)


class Evening:
    """An evening check-out wired to fakes, the desktop in ``state``."""

    def __init__(
        self,
        start: datetime | None = None,
        calendar_answer: bool | None = True,
        state: SessionState = SessionState.DISCONNECTED,
    ) -> None:
        self.clock = FakeClock(at(17, 0) if start is None else start)
        self.calendar = FakeCalendar(calendar_answer)
        self.notifier = FakeNotifier()
        self.client = FakeHorizonClient(desktop=DESKTOP, state=state)
        runner = WindowedRun(
            calendar=self.calendar,
            clock=self.clock,
            notifier=self.notifier,
            window=Window(start=time(17, 0), end=time(17, 5)),
            policy=POLICY,
        )
        self.checkout = EveningCheckout(
            client=self.client, clock=self.clock, runner=runner, desktop=DESKTOP
        )

    def run(self, *, force: bool = False) -> RunReport:
        return self.checkout.run(force=force)

    @property
    def only_report(self) -> RunReport:
        assert len(self.notifier.sent) == 1, f"expected one notification, got {self.notifier.sent}"
        return self.notifier.sent[0]


# --- success -----------------------------------------------------------------------


def test_checkout_logs_the_desktop_off_and_confirms_it() -> None:
    evening = Evening()

    evening.run()

    assert evening.client.calls == ONE_CHECKOUT
    assert evening.client.state is SessionState.NO_SESSION


def test_checkout_never_opens_the_desktop() -> None:
    evening = Evening()

    evening.run()

    assert "open_desktop" not in evening.client.calls


def test_checkout_reports_success_once() -> None:
    evening = Evening(start=at(17, 0, 7))

    report = evening.run()

    assert evening.only_report == report
    assert report.kind is RunKind.CHECKOUT
    assert report.outcome is Outcome.SUCCEEDED
    assert report.at == at(17, 0, 7)
    assert report.verdict_source is VerdictSource.CALENDAR


def test_a_checkout_reports_the_screenshot_of_the_launch_list() -> None:
    evening = Evening()
    evening.client.success_screenshot = LIST

    report = evening.run()

    assert evening.only_report == report
    assert report.outcome is Outcome.SUCCEEDED
    assert report.screenshot == LIST


def test_a_checkout_without_a_success_screenshot_reports_success_as_text() -> None:
    evening = Evening()

    report = evening.run()

    assert report.outcome is Outcome.SUCCEEDED
    assert report.screenshot is None


def test_a_forced_checkout_reports_the_screenshot_of_the_launch_list() -> None:
    evening = Evening(start=at(21, 0), calendar_answer=False)
    evening.client.success_screenshot = LIST

    report = evening.run(force=True)

    assert report.outcome is Outcome.SUCCEEDED
    assert report.screenshot == LIST


def test_checkout_logs_off_a_desktop_someone_is_attached_to() -> None:
    evening = Evening(state=SessionState.CONNECTED)

    assert evening.run().outcome is Outcome.SUCCEEDED
    assert evening.client.state is SessionState.NO_SESSION


# --- already logged off ------------------------------------------------------------


def test_an_already_logged_off_desktop_is_reported_and_the_run_stops() -> None:
    evening = Evening(state=SessionState.NO_SESSION)

    report = evening.run()

    assert evening.client.calls == ["login", "desktop_status"]
    assert evening.clock.sleeps == []
    assert evening.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.ALREADY_LOGGED_OFF


# --- not confirmed, retried --------------------------------------------------------


def test_a_log_off_the_broker_does_not_confirm_fails_after_every_attempt() -> None:
    evening = Evening()
    evening.client.log_off_takes_effect = False

    report = evening.run()

    assert evening.client.calls == ONE_CHECKOUT * POLICY.max_attempts
    assert evening.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.LOGOFF_NOT_CONFIRMED


def test_a_log_off_the_broker_does_not_confirm_reports_no_screenshot_of_the_list() -> None:
    evening = Evening()
    evening.client.log_off_takes_effect = False
    evening.client.success_screenshot = LIST

    report = evening.run()

    assert report.outcome is Outcome.FAILED
    assert report.screenshot is None


def test_a_retried_checkout_reports_the_launch_list_not_the_earlier_failure() -> None:
    evening = Evening()
    evening.client.fail_on("log_off", HorizonClientError(Reason.LOGOFF_NOT_CONFIRMED, SHOT))
    evening.client.success_screenshot = LIST

    report = evening.run()

    assert report.outcome is Outcome.SUCCEEDED
    assert report.screenshot == LIST


def test_a_failed_login_is_retried_after_the_backoff_and_succeeds() -> None:
    evening = Evening()
    evening.client.fail_on("login", HorizonClientError(Reason.PORTAL_UNREACHABLE))

    report = evening.run()

    assert evening.clock.sleeps == [BACKOFF.total_seconds()]
    assert evening.client.calls == ["login", *ONE_CHECKOUT]
    assert report.outcome is Outcome.SUCCEEDED


def test_a_log_off_whose_confirmation_was_lost_counts_on_the_retry() -> None:
    evening = Evening()
    evening.client.fail_on("desktop_status", HorizonClientError(Reason.UNEXPECTED), after=1)

    report = evening.run()

    assert evening.client.calls == [*ONE_CHECKOUT, "login", "desktop_status"]
    assert evening.only_report == report
    assert report.outcome is Outcome.SUCCEEDED


def _log_off_not_confirmed(client: FakeHorizonClient) -> None:
    """The log off takes effect, then the client answers with its failure screenshot."""
    client.lose_on("log_off", HorizonClientError(Reason.LOGOFF_NOT_CONFIRMED, SHOT))


def _read_after_log_off_fails(client: FakeHorizonClient) -> None:
    """The log off answers with its photo, then the read that would confirm it fails."""
    client.fail_on("desktop_status", HorizonClientError(Reason.UNEXPECTED), after=1)


@pytest.mark.parametrize("lose", [_log_off_not_confirmed, _read_after_log_off_fails])
def test_a_checkout_confirmed_only_on_the_retry_reports_no_screenshot(
    lose: Callable[[FakeHorizonClient], None],
) -> None:
    # The first log off went through and its attempt was not confirmed: the retry finds
    # no session and calls no log off, so no photo of the list is taken. Neither the
    # photo of the lost attempt nor its failure screenshot is carried into the success.
    evening = Evening()
    evening.client.success_screenshot = LIST
    lose(evening.client)

    report = evening.run()

    assert evening.client.calls.count("log_off") == 1
    assert report.outcome is Outcome.SUCCEEDED
    assert report.screenshot is None


def test_a_failed_log_off_reports_its_reason_and_screenshot() -> None:
    evening = Evening()
    evening.client.fail_on(
        "log_off", HorizonClientError(Reason.LOGOFF_NOT_CONFIRMED, SHOT), times=3
    )

    report = evening.run()

    assert evening.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.LOGOFF_NOT_CONFIRMED
    assert report.screenshot == SHOT


# --- skips -------------------------------------------------------------------------


def test_a_holiday_is_skipped_without_touching_the_portal() -> None:
    evening = Evening(calendar_answer=False)

    report = evening.run()

    assert evening.client.calls == []
    assert evening.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.NON_WORKING_DAY


def test_a_late_start_is_skipped_without_touching_the_portal() -> None:
    evening = Evening(start=at(17, 5, 1))

    report = evening.run()

    assert evening.client.calls == []
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.WINDOW_MISSED


def test_an_unreachable_calendar_on_a_weekday_checks_out_and_says_so() -> None:
    evening = Evening(calendar_answer=None)

    report = evening.run()

    assert report.outcome is Outcome.SUCCEEDED
    assert report.verdict_source is VerdictSource.WEEKDAY_FALLBACK


def test_force_checks_out_outside_the_window_without_the_calendar() -> None:
    evening = Evening(start=at(21, 0), calendar_answer=False)

    report = evening.run(force=True)

    assert evening.calendar.asked == []
    assert evening.client.calls == ONE_CHECKOUT
    assert report.verdict_source is None


# --- what one attempt does, in words ---------------------------------------------------


def test_the_checkout_is_a_run_of_the_checkout_kind() -> None:
    assert Evening().checkout.kind is RunKind.CHECKOUT


def test_the_checkout_names_the_steps_of_one_attempt_and_never_holds() -> None:
    text = "\n".join(Evening().checkout.steps())

    assert text.index("log in") < text.index("log off") < text.index("NO_SESSION")
    assert repr(DESKTOP) in text
    assert "hold" not in text
    assert "disconnect" not in text
