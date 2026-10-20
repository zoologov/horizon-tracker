"""Checks whether the service could run, without ever logging in: a dependency probe and a dry run.

``Probe`` asks each dependency the one question it can answer without credentials: the
portal names the client bundles it serves, the calendar answers for today, the Chrome
binary is where the settings say, starts headless and names its version. What is
measured is the client bundles and the browser version; no portal version is read. An
unreachable calendar degrades the probe rather than failing it, because a run falls back
to the Mon-Fri rule.

``DryRun`` names what a run would do now and calls nothing on the Horizon client at
all, so it cannot log in. It plans the very use case a run would execute: the decision
is ``WindowedRun.first_decision``, the steps are the use case's own list followed by the
loop's. Neither is restated here, so the plan cannot describe a run that no longer exists.

The settings themselves are validated before either is built: a probe exists only for a
configuration the composition root could read.
"""

# beadloom:domain=application

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from horizon_tracker.application.windowed_run import WindowedRun
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import (
    Clock,
    HorizonClient,
    HorizonClientError,
    WorkingDayCalendar,
)
from horizon_tracker.domain.schedule import Decision, RunKind

_WOULD_RUN = frozenset({Decision.RUN, Decision.RETRY})


class CheckStatus(StrEnum):
    """How one probed dependency answered."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class Check:
    """One dependency's answer: its name, its status and what it said."""

    name: str
    status: CheckStatus
    detail: str


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
    """Asks the portal, the calendar and Chrome whether a run could go ahead."""

    client: HorizonClient
    calendar: WorkingDayCalendar
    clock: Clock
    chrome_path: Path
    file_exists: Callable[[Path], bool]

    def run(self) -> ProbeReport:
        """Probe every dependency once, whatever the others answered."""
        return ProbeReport((self._portal(), self._calendar(), self._chrome()))

    def _portal(self) -> Check:
        try:
            bundles = self.client.client_bundles()
        except HorizonClientError as error:
            return Check("portal", CheckStatus.FAILED, f"no answer: {error.reason.value}")
        return Check("portal", CheckStatus.OK, "client bundles: " + ", ".join(bundles))

    def _calendar(self) -> Check:
        today = self.clock.now().date()
        answer = self.calendar.is_working_day(today)
        if answer is None:
            detail = f"isdayoff.ru did not answer for {today}; runs fall back to the Mon-Fri rule"
            return Check("calendar", CheckStatus.DEGRADED, detail)
        day = "a working day" if answer else "a day off"
        return Check("calendar", CheckStatus.OK, f"isdayoff.ru: {today} is {day}")

    def _chrome(self) -> Check:
        """Chrome is found at its path, then started to name its version: the deploy smoke."""
        where = self.chrome_path
        if not self.file_exists(where):
            return Check("chrome", CheckStatus.FAILED, f"not found at {where}")
        try:
            version = self.client.browser_version()
        except HorizonClientError as error:
            detail = f"found at {where} but did not start: {error.reason.value}"
            return Check("chrome", CheckStatus.FAILED, detail)
        return Check("chrome", CheckStatus.OK, f"Chrome {version} started from {where}")


@dataclass(frozen=True)
class RunPlan:
    """What a run of ``kind`` would do at ``at``: the decision, its calendar source, the steps.

    ``verdict_source`` is ``None`` for a forced plan, which asks no calendar.
    """

    kind: RunKind
    at: datetime
    forced: bool
    decision: Decision
    verdict_source: VerdictSource | None
    steps: tuple[str, ...]

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

    def steps(self) -> tuple[str, ...]:
        """What one attempt does, in the owner's words."""
        ...


@dataclass(frozen=True)
class DryRun:
    """Plans the use case a run would execute, without touching the portal or the owner."""

    use_case: PlannedRun

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
        )
