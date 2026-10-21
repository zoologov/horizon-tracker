"""Tests for the shared run loop: calendar, window, retries, and exactly one report."""

import logging
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.windowed_run import AttemptResult, FirstDecision, WindowedRun
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.messages import Language, Message
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Outcome, Reason, RunReport, render
from horizon_tracker.domain.schedule import Decision, RetryPolicy, RunKind, Window, window_from
from tests.support.fakes import FakeCalendar, FakeClock, FakeNotifier

MSK = ZoneInfo("Europe/Moscow")
WEDNESDAY = date(2026, 10, 21)
SATURDAY = date(2026, 10, 24)
WINDOW = Window(start=time(7, 55), end=time(8, 0))
BACKOFF = timedelta(seconds=30)
POLICY = RetryPolicy(max_attempts=3, backoff=BACKOFF)
SHOT = Path("/var/lib/horizon-tracker/shots/checkin.png")
PASSWORD = "Pa$$w0rd-never-shown"
# A scheduled run: the timer fires at the start of the range, the run waits for the moment.
RANGE_START = time(7, 30)
MOMENT = time(7, 43)
GRACE = timedelta(minutes=5)
DRAWN_WINDOW = window_from(MOMENT, GRACE)


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

    @classmethod
    def drawn(
        cls,
        start: datetime,
        calendar_answer: bool | None = True,
        moment: time = MOMENT,
        range_start: time = RANGE_START,
    ) -> "World":
        """A run due at today's drawn ``moment``, whose timer fires from ``range_start``."""
        world = cls(start, calendar_answer)
        world.runner = WindowedRun(
            calendar=world.calendar,
            clock=world.clock,
            notifier=world.notifier,
            window=window_from(moment, GRACE),
            policy=POLICY,
            moment=moment,
            range_start=range_start,
        )
        return world

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

    text = render(world.only_report, Language.RU)
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
    assert all(PASSWORD not in render(world.only_report, language) for language in Language)


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
    assert english(World(at(WEDNESDAY, 7, 55)).runner.steps()) == (
        "retry a failed attempt, up to 3 attempts 30 s apart, while the window allows",
        "send one report to Telegram",
    )


# --- the drawn moment: wait for it inside the process -----------------------------------


def english(steps: tuple[Message, ...]) -> tuple[str, ...]:
    return tuple(step.in_language(Language.EN) for step in steps)


def seconds(hours: int = 0, minutes: int = 0, secs: int = 0) -> float:
    return timedelta(hours=hours, minutes=minutes, seconds=secs).total_seconds()


@pytest.mark.parametrize(
    ("start", "wait"),
    [
        (at(WEDNESDAY, 7, 30), seconds(minutes=13)),
        (at(WEDNESDAY, 7, 35, 20), seconds(minutes=7, secs=40)),
        (at(WEDNESDAY, 7, 42, 59), seconds(secs=1)),
    ],
    ids=["from the range start", "mid-range with seconds", "a second before"],
)
def test_a_run_started_before_its_moment_waits_exactly_until_it_in_one_sleep(
    start: datetime, wait: float
) -> None:
    world = World.drawn(start)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert world.clock.sleeps == [wait]
    assert attempt.made == 1
    assert report.at == at(WEDNESDAY, 7, 43)
    assert world.only_report == report
    assert report.outcome is Outcome.SUCCEEDED


@pytest.mark.parametrize(
    ("start", "outcome", "reason"),
    [
        (at(WEDNESDAY, 7, 43), Outcome.SUCCEEDED, None),
        (at(WEDNESDAY, 7, 46, 30), Outcome.SUCCEEDED, None),
        (at(WEDNESDAY, 7, 48), Outcome.SUCCEEDED, None),
        (at(WEDNESDAY, 7, 48, 1), Outcome.SKIPPED, Reason.WINDOW_MISSED),
    ],
    ids=["at the moment", "inside the window", "the window's last second", "after the window"],
)
def test_a_run_started_at_or_after_its_moment_does_not_wait(
    start: datetime, outcome: Outcome, reason: Reason | None
) -> None:
    world = World.drawn(start)

    report = world.run(world.attempt(Outcome.SUCCEEDED))

    assert world.clock.sleeps == []
    assert (report.outcome, report.reason) == (outcome, reason)


@pytest.mark.parametrize(
    "start",
    [at(WEDNESDAY, 7, 29, 59), at(WEDNESDAY, 3, 0)],
    ids=["a second before the range", "hours before the range"],
)
def test_a_run_started_before_the_range_is_skipped_as_too_early_without_waiting(
    start: datetime,
) -> None:
    world = World.drawn(start)
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt)

    assert world.clock.sleeps == []
    assert attempt.made == 0
    assert world.only_report == report
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.TOO_EARLY
    assert report.at == start


def test_a_non_working_day_is_skipped_at_once_without_waiting_for_the_moment() -> None:
    world = World.drawn(at(SATURDAY, 7, 30), calendar_answer=False)

    report = world.run(world.attempt(Outcome.SUCCEEDED))

    assert world.clock.sleeps == []
    assert report.reason is Reason.NON_WORKING_DAY
    assert report.at == at(SATURDAY, 7, 30)


def test_a_forced_run_does_not_wait_for_the_drawn_moment() -> None:
    world = World.drawn(at(WEDNESDAY, 7, 30))
    attempt = world.attempt(Outcome.SUCCEEDED)

    report = world.run(attempt, force=True)

    assert world.clock.sleeps == []
    assert attempt.made == 1
    assert report.at == at(WEDNESDAY, 7, 30)
    assert report.planned_at is None


def test_a_moment_of_now_runs_at_once_even_before_the_range() -> None:
    # --force may be composed as moment = now: no wait, whatever the range says.
    now = at(SATURDAY, 6, 0, 17)
    world = World.drawn(now, calendar_answer=False, moment=now.time(), range_start=now.time())

    report = world.run(world.attempt(Outcome.SUCCEEDED), force=True)

    assert world.clock.sleeps == []
    assert report.outcome is Outcome.SUCCEEDED


def test_a_retry_after_the_wait_still_waits_its_backoff() -> None:
    world = World.drawn(at(WEDNESDAY, 7, 30))

    report = world.run(world.attempt(Outcome.FAILED, Outcome.SUCCEEDED))

    assert world.clock.sleeps == [seconds(minutes=13), BACKOFF.total_seconds()]
    assert world.only_report == report
    assert report.outcome is Outcome.SUCCEEDED


@pytest.mark.parametrize(
    ("start", "calendar_answer", "attempts"),
    [
        (at(WEDNESDAY, 7, 30), True, (Outcome.SUCCEEDED,)),
        (at(WEDNESDAY, 7, 30), True, (Outcome.FAILED,) * POLICY.max_attempts),
        (at(WEDNESDAY, 7, 0), True, ()),
        (at(WEDNESDAY, 9, 0), True, ()),
        (at(SATURDAY, 7, 30), False, ()),
    ],
    ids=["success", "failure", "too early", "too late", "day off"],
)
def test_a_scheduled_report_names_the_drawn_moment_whatever_the_outcome(
    start: datetime, calendar_answer: bool, attempts: tuple[Outcome, ...]
) -> None:
    world = World.drawn(start, calendar_answer)

    report = world.run(world.attempt(*attempts))

    assert report.planned_at == MOMENT
    assert "назначено на 07:43" in render(world.only_report, Language.RU)


def test_a_run_without_a_drawn_moment_names_no_planned_time() -> None:
    world = World(at(WEDNESDAY, 7, 55))

    assert world.run(world.attempt(Outcome.SUCCEEDED)).planned_at is None


def test_the_first_decision_while_waiting_is_the_decision_at_the_moment() -> None:
    world = World.drawn(at(WEDNESDAY, 7, 30))

    first = world.runner.first_decision()

    assert first == FirstDecision(
        at(WEDNESDAY, 7, 30), Decision.RUN, VerdictSource.CALENDAR, at(WEDNESDAY, 7, 43)
    )
    assert world.clock.sleeps == []
    assert world.notifier.sent == []


@pytest.mark.parametrize(
    ("start", "decision"),
    [
        (at(WEDNESDAY, 7, 29), Decision.SKIP_EARLY),
        (at(WEDNESDAY, 7, 44), Decision.RUN),
        (at(WEDNESDAY, 8, 0), Decision.SKIP_LATE),
    ],
)
def test_the_first_decision_names_no_wait_outside_the_waiting_span(
    start: datetime, decision: Decision
) -> None:
    first = World.drawn(start).runner.first_decision()

    assert (first.decision, first.waits_until) == (decision, None)


def test_a_forced_first_decision_does_not_wait() -> None:
    first = World.drawn(at(WEDNESDAY, 7, 30)).runner.first_decision(force=True)

    assert (first.decision, first.waits_until) == (Decision.RUN, None)


def test_a_scheduled_loop_names_its_wait_before_its_retries() -> None:
    assert english(World.drawn(at(WEDNESDAY, 7, 30)).runner.steps()) == (
        "wait until the drawn moment 07:43 if started from 07:30; earlier is skipped as too early",
        "retry a failed attempt, up to 3 attempts 30 s apart, while the window allows",
        "send one report to Telegram",
    )


def make_runner(window: Window, moment: time | None, range_start: time | None) -> WindowedRun:
    return WindowedRun(
        calendar=FakeCalendar(True),
        clock=FakeClock(at(WEDNESDAY, 7, 30)),
        notifier=FakeNotifier(),
        window=window,
        policy=POLICY,
        moment=moment,
        range_start=range_start,
    )


@pytest.mark.parametrize(
    ("window", "moment", "range_start", "message"),
    [
        (DRAWN_WINDOW, MOMENT, None, "moment and range_start come together"),
        (DRAWN_WINDOW, None, RANGE_START, "moment and range_start come together"),
        (WINDOW, MOMENT, RANGE_START, "the window must open at the moment"),
        (DRAWN_WINDOW, MOMENT, time(7, 44), "range_start 07:44:00 is after the moment"),
    ],
    ids=["no range start", "no moment", "window elsewhere", "range after the moment"],
)
def test_a_scheduled_run_refuses_a_moment_its_window_or_range_does_not_fit(
    window: Window, moment: time | None, range_start: time | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        make_runner(window, moment, range_start)


def test_a_range_starting_at_the_moment_itself_is_accepted() -> None:
    runner = make_runner(DRAWN_WINDOW, MOMENT, MOMENT)

    assert runner.moment == runner.range_start == MOMENT
