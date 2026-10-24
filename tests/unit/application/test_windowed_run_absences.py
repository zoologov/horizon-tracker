"""Tests for the run loop's absence verdict and for which skips it reports.

An absence entered for today skips the run before the calendar is asked; an unreadable
absence store is read as none entered. ``notify_day_skips=False`` keeps a day-level skip
(a non-working day, an absence) out of the chat and nothing else.
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.windowed_run import AttemptResult, FirstDecision, WindowedRun
from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.report import Outcome, Reason, RunReport, absence_reason, render
from horizon_tracker.domain.schedule import Decision, RetryPolicy, RunKind, window_from
from tests.support.fakes import FakeAbsenceStore, FakeCalendar, FakeClock, FakeNotifier

MSK = ZoneInfo("Europe/Moscow")
TUESDAY = date(2026, 11, 3)
RANGE_START = time(7, 30)
MOMENT = time(7, 43)
GRACE = timedelta(minutes=5)
POLICY = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=30))
VACATION = Absence(1, AbsenceKind.VACATION, date(2026, 11, 3), date(2026, 11, 14))


def at(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MSK)


class World:
    """A scheduled run over fakes, with ``absences`` entered and the calendar's ``answer``."""

    def __init__(
        self,
        start: datetime,
        *absences: Absence,
        answer: bool | None = True,
        notify_day_skips: bool = True,
    ) -> None:
        self.clock = FakeClock(start)
        self.calendar = FakeCalendar(answer)
        self.notifier = FakeNotifier()
        self.store = FakeAbsenceStore(AbsenceBook.of(absences))
        self.made = 0
        self.runner = WindowedRun(
            calendar=self.calendar,
            clock=self.clock,
            notifier=self.notifier,
            window=window_from(MOMENT, GRACE),
            policy=POLICY,
            moment=MOMENT,
            range_start=RANGE_START,
            absences=self.store,
            notify_day_skips=notify_day_skips,
        )

    def attempt(self) -> AttemptResult:
        self.made += 1
        return AttemptResult(Outcome.SUCCEEDED, self.clock.now())

    def run(self, kind: RunKind = RunKind.CHECKIN, *, force: bool = False) -> RunReport:
        return self.runner.run(kind, self.attempt, force=force)


# --- the absence verdict ----------------------------------------------------------------


@pytest.mark.parametrize("kind", list(AbsenceKind))
def test_a_day_an_absence_covers_is_skipped_with_its_kind_and_asks_no_calendar(
    kind: AbsenceKind,
) -> None:
    absence = Absence(4, kind, date(2026, 11, 1), date(2026, 11, 5))
    world = World(at(TUESDAY, 7, 30), absence)

    report = world.run()

    assert world.calendar.asked == []
    assert world.made == 0
    assert world.clock.sleeps == []
    assert world.notifier.sent == [report]
    assert report == RunReport(
        kind=RunKind.CHECKIN,
        outcome=Outcome.SKIPPED,
        at=at(TUESDAY, 7, 30),
        verdict_source=None,
        reason=absence_reason(kind),
        planned_at=MOMENT,
        absence=absence,
    )


@pytest.mark.parametrize(
    "day", [date(2026, 11, 3), date(2026, 11, 14)], ids=["first day", "last day"]
)
def test_both_ends_of_an_absence_are_skipped(day: date) -> None:
    report = World(at(day, 7, 30), VACATION).run()

    assert report.reason is Reason.ON_VACATION


@pytest.mark.parametrize(
    "day", [date(2026, 11, 2), date(2026, 11, 16)], ids=["the day before", "the day after"]
)
def test_a_day_outside_every_absence_runs_after_asking_the_calendar(day: date) -> None:
    world = World(at(day, 7, 30), VACATION)

    report = world.run()

    assert world.calendar.asked == [day]
    assert world.made == 1
    assert report.outcome is Outcome.SUCCEEDED
    assert report.absence is None


NEW_YEAR = Absence(2, AbsenceKind.VACATION, date(2026, 12, 30), date(2027, 1, 2))


@pytest.mark.parametrize(
    ("day", "outcome"),
    [
        (date(2026, 12, 29), Outcome.SUCCEEDED),
        (date(2026, 12, 31), Outcome.SKIPPED),
        (date(2027, 1, 2), Outcome.SKIPPED),
        (date(2027, 1, 3), Outcome.SUCCEEDED),
    ],
    ids=["the day before", "new year's eve", "the last day", "the day after"],
)
def test_an_absence_across_new_year_covers_its_days_in_both_years(
    day: date, outcome: Outcome
) -> None:
    report = World(at(day, 7, 30), NEW_YEAR).run()

    assert report.outcome is outcome


def test_an_absence_across_new_year_is_named_without_the_years() -> None:
    world = World(at(date(2027, 1, 1), 7, 30), NEW_YEAR)

    text = render(world.run(), Language.RU)

    assert text.splitlines() == ["Вход пропущен", "Причина: отпуск (30.12–02.01)"]


def test_the_store_is_read_once_per_run() -> None:
    world = World(at(TUESDAY, 7, 30), VACATION)

    world.run()

    assert world.store.loads == 1


def test_an_absence_skip_is_reported_in_the_owners_words() -> None:
    world = World(at(TUESDAY, 7, 30), VACATION)

    text = render(world.run(), Language.RU)

    assert text.splitlines() == ["Вход пропущен", "Причина: отпуск (03.11–14.11)"]


def test_an_unreadable_store_is_logged_by_type_and_the_day_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World(at(TUESDAY, 7, 30))
    world.store.broken = True

    with caplog.at_level(logging.WARNING, logger="horizon_tracker"):
        report = world.run()

    assert report.outcome is Outcome.SUCCEEDED
    assert world.calendar.asked == [TUESDAY]
    assert "AbsenceStoreError" in caplog.text
    # The detail stays with the probe: the run names the type only.
    assert "not valid JSON" not in caplog.text


def test_a_forced_run_ignores_an_absence_and_does_not_read_the_store() -> None:
    world = World(at(TUESDAY, 12, 0), VACATION)

    report = world.run(force=True)

    assert world.made == 1
    assert report.outcome is Outcome.SUCCEEDED
    assert world.store.loads == 0


# --- the first decision, as the dry run reads it ------------------------------------------


def test_the_first_decision_on_an_absence_day_is_an_absence_skip_without_a_calendar() -> None:
    world = World(at(TUESDAY, 7, 30), VACATION)

    first = world.runner.first_decision()

    assert first == FirstDecision(at(TUESDAY, 7, 30), Decision.SKIP_ABSENT, None, None)
    assert world.calendar.asked == []
    assert world.notifier.sent == []


def test_a_forced_first_decision_ignores_an_absence() -> None:
    world = World(at(TUESDAY, 12, 0), VACATION)

    assert world.runner.first_decision(force=True).decision is Decision.RUN
    assert world.store.loads == 0


def test_the_loop_names_its_absence_check_first() -> None:
    steps = World(at(TUESDAY, 7, 30)).runner.steps()

    assert steps[0].in_language(Language.EN) == (
        "skip the day if an absence entered through the bot covers it, before the calendar is asked"
    )


@pytest.mark.parametrize(
    ("notify_day_skips", "report_step"),
    [
        (True, "send one report to Telegram"),
        (False, "send one report to Telegram, unless the day is skipped: the morning reports it"),
    ],
)
def test_the_loop_names_which_reports_it_sends(notify_day_skips: bool, report_step: str) -> None:
    runner = World(at(TUESDAY, 7, 30), notify_day_skips=notify_day_skips).runner

    assert runner.steps()[-1].in_language(Language.EN) == report_step


# --- notify_day_skips: the evening is silent on a skipped day ----------------------------------


def test_an_absence_skip_is_not_sent_when_day_skips_are_not_notified(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World(at(TUESDAY, 16, 30), VACATION, notify_day_skips=False)

    with caplog.at_level(logging.INFO, logger="horizon_tracker"):
        report = world.run(RunKind.CHECKOUT)

    assert world.notifier.sent == []
    assert report.reason is Reason.ON_VACATION
    assert "checkout run skipped (on_vacation)" in caplog.text
    assert "not sent" in caplog.text


def test_a_non_working_day_is_not_sent_when_day_skips_are_not_notified() -> None:
    world = World(at(TUESDAY, 16, 30), answer=False, notify_day_skips=False)

    report = world.run(RunKind.CHECKOUT)

    assert world.notifier.sent == []
    assert report.reason is Reason.NON_WORKING_DAY


@pytest.mark.parametrize(
    ("start", "reason"),
    [(at(TUESDAY, 7, 0), Reason.TOO_EARLY), (at(TUESDAY, 9, 0), Reason.WINDOW_MISSED)],
)
def test_an_anomalous_skip_is_sent_even_when_day_skips_are_not_notified(
    start: datetime, reason: Reason
) -> None:
    world = World(start, notify_day_skips=False)

    report = world.run(RunKind.CHECKOUT)

    assert world.notifier.sent == [report]
    assert report.reason is reason


def test_a_run_that_was_made_is_sent_even_when_day_skips_are_not_notified() -> None:
    world = World(at(TUESDAY, 7, 30), notify_day_skips=False)

    report = world.run(RunKind.CHECKOUT)

    assert world.notifier.sent == [report]
    assert report.outcome is Outcome.SUCCEEDED
