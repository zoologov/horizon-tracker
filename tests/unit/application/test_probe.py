"""Tests for the checks that log nothing in: the dependency probe and the dry-run plan."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.probe import (
    Check,
    CheckStatus,
    DryRun,
    Probe,
    ProbeReport,
    RunPlan,
)
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Reason
from horizon_tracker.domain.schedule import Decision, RetryPolicy, RunKind, Window
from tests.unit.fakes import FakeCalendar, FakeClock, FakeHorizonClient

MSK = ZoneInfo("Europe/Moscow")
WEDNESDAY = date(2026, 10, 21)
SATURDAY = date(2026, 10, 24)
DESKTOP = "DEV desktop"
CHROME = Path("/usr/bin/google-chrome")
CHECKIN_WINDOW = Window(start=time(7, 55), end=time(8, 0))
CHECKOUT_WINDOW = Window(start=time(17, 0), end=time(17, 5))
POLICY = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=30))
HOLD = timedelta(seconds=120)


def at(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MSK)


# --- Probe ---------------------------------------------------------------------------


class Probing:
    """A probe over fakes: a reachable portal and calendar, Chrome installed."""

    def __init__(self, calendar_answer: bool | None = True, chrome_found: bool = True) -> None:
        self.client = FakeHorizonClient(desktop=DESKTOP)
        self.calendar = FakeCalendar(calendar_answer)
        self.clock = FakeClock(at(WEDNESDAY, 12, 0))
        self.looked_for: list[Path] = []
        self._chrome_found = chrome_found

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
        )
        return probe.run()


def check(report: ProbeReport, name: str) -> Check:
    (found,) = [item for item in report.checks if item.name == name]
    return found


def test_probe_checks_portal_calendar_and_chrome_in_that_order() -> None:
    report = Probing().run()

    assert [item.name for item in report.checks] == ["portal", "calendar", "chrome"]
    assert all(item.status is CheckStatus.OK for item in report.checks)
    assert report.ok


def test_probe_reads_the_portal_without_logging_in() -> None:
    probing = Probing()

    report = probing.run()

    assert probing.client.calls == ["probe"]
    assert "fake-2312" in check(report, "portal").detail


def test_an_unreachable_portal_fails_the_probe_and_names_the_reason() -> None:
    probing = Probing()
    probing.client.fail_on("probe", HorizonClientError(Reason.PORTAL_UNREACHABLE))

    report = probing.run()

    portal = check(report, "portal")
    assert portal.status is CheckStatus.FAILED
    assert Reason.PORTAL_UNREACHABLE.value in portal.detail
    assert not report.ok


def test_the_calendar_is_asked_about_today() -> None:
    probing = Probing()

    report = probing.run()

    assert probing.calendar.asked == [WEDNESDAY]
    assert "working day" in check(report, "calendar").detail


def test_the_calendar_names_a_day_off() -> None:
    report = Probing(calendar_answer=False).run()

    calendar = check(report, "calendar")
    assert calendar.status is CheckStatus.OK
    assert "day off" in calendar.detail


def test_an_unreachable_calendar_degrades_the_probe_without_failing_it() -> None:
    report = Probing(calendar_answer=None).run()

    calendar = check(report, "calendar")
    assert calendar.status is CheckStatus.DEGRADED
    assert "Mon-Fri" in calendar.detail
    assert report.ok


def test_chrome_is_looked_for_at_the_configured_path() -> None:
    probing = Probing()

    report = probing.run()

    assert probing.looked_for == [CHROME]
    assert str(CHROME) in check(report, "chrome").detail


def test_a_missing_chrome_fails_the_probe() -> None:
    report = Probing(chrome_found=False).run()

    chrome = check(report, "chrome")
    assert chrome.status is CheckStatus.FAILED
    assert str(CHROME) in chrome.detail
    assert not report.ok


def test_a_probe_report_is_ok_unless_a_check_failed() -> None:
    ok = Check("a", CheckStatus.OK, "")
    degraded = Check("b", CheckStatus.DEGRADED, "")
    failed = Check("c", CheckStatus.FAILED, "")

    assert ProbeReport((ok, degraded)).ok
    assert not ProbeReport((ok, failed, degraded)).ok


# --- DryRun --------------------------------------------------------------------------


def dry_run(
    now: datetime,
    window: Window = CHECKIN_WINDOW,
    calendar_answer: bool | None = True,
) -> tuple[DryRun, FakeCalendar]:
    calendar = FakeCalendar(calendar_answer)
    planner = DryRun(
        calendar=calendar,
        clock=FakeClock(now),
        window=window,
        policy=POLICY,
        desktop=DESKTOP,
        hold=HOLD,
    )
    return planner, calendar


def test_a_checkin_plan_inside_the_window_would_run() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 7, 55))

    plan = planner.plan(RunKind.CHECKIN)

    assert plan.kind is RunKind.CHECKIN
    assert plan.decision is Decision.RUN
    assert plan.verdict_source is VerdictSource.CALENDAR
    assert plan.would_run
    assert not plan.forced


def test_a_checkin_plan_names_its_steps_in_order() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 7, 55))

    steps = planner.plan(RunKind.CHECKIN).steps

    text = "\n".join(steps)
    assert text.index("log in") < text.index("open desktop") < text.index("hold")
    assert text.index("hold") < text.index("disconnect") < text.index("DISCONNECTED")
    assert repr(DESKTOP) in text
    assert "120 s" in text
    assert "log off" not in text


def test_a_checkout_plan_logs_off_and_never_holds() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 17, 0), window=CHECKOUT_WINDOW)

    plan = planner.plan(RunKind.CHECKOUT)

    text = "\n".join(plan.steps)
    assert plan.decision is Decision.RUN
    assert text.index("log in") < text.index("log off") < text.index("NO_SESSION")
    assert "hold" not in text
    assert "disconnect" not in text


@pytest.mark.parametrize("kind", list(RunKind))
def test_every_plan_names_the_retry_policy_and_the_one_report(kind: RunKind) -> None:
    planner, _ = dry_run(at(WEDNESDAY, 7, 55))

    text = "\n".join(planner.plan(kind).steps)

    assert "3 attempts" in text
    assert "30 s apart" in text
    assert text.rstrip().endswith("send one report to Telegram")


def test_a_plan_outside_the_window_would_not_run_but_still_lists_its_steps() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 12, 0))

    plan = planner.plan(RunKind.CHECKIN)

    assert plan.decision is Decision.SKIP_LATE
    assert not plan.would_run
    assert plan.steps


def test_a_plan_before_the_window_would_not_run() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 7, 54))

    plan = planner.plan(RunKind.CHECKIN)

    assert plan.decision is Decision.SKIP_EARLY
    assert not plan.would_run


def test_a_plan_on_a_day_off_would_not_run() -> None:
    planner, calendar = dry_run(at(SATURDAY, 7, 55), calendar_answer=False)

    plan = planner.plan(RunKind.CHECKIN)

    assert calendar.asked == [SATURDAY]
    assert plan.decision is Decision.SKIP_NON_WORKING_DAY
    assert not plan.would_run


def test_a_plan_with_an_unreachable_calendar_names_the_fallback() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 7, 55), calendar_answer=None)

    plan = planner.plan(RunKind.CHECKIN)

    assert plan.verdict_source is VerdictSource.WEEKDAY_FALLBACK
    assert plan.would_run


def test_a_forced_plan_runs_outside_the_window_and_asks_no_calendar() -> None:
    planner, calendar = dry_run(at(SATURDAY, 12, 0), calendar_answer=False)

    plan = planner.plan(RunKind.CHECKIN, force=True)

    assert calendar.asked == []
    assert plan.forced
    assert plan.decision is Decision.RUN
    assert plan.verdict_source is None
    assert plan.would_run


def test_a_plan_records_when_it_was_made() -> None:
    planner, _ = dry_run(at(WEDNESDAY, 7, 56))

    assert planner.plan(RunKind.CHECKIN).at == at(WEDNESDAY, 7, 56)


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
