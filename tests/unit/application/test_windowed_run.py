"""Tests for the shared run loop: calendar, window, retries, and exactly one report."""

import logging
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.windowed_run import AttemptResult, FirstDecision, WindowedRun
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Outcome, Reason, RunReport, render
from horizon_tracker.domain.schedule import Decision, RetryPolicy, RunKind, Window
from tests.support.fakes import FakeCalendar, FakeClock, FakeNotifier

MSK = ZoneInfo("Europe/Moscow")
WEDNESDAY = date(2026, 10, 21)
SATURDAY = date(2026, 10, 24)
WINDOW = Window(start=time(7, 55), end=time(8, 0))
BACKOFF = timedelta(seconds=30)
POLICY = RetryPolicy(max_attempts=3, backoff=BACKOFF)
SHOT = Path("/var/lib/horizon-tracker/shots/checkin.png")
PASSWORD = "Pa$$w0rd-never-shown"


def at(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=MSK)


class ScriptedAttempt:
    """An attempt that plays its outcomes in order and counts how often it was made."""

    def __init__(self, clock: FakeClock, *outcomes: Outcome | Exception) -> None:
        self._clock = clock
        self._outcomes = list(outcomes)
        self.made = 0

    def __call__(self) -> AttemptResult:
        self.made += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        reason = {
            Outcome.SUCCEEDED: None,
            Outcome.FAILED: Reason.DESKTOP_DID_NOT_OPEN,
            Outcome.SKIPPED: Reason.ALREADY_LOGGED_OFF,
        }[outcome]
        return AttemptResult(outcome, self._clock.now(), reason)


class World:
    """The ports a windowed run talks to, with a clock set to ``start``."""

    def __init__(self, start: datetime, calendar_answer: bool | None = True) -> None:
        self.clock = FakeClock(start)
        self.calendar = FakeCalendar(calendar_answer)
        self.notifier = FakeNotifier()
        self.runner = WindowedRun(
            calendar=self.calendar,
            clock=self.clock,
            notifier=self.notifier,
            window=WINDOW,
            policy=POLICY,
        )

    def attempt(self, *outcomes: Outcome | Exception) -> ScriptedAttempt:
        return ScriptedAttempt(self.clock, *outcomes)

    def run(self, attempt: Callable[[], AttemptResult], *, force: bool = False) -> RunReport:
        return self.runner.run(RunKind.CHECKIN, attempt, force=force)

    @property
    def only_report(self) -> RunReport:
        assert len(self.notifier.sent) == 1, f"expected one notification, got {self.notifier.sent}"
        return self.notifier.sent[0]


# --- a working day inside the window ---------------------------------------------


def test_a_successful_first_attempt_is_reported_once_as_a_success() -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(Outcome.SUCCEEDED)

    returned = world.run(attempt)

    assert attempt.made == 1
    assert world.only_report == returned
    assert returned.kind is RunKind.CHECKIN
    assert returned.outcome is Outcome.SUCCEEDED
    assert returned.reason is None
    assert returned.verdict_source is VerdictSource.CALENDAR
    assert world.clock.sleeps == []


def test_the_report_carries_the_time_the_attempt_observed() -> None:
    world = World(at(WEDNESDAY, 7, 55))

    def attempt() -> AttemptResult:
        return AttemptResult(Outcome.SUCCEEDED, at(WEDNESDAY, 7, 56, 12))

    assert world.run(attempt).at == at(WEDNESDAY, 7, 56, 12)


def test_the_calendar_is_asked_about_the_day_on_the_clock() -> None:
    world = World(at(WEDNESDAY, 7, 55))

    world.run(world.attempt(Outcome.SUCCEEDED))

    assert world.calendar.asked == [WEDNESDAY]


def test_the_last_moment_of_the_window_still_runs() -> None:
    world = World(at(WEDNESDAY, 8, 0))
    attempt = world.attempt(Outcome.SUCCEEDED)

    assert world.run(attempt).outcome is Outcome.SUCCEEDED
    assert attempt.made == 1


# --- calendar ----------------------------------------------------------------------


def test_a_holiday_is_skipped_without_an_attempt_and_reported() -> None:
    world = World(at(WEDNESDAY, 7, 55), calendar_answer=False)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 0
    assert world.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.NON_WORKING_DAY
    assert report.verdict_source is VerdictSource.CALENDAR
    assert report.at == at(WEDNESDAY, 7, 55)


def test_an_unreachable_calendar_on_a_weekday_runs_and_names_the_fallback() -> None:
    world = World(at(WEDNESDAY, 7, 55), calendar_answer=None)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 1
    assert report.outcome is Outcome.SUCCEEDED
    assert report.verdict_source is VerdictSource.WEEKDAY_FALLBACK


def test_an_unreachable_calendar_on_a_weekend_skips_and_names_the_fallback() -> None:
    world = World(at(SATURDAY, 7, 55), calendar_answer=None)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 0
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.NON_WORKING_DAY
    assert report.verdict_source is VerdictSource.WEEKDAY_FALLBACK


# --- the window --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "reason"),
    [
        (at(WEDNESDAY, 8, 0, 1), Reason.WINDOW_MISSED),
        (at(WEDNESDAY, 11, 0), Reason.WINDOW_MISSED),
        (at(WEDNESDAY, 7, 54, 59), Reason.TOO_EARLY),
        (at(WEDNESDAY, 3, 0), Reason.TOO_EARLY),
    ],
    ids=["a second late", "hours late", "a second early", "hours early"],
)
def test_a_run_outside_its_window_is_skipped_and_reported(start: datetime, reason: Reason) -> None:
    world = World(start)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 0
    assert world.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is reason
    assert report.verdict_source is VerdictSource.CALENDAR


@pytest.mark.parametrize(
    ("start", "said", "not_said"),
    [
        (at(WEDNESDAY, 7, 54, 59), "до своего окна", "после своего окна"),
        (at(WEDNESDAY, 8, 0, 1), "после своего окна", "до своего окна"),
    ],
    ids=["early", "late"],
)
def test_the_notification_says_on_which_side_of_the_window_the_run_started(
    start: datetime, said: str, not_said: str
) -> None:
    world = World(start)

    world.run(world.attempt(Outcome.SUCCEEDED))

    text = render(world.only_report)
    assert said in text
    assert not_said not in text


# --- retries -----------------------------------------------------------------------


def test_a_failed_attempt_is_retried_after_the_backoff() -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(Outcome.FAILED, Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 2
    assert world.clock.sleeps == [BACKOFF.total_seconds()]
    assert world.only_report == report
    assert report.outcome is Outcome.SUCCEEDED


def test_a_client_error_is_a_failed_attempt_and_is_retried() -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(HorizonClientError(Reason.PORTAL_UNREACHABLE), Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 2
    assert report.outcome is Outcome.SUCCEEDED


def test_spent_attempts_report_the_last_failure_with_its_screenshot() -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(
        Outcome.FAILED,
        HorizonClientError(Reason.PORTAL_UNREACHABLE),
        HorizonClientError(Reason.LOGIN_REJECTED, screenshot=SHOT),
    )

    report = world.run(attempt)

    assert attempt.made == POLICY.max_attempts
    assert world.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.LOGIN_REJECTED
    assert report.screenshot == SHOT
    assert report.verdict_source is VerdictSource.CALENDAR


def test_no_backoff_is_waited_after_the_last_attempt() -> None:
    world = World(at(WEDNESDAY, 7, 55))

    world.run(world.attempt(Outcome.FAILED, Outcome.FAILED, Outcome.FAILED))

    assert world.clock.sleeps == [BACKOFF.total_seconds()] * (POLICY.max_attempts - 1)


def test_a_retry_that_would_start_after_the_window_is_not_made_and_the_failure_reported() -> None:
    world = World(at(WEDNESDAY, 7, 59, 50))
    attempt = world.attempt(
        HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN, screenshot=SHOT), Outcome.SUCCEEDED
    )

    report = world.run(attempt)

    assert attempt.made == 1
    assert world.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.DESKTOP_DID_NOT_OPEN
    assert report.screenshot == SHOT


def test_a_skip_the_attempt_found_is_final_and_not_retried() -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(Outcome.SKIPPED, Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert attempt.made == 1
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.ALREADY_LOGGED_OFF
    assert world.clock.sleeps == []


# --- an error nobody named ---------------------------------------------------------


def test_an_unexpected_error_is_a_failed_attempt_reported_as_unexpected() -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(*[RuntimeError("boom")] * POLICY.max_attempts)

    report = world.run(attempt)

    assert attempt.made == POLICY.max_attempts
    assert world.only_report == report
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.UNEXPECTED


def test_an_unexpected_error_text_reaches_neither_the_notification_nor_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World(at(WEDNESDAY, 7, 55))
    attempt = world.attempt(RuntimeError(f"fill #password {PASSWORD}"), Outcome.SUCCEEDED)
    caplog.set_level(logging.DEBUG)

    world.run(attempt)

    assert "RuntimeError" in caplog.text
    assert PASSWORD not in caplog.text
    assert PASSWORD not in render(world.only_report)


# --- --force -----------------------------------------------------------------------


def test_force_runs_outside_the_window_without_asking_the_calendar() -> None:
    world = World(at(SATURDAY, 11, 0), calendar_answer=False)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt, force=True)

    assert attempt.made == 1
    assert world.calendar.asked == []
    assert world.only_report == report
    assert report.outcome is Outcome.SUCCEEDED
    assert report.verdict_source is None


def test_force_still_gives_up_when_the_attempts_are_spent() -> None:
    world = World(at(SATURDAY, 11, 0))
    attempt = world.attempt(Outcome.FAILED, Outcome.FAILED, Outcome.FAILED, Outcome.SUCCEEDED)

    report = world.run(attempt, force=True)

    assert attempt.made == POLICY.max_attempts
    assert report.outcome is Outcome.FAILED
    assert report.verdict_source is None


# --- the first decision, as the dry run reads it --------------------------------------


def test_the_first_decision_names_the_moment_the_decision_and_the_calendars_word() -> None:
    world = World(at(WEDNESDAY, 7, 56))

    first = world.runner.first_decision()

    assert first == FirstDecision(at(WEDNESDAY, 7, 56), Decision.RUN, VerdictSource.CALENDAR)
    assert world.calendar.asked == [WEDNESDAY]
    assert world.notifier.sent == []


@pytest.mark.parametrize(
    ("start", "calendar_answer", "decision", "source", "outcome"),
    [
        (at(WEDNESDAY, 7, 55), True, Decision.RUN, VerdictSource.CALENDAR, Outcome.SUCCEEDED),
        (at(WEDNESDAY, 7, 54), True, Decision.SKIP_EARLY, VerdictSource.CALENDAR, Outcome.SKIPPED),
        (at(WEDNESDAY, 8, 1), True, Decision.SKIP_LATE, VerdictSource.CALENDAR, Outcome.SKIPPED),
        (
            at(SATURDAY, 7, 55),
            False,
            Decision.SKIP_NON_WORKING_DAY,
            VerdictSource.CALENDAR,
            Outcome.SKIPPED,
        ),
        (
            at(WEDNESDAY, 7, 55),
            None,
            Decision.RUN,
            VerdictSource.WEEKDAY_FALLBACK,
            Outcome.SUCCEEDED,
        ),
    ],
)
def test_the_first_decision_is_the_one_the_run_then_takes(
    start: datetime,
    calendar_answer: bool | None,
    decision: Decision,
    source: VerdictSource,
    outcome: Outcome,
) -> None:
    world = World(start, calendar_answer)

    first = world.runner.first_decision()
    report = world.run(world.attempt(Outcome.SUCCEEDED))

    assert (first.decision, first.verdict_source) == (decision, source)
    assert (report.outcome, report.verdict_source) == (outcome, source)


def test_a_forced_first_decision_runs_and_asks_no_calendar() -> None:
    world = World(at(SATURDAY, 12, 0), calendar_answer=False)

    first = world.runner.first_decision(force=True)

    assert first == FirstDecision(at(SATURDAY, 12, 0), Decision.RUN, None)
    assert world.calendar.asked == []


def test_the_loop_names_its_retries_and_its_one_report() -> None:
    assert World(at(WEDNESDAY, 7, 55)).runner.steps() == (
        "retry a failed attempt, up to 3 attempts 30 s apart, while the window allows",
        "send one report to Telegram",
    )
