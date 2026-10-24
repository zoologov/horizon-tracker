"""Tests for the checks that log nothing in: the dependency probe and the dry-run plan."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.checkin import MorningCheckin
from horizon_tracker.application.checkout import EveningCheckout
from horizon_tracker.application.probe import (
    Check,
    CheckStatus,
    DryRun,
    Probe,
    ProbeReport,
    RunPlan,
    schedule_detail,
)
from horizon_tracker.application.windowed_run import WindowedRun
from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.messages import Language, Message
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Reason
from horizon_tracker.domain.schedule import (
    DailyMoments,
    Decision,
    RetryPolicy,
    RunKind,
    Window,
    window_from,
)
from tests.support.fakes import (
    FakeAbsenceStore,
    FakeCalendar,
    FakeClock,
    FakeHorizonClient,
    FakeNotifier,
)

MSK = ZoneInfo("Europe/Moscow")
WEDNESDAY = date(2026, 10, 21)
SATURDAY = date(2026, 10, 24)
DESKTOP = "DEV desktop"
CHROME = Path("/usr/bin/google-chrome")
ABSENCES = Path("/srv/state/absences.json")
CHECKIN_WINDOW = Window(start=time(7, 55), end=time(8, 0))
CHECKOUT_WINDOW = Window(start=time(17, 0), end=time(17, 5))
POLICY = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=30))
HOLD = timedelta(seconds=120)
MOMENTS = DailyMoments(check_in=time(7, 43), check_out=time(16, 52))
RANGE_STARTS = {RunKind.CHECKIN: time(7, 30), RunKind.CHECKOUT: time(16, 30)}
GRACE = timedelta(minutes=5)
ANY_DETAIL = Message("probe.status.ok")


def at(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MSK)


def english(message: Message) -> str:
    return message.in_language(Language.EN)


# --- Probe ---------------------------------------------------------------------------


class Probing:
    """A probe over fakes: a reachable portal and calendar, Chrome installed."""

    def __init__(
        self,
        calendar_answer: bool | None = True,
        chrome_found: bool = True,
        moments: DailyMoments | None = None,
    ) -> None:
        self.moments = moments
        self.client = FakeHorizonClient(desktop=DESKTOP)
        self.calendar = FakeCalendar(calendar_answer)
        self.clock = FakeClock(at(WEDNESDAY, 12, 0))
        self.looked_for: list[Path] = []
        self._chrome_found = chrome_found
        self.absences = FakeAbsenceStore()

    def file_exists(self, path: Path) -> bool:
        self.looked_for.append(path)
        return self._chrome_found

    def run(self) -> ProbeReport:
        probe = Probe(
            client=self.client,
            calendar=self.calendar,
            clock=self.clock,
            chrome_path=CHROME,
            file_exists=self.file_exists,
            absences=self.absences,
            absences_file=ABSENCES,
            moments=self.moments,
        )
        return probe.run()


def check(report: ProbeReport, name: str) -> Check:
    (found,) = [item for item in report.checks if item.name == name]
    return found


def test_probe_checks_portal_calendar_and_chrome_in_that_order() -> None:
    report = Probing().run()

    assert [item.name for item in report.checks] == ["portal", "calendar", "chrome", "absences"]
    assert all(item.status is CheckStatus.OK for item in report.checks)
    assert report.ok


def test_probe_asks_for_the_client_bundles_and_the_browser_version_and_nothing_else() -> None:
    probing = Probing()

    probing.run()

    assert probing.client.calls == ["client_bundles", "browser_version"]


def test_the_portal_check_names_the_client_bundles_it_read() -> None:
    probing = Probing()
    probing.client.bundles = ("app-htmlaccess.a1.js", "vendor.b2.js")

    report = probing.run()

    assert (
        english(check(report, "portal").detail)
        == "client bundles: app-htmlaccess.a1.js, vendor.b2.js"
    )


def test_an_unreachable_portal_fails_the_probe_and_names_the_reason() -> None:
    probing = Probing()
    probing.client.fail_on("client_bundles", HorizonClientError(Reason.PORTAL_UNREACHABLE))

    report = probing.run()

    portal = check(report, "portal")
    assert portal.status is CheckStatus.FAILED
    assert english(portal.detail) == "no answer: portal_unreachable"
    assert check(report, "chrome").status is CheckStatus.OK
    assert not report.ok


def test_the_calendar_is_asked_about_today() -> None:
    probing = Probing()

    report = probing.run()

    assert probing.calendar.asked == [WEDNESDAY]
    assert english(check(report, "calendar").detail) == "isdayoff.ru: 2026-10-21 is a working day"


def test_the_calendar_names_a_day_off() -> None:
    report = Probing(calendar_answer=False).run()

    calendar = check(report, "calendar")
    assert calendar.status is CheckStatus.OK
    assert english(calendar.detail) == "isdayoff.ru: 2026-10-21 is a day off"


def test_an_unreachable_calendar_degrades_the_probe_without_failing_it() -> None:
    report = Probing(calendar_answer=None).run()

    calendar = check(report, "calendar")
    assert calendar.status is CheckStatus.DEGRADED
    assert "Mon-Fri" in english(calendar.detail)
    assert report.ok


def test_chrome_is_started_from_the_configured_path_and_its_version_named() -> None:
    probing = Probing()

    report = probing.run()

    assert probing.looked_for == [CHROME]
    chrome = check(report, "chrome")
    assert chrome.status is CheckStatus.OK
    assert english(chrome.detail) == f"Chrome 131.0.6778.85 started from {CHROME}"


def test_a_missing_chrome_fails_the_probe_without_starting_anything() -> None:
    probing = Probing(chrome_found=False)

    report = probing.run()

    chrome = check(report, "chrome")
    assert chrome.status is CheckStatus.FAILED
    assert english(chrome.detail) == f"not found at {CHROME}"
    assert "browser_version" not in probing.client.calls
    assert not report.ok


def test_a_chrome_that_does_not_start_fails_the_probe_and_names_the_reason() -> None:
    probing = Probing()
    probing.client.fail_on("browser_version", HorizonClientError(Reason.UNEXPECTED))

    report = probing.run()

    chrome = check(report, "chrome")
    assert chrome.status is CheckStatus.FAILED
    assert (
        english(chrome.detail) == f"found at {CHROME} but did not start: {Reason.UNEXPECTED.value}"
    )
    assert check(report, "portal").status is CheckStatus.OK
    assert not report.ok


def test_a_check_names_what_it_found_in_any_language_it_is_shown_in() -> None:
    # The probe hands out keys and values; the language is the reader's, not the probe's.
    chrome = check(Probing().run(), "chrome")

    assert chrome.detail.in_language(Language.RU) == f"Chrome 131.0.6778.85 запущен из {CHROME}"


def test_a_probe_report_is_ok_unless_a_check_failed() -> None:
    ok = Check("portal", CheckStatus.OK, ANY_DETAIL)
    degraded = Check("calendar", CheckStatus.DEGRADED, ANY_DETAIL)
    failed = Check("chrome", CheckStatus.FAILED, ANY_DETAIL)

    assert ProbeReport((ok, degraded)).ok
    assert not ProbeReport((ok, failed, degraded)).ok


@pytest.mark.parametrize("status", list(CheckStatus))
@pytest.mark.parametrize("name", ["portal", "calendar", "chrome", "absences", "schedule"])
def test_a_check_names_itself_and_its_status_as_messages(name: str, status: CheckStatus) -> None:
    made = Check(name, status, ANY_DETAIL)

    assert made.label == Message(f"probe.check.{name}")
    assert made.status_label == Message(f"probe.status.{status}")


def test_every_check_the_probe_makes_has_a_label() -> None:
    # The names are free strings: the probe's own checks are the ones that must read.
    report = Probing(moments=MOMENTS).run()

    assert [item.label.key for item in report.checks] == [
        "probe.check.portal",
        "probe.check.calendar",
        "probe.check.chrome",
        "probe.check.absences",
        "probe.check.schedule",
    ]


def test_a_check_with_a_name_the_catalogue_lacks_is_refused_when_it_is_made() -> None:
    # A fifth check without a text fails where it is written, not when the CLI prints it.
    with pytest.raises(KeyError, match=r"'probe\.check\.porta'"):
        Check("porta", CheckStatus.OK, ANY_DETAIL)


# --- the absences check ----------------------------------------------------------------


def absence(identifier: int, kind: AbsenceKind, first: date, last: date) -> Absence:
    return Absence(id=identifier, kind=kind, first_day=first, last_day=last)


PAST_DAY_OFF = absence(1, AbsenceKind.DAY_OFF, date(2026, 10, 19), date(2026, 10, 19))
VACATION = absence(2, AbsenceKind.VACATION, date(2026, 11, 3), date(2026, 11, 14))
SICK_LEAVE = absence(3, AbsenceKind.SICK_LEAVE, date(2026, 11, 20), date(2026, 11, 20))
CURRENT_SICK_LEAVE = absence(4, AbsenceKind.SICK_LEAVE, date(2026, 10, 20), date(2026, 10, 23))


def absences_check(*held: Absence) -> Check:
    probing = Probing()
    probing.absences.book = AbsenceBook.of(held)
    return check(probing.run(), "absences")


def test_no_absences_entered_is_ok_and_names_the_file_read() -> None:
    absences = absences_check()

    assert absences.status is CheckStatus.OK
    assert english(absences.detail) == f"none ({ABSENCES})"


def test_the_absences_check_reads_the_store_once() -> None:
    probing = Probing()

    probing.run()

    assert probing.absences.loads == 1


def test_the_absences_check_counts_every_absence_and_names_the_next_one() -> None:
    absences = absences_check(SICK_LEAVE, PAST_DAY_OFF, VACATION)

    assert absences.status is CheckStatus.OK
    assert english(absences.detail) == f"3 entered, next: vacation 03.11\u201314.11 ({ABSENCES})"


def test_the_next_absence_is_the_one_after_today_not_the_one_under_way() -> None:
    absences = absences_check(CURRENT_SICK_LEAVE, SICK_LEAVE)

    assert english(absences.detail) == f"2 entered, next: sick leave 20.11 ({ABSENCES})"


def test_absences_entered_with_none_ahead_are_ok_and_say_so() -> None:
    absences = absences_check(PAST_DAY_OFF, CURRENT_SICK_LEAVE)

    assert absences.status is CheckStatus.OK
    assert english(absences.detail) == f"2 entered, none ahead ({ABSENCES})"


def test_an_absences_file_that_cannot_be_read_fails_the_probe_and_names_why() -> None:
    probing = Probing()
    probing.absences.broken = True

    report = probing.run()

    absences = check(report, "absences")
    assert absences.status is CheckStatus.FAILED
    assert english(absences.detail) == f"{FakeAbsenceStore.PATH}: not valid JSON"
    assert check(report, "chrome").status is CheckStatus.OK
    assert not report.ok


@pytest.mark.parametrize(
    ("held", "russian"),
    [
        ((), f"нет ({ABSENCES})"),
        ((VACATION,), f"внесено: 1, ближайшее: отпуск 03.11\u201314.11 ({ABSENCES})"),
        ((PAST_DAY_OFF,), f"внесено: 1, впереди нет ({ABSENCES})"),
    ],
    ids=["none", "next", "none-ahead"],
)
def test_the_absences_check_reads_in_russian(held: tuple[Absence, ...], russian: str) -> None:
    assert absences_check(*held).detail.in_language(Language.RU) == russian


def test_an_unreadable_absences_file_reads_in_russian_with_the_technical_reason() -> None:
    probing = Probing()
    probing.absences.broken = True

    detail = check(probing.run(), "absences").detail

    assert detail.in_language(Language.RU) == (
        f"{FakeAbsenceStore.PATH}: не прочитан: not valid JSON"
    )


# --- DryRun --------------------------------------------------------------------------


class Planning:
    """A dry run over the use case a run of ``kind`` would execute, wired to fakes.

    Given ``moments``, the run is scheduled: due at the kind's drawn moment, from its range.
    """

    def __init__(
        self,
        now: datetime,
        kind: RunKind = RunKind.CHECKIN,
        calendar_answer: bool | None = True,
        moments: DailyMoments | None = None,
    ) -> None:
        self.moments = moments
        self.clock = FakeClock(now)
        self.calendar = FakeCalendar(calendar_answer)
        self.notifier = FakeNotifier()
        self.client = FakeHorizonClient(desktop=DESKTOP)
        self.absences = FakeAbsenceStore()
        if moments is None:
            window = CHECKIN_WINDOW if kind is RunKind.CHECKIN else CHECKOUT_WINDOW
            self.runner = WindowedRun(
                self.calendar, self.clock, self.notifier, window, POLICY, absences=self.absences
            )
        else:
            moment = moments.check_in if kind is RunKind.CHECKIN else moments.check_out
            self.runner = WindowedRun(
                self.calendar,
                self.clock,
                self.notifier,
                window_from(moment, GRACE),
                POLICY,
                moment=moment,
                range_start=RANGE_STARTS[kind],
                absences=self.absences,
            )
        self.use_case: MorningCheckin | EveningCheckout = (
            MorningCheckin(self.client, self.clock, self.runner, DESKTOP, HOLD)
            if kind is RunKind.CHECKIN
            else EveningCheckout(self.client, self.clock, self.runner, DESKTOP)
        )

    def plan(self, *, force: bool = False) -> RunPlan:
        return DryRun(self.use_case, self.moments).plan(force=force)


@pytest.mark.parametrize("kind", list(RunKind))
def test_a_plan_lists_the_use_cases_steps_then_the_loops(kind: RunKind) -> None:
    planning = Planning(at(WEDNESDAY, 7, 55), kind)

    plan = planning.plan()

    assert plan.kind is kind
    assert plan.steps == (*planning.use_case.steps(), *planning.runner.steps())


@pytest.mark.parametrize("kind", list(RunKind))
@pytest.mark.parametrize("language", list(Language))
def test_every_step_of_a_plan_reads_in_every_language(kind: RunKind, language: Language) -> None:
    plan = Planning(at(WEDNESDAY, 7, 30), kind, moments=MOMENTS).plan()

    assert all(step.in_language(language).strip() for step in plan.steps)


@pytest.mark.parametrize("kind", list(RunKind))
def test_a_plan_touches_neither_the_portal_nor_the_owner(kind: RunKind) -> None:
    planning = Planning(at(WEDNESDAY, 17, 0), kind)

    planning.plan()

    assert planning.client.calls == []
    assert planning.notifier.sent == []


def test_a_checkin_plan_inside_the_window_would_run() -> None:
    plan = Planning(at(WEDNESDAY, 7, 55)).plan()

    assert plan.kind is RunKind.CHECKIN
    assert plan.decision is Decision.RUN
    assert plan.verdict_source is VerdictSource.CALENDAR
    assert plan.would_run
    assert not plan.forced


def test_a_checkout_plan_is_decided_in_the_checkout_window() -> None:
    plan = Planning(at(WEDNESDAY, 17, 0), RunKind.CHECKOUT).plan()

    assert plan.decision is Decision.RUN


def test_a_plan_outside_the_window_would_not_run_but_still_lists_its_steps() -> None:
    plan = Planning(at(WEDNESDAY, 12, 0)).plan()

    assert plan.decision is Decision.SKIP_LATE
    assert not plan.would_run
    assert plan.steps


def test_a_plan_before_the_window_would_not_run() -> None:
    plan = Planning(at(WEDNESDAY, 7, 54)).plan()

    assert plan.decision is Decision.SKIP_EARLY
    assert not plan.would_run


def test_a_plan_on_a_day_off_would_not_run() -> None:
    planning = Planning(at(SATURDAY, 7, 55), calendar_answer=False)

    plan = planning.plan()

    assert planning.calendar.asked == [SATURDAY]
    assert plan.decision is Decision.SKIP_NON_WORKING_DAY
    assert not plan.would_run


def test_a_plan_with_an_unreachable_calendar_names_the_fallback() -> None:
    plan = Planning(at(WEDNESDAY, 7, 55), calendar_answer=None).plan()

    assert plan.verdict_source is VerdictSource.WEEKDAY_FALLBACK
    assert plan.would_run


def test_a_forced_plan_runs_outside_the_window_and_asks_no_calendar() -> None:
    planning = Planning(at(SATURDAY, 12, 0), calendar_answer=False)

    plan = planning.plan(force=True)

    assert planning.calendar.asked == []
    assert plan.forced
    assert plan.decision is Decision.RUN
    assert plan.verdict_source is None
    assert plan.would_run


def test_a_plan_records_when_it_was_made() -> None:
    assert Planning(at(WEDNESDAY, 7, 56)).plan().at == at(WEDNESDAY, 7, 56)


def test_a_run_plan_would_run_only_on_run_or_retry() -> None:
    def plan(decision: Decision) -> RunPlan:
        return RunPlan(
            kind=RunKind.CHECKIN,
            at=at(WEDNESDAY, 7, 55),
            forced=False,
            decision=decision,
            verdict_source=VerdictSource.CALENDAR,
            steps=(),
        )

    assert [d for d in Decision if plan(d).would_run] == [Decision.RUN, Decision.RETRY]


# --- the day's drawn moments -----------------------------------------------------------


def test_the_schedule_detail_names_both_moments_of_today() -> None:
    assert english(schedule_detail(MOMENTS)) == "today 07:43 / 16:52"
    assert english(schedule_detail(DailyMoments(time(8, 5), time(17, 10)))) == "today 08:05 / 17:10"


def test_a_probe_given_the_days_moments_names_them_last() -> None:
    probing = Probing(moments=MOMENTS)

    report = probing.run()

    assert [item.name for item in report.checks] == [
        "portal",
        "calendar",
        "chrome",
        "absences",
        "schedule",
    ]
    schedule = check(report, "schedule")
    assert schedule.status is CheckStatus.OK
    assert english(schedule.detail) == "today 07:43 / 16:52"
    assert probing.client.calls == ["client_bundles", "browser_version"]
    assert report.ok


def test_a_probe_without_moments_checks_no_schedule() -> None:
    report = Probing().run()

    assert "schedule" not in [item.name for item in report.checks]


@pytest.mark.parametrize("kind", list(RunKind))
def test_a_plan_names_both_of_the_days_drawn_moments(kind: RunKind) -> None:
    plan = Planning(at(WEDNESDAY, 7, 30), kind, moments=MOMENTS).plan()

    assert plan.moments == MOMENTS


def test_a_plan_on_an_absence_day_would_not_run_and_asks_no_calendar() -> None:
    planning = Planning(at(WEDNESDAY, 7, 30), moments=MOMENTS)
    vacation = Absence(1, AbsenceKind.VACATION, WEDNESDAY, WEDNESDAY)
    planning.absences.book = AbsenceBook.of((vacation,))

    plan = planning.plan()

    assert (plan.decision, plan.verdict_source, plan.waits_until) == (
        Decision.SKIP_ABSENT,
        None,
        None,
    )
    assert not plan.would_run
    assert planning.calendar.asked == []


def test_a_plan_without_drawn_moments_names_none() -> None:
    assert Planning(at(WEDNESDAY, 7, 55)).plan().moments is None


def test_a_checkin_plan_from_the_range_start_waits_for_its_moment_then_runs() -> None:
    planning = Planning(at(WEDNESDAY, 7, 30), moments=MOMENTS)

    plan = planning.plan()

    assert plan.at == at(WEDNESDAY, 7, 30)
    assert plan.waits_until == at(WEDNESDAY, 7, 43)
    assert plan.decision is Decision.RUN
    assert plan.would_run
    assert planning.clock.sleeps == []
    # The loop's steps follow the attempt's: the absence check, then the wait.
    assert english(plan.steps[len(planning.use_case.steps()) + 1]) == (
        "wait until the drawn moment 07:43 if started from 07:30; earlier is skipped as too early"
    )


def test_a_checkout_plan_waits_for_the_check_out_moment() -> None:
    plan = Planning(at(WEDNESDAY, 16, 30), RunKind.CHECKOUT, moments=MOMENTS).plan()

    assert plan.waits_until == at(WEDNESDAY, 16, 52)
    assert plan.decision is Decision.RUN


def test_a_forced_plan_waits_for_no_moment_but_still_names_the_days_moments() -> None:
    plan = Planning(at(WEDNESDAY, 7, 30), moments=MOMENTS).plan(force=True)

    assert plan.waits_until is None
    assert plan.moments == MOMENTS
    assert plan.decision is Decision.RUN
