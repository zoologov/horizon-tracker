"""Checks whether the service could run, without ever logging in: a dependency probe and a dry run.

``Probe`` asks each dependency the one question it can answer without credentials: the
portal names the client bundles it serves, the calendar answers for today, the Chrome
binary is where the settings say, starts headless and names its version, and the
absences file can be read. What is measured is the client bundles and the browser
version; no portal version is read. An unreachable calendar degrades the probe rather than
failing it, because a run falls back to the Mon-Fri rule. An absences file that cannot be
read or parsed fails it, because the owner's absences are then unknown. Given the day's
drawn moments, the probe names them last, as the ``schedule`` check; it does not draw
them, the composition root does.

``DryRun`` names what a run would do now and calls nothing on the Horizon client at
all, so it cannot log in. It plans the very use case a run would execute: the decision
is ``WindowedRun.first_decision``, the steps are the use case's own list followed by the
loop's. Neither is restated here, so the plan cannot describe a run that no longer exists.
The plan carries the day's drawn moments it is given and, from the loop, the moment a
run started now would wait for.

The settings themselves are validated before either is built: a probe exists only for a
configuration the composition root could read.
"""

# beadloom:domain=application

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from horizon_tracker.application.windowed_run import WindowedRun
from horizon_tracker.domain.absence import Absence, next_after
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.messages import Message
from horizon_tracker.domain.ports import (
    AbsenceStore,
    AbsenceStoreError,
    Clock,
    HorizonClient,
    HorizonClientError,
    WorkingDayCalendar,
)
from horizon_tracker.domain.report import absence_reason, absence_span
from horizon_tracker.domain.schedule import DailyMoments, Decision, RunKind

_WOULD_RUN = frozenset({Decision.RUN, Decision.RETRY})


class CheckStatus(StrEnum):
    """How one probed dependency answered."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class Check:
    """One dependency's answer: its name, its status and what it said, as a message.

    ``name`` and ``status`` are identifiers; ``label`` and ``status_label`` are the same
    as messages, made with the check, so a name the catalogue lacks fails where the
    check is made rather than when it is shown.
    """

    name: str
    status: CheckStatus
    detail: Message
    label: Message = field(init=False, repr=False, compare=False)
    status_label: Message = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", Message(f"probe.check.{self.name}"))
        object.__setattr__(self, "status_label", Message(f"probe.status.{self.status}"))


@dataclass(frozen=True)
class ProbeReport:
    """The probe's checks, in the order they ran; it passes unless one of them failed."""

    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        """Whether no check failed; a degraded dependency still lets the service run."""
        return all(item.status is not CheckStatus.FAILED for item in self.checks)


@dataclass(frozen=True)
class Probe:
    """Asks the portal, the calendar, Chrome and the absences whether a run could go ahead.

    ``absences_file`` is the file ``absences`` reads, named on the line so the owner knows
    which file was read. ``moments`` are today's drawn moments; given, they are named as the
    last check.
    """

    client: HorizonClient
    calendar: WorkingDayCalendar
    clock: Clock
    chrome_path: Path
    file_exists: Callable[[Path], bool]
    absences: AbsenceStore
    absences_file: Path
    moments: DailyMoments | None = None

    def run(self) -> ProbeReport:
        """Probe every dependency once, whatever the others answered."""
        checks = (self._portal(), self._calendar(), self._chrome(), self._absences())
        if self.moments is None:
            return ProbeReport(checks)
        schedule = Check("schedule", CheckStatus.OK, schedule_detail(self.moments))
        return ProbeReport((*checks, schedule))

    def _portal(self) -> Check:
        try:
            bundles = self.client.client_bundles()
        except HorizonClientError as error:
            detail = Message("probe.portal.no_answer", {"reason": error.reason.value})
            return Check("portal", CheckStatus.FAILED, detail)
        detail = Message("probe.portal.bundles", {"bundles": ", ".join(bundles)})
        return Check("portal", CheckStatus.OK, detail)

    def _calendar(self) -> Check:
        today = self.clock.now().date()
        answer = self.calendar.is_working_day(today)
        if answer is None:
            detail = Message("probe.calendar.no_answer", {"day": today})
            return Check("calendar", CheckStatus.DEGRADED, detail)
        key = "probe.calendar.working_day" if answer else "probe.calendar.day_off"
        return Check("calendar", CheckStatus.OK, Message(key, {"day": today}))

    def _chrome(self) -> Check:
        """Chrome is found at its path, then started to name its version: the deploy smoke."""
        where = self.chrome_path
        if not self.file_exists(where):
            return Check(
                "chrome", CheckStatus.FAILED, Message("probe.chrome.not_found", {"path": where})
            )
        try:
            version = self.client.browser_version()
        except HorizonClientError as error:
            detail = Message(
                "probe.chrome.did_not_start", {"path": where, "reason": error.reason.value}
            )
            return Check("chrome", CheckStatus.FAILED, detail)
        detail = Message("probe.chrome.started", {"version": version, "path": where})
        return Check("chrome", CheckStatus.OK, detail)

    def _absences(self) -> Check:
        """How many absences are entered and which comes next; a file that cannot be read fails."""
        try:
            book = self.absences.load()
        except AbsenceStoreError as error:
            detail = Message(
                "probe.absences.unreadable", {"path": error.path, "reason": error.detail}
            )
            return Check("absences", CheckStatus.FAILED, detail)
        today = self.clock.now().date()
        detail = _absences_detail(book.absences, today, self.absences_file)
        return Check("absences", CheckStatus.OK, detail)


def _absences_detail(held: tuple[Absence, ...], today: date, where: Path) -> Message:
    """The absences held, counted, with the first one that starts after ``today``."""
    if not held:
        return Message("probe.absences.none", {"path": where})
    ahead = next_after(held, today)
    if ahead is None:
        return Message("probe.absences.entered", {"count": len(held), "path": where})
    kind = Message(f"reason.{absence_reason(ahead.kind)}")
    fields = {"count": len(held), "kind": kind, "span": absence_span(ahead), "path": where}
    return Message("probe.absences.entered_next", fields)


@dataclass(frozen=True)
class RunPlan:
    """What a run of ``kind`` would do at ``at``: the decision, its calendar source, the steps.

    ``verdict_source`` is ``None`` for a forced plan, which asks no calendar. ``waits_until``
    is the drawn moment the run would sleep until first, ``None`` when it would not wait;
    ``moments`` are the day's drawn pair, ``None`` when the plan was given none.
    """

    kind: RunKind
    at: datetime
    forced: bool
    decision: Decision
    verdict_source: VerdictSource | None
    steps: tuple[Message, ...]
    waits_until: datetime | None = None
    moments: DailyMoments | None = None

    @property
    def would_run(self) -> bool:
        """Whether an attempt would be made now."""
        return self.decision in _WOULD_RUN


class PlannedRun(Protocol):
    """A use case the dry run can plan: its kind, its run loop, the steps of one attempt."""

    @property
    def kind(self) -> RunKind:
        """Which daily run this is."""
        ...

    @property
    def runner(self) -> WindowedRun:
        """The loop that decides, retries and reports."""
        ...

    def steps(self) -> tuple[Message, ...]:
        """What one attempt does, as messages the owner reads in their language."""
        ...


@dataclass(frozen=True)
class DryRun:
    """Plans the use case a run would execute, without touching the portal or the owner.

    ``moments`` are today's drawn moments, named in the plan as given; never drawn here.
    """

    use_case: PlannedRun
    moments: DailyMoments | None = None

    def plan(self, *, force: bool = False) -> RunPlan:
        """Decide as the run's first attempt would now, and name its steps; logs nothing in."""
        runner = self.use_case.runner
        first = runner.first_decision(force=force)
        return RunPlan(
            kind=self.use_case.kind,
            at=first.at,
            forced=force,
            decision=first.decision,
            verdict_source=first.verdict_source,
            steps=(*self.use_case.steps(), *runner.steps()),
            waits_until=first.waits_until,
            moments=self.moments,
        )


def schedule_detail(moments: DailyMoments) -> Message:
    """Today's drawn check-in and check-out as a message: ``today 07:43 / 16:52`` in English."""
    return Message(
        "probe.schedule",
        {"check_in": f"{moments.check_in:%H:%M}", "check_out": f"{moments.check_out:%H:%M}"},
    )
