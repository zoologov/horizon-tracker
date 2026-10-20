"""Checks whether the service could run, without ever logging in: a dependency probe and a dry run.

``Probe`` asks each dependency the one question it can answer without credentials: the
portal names the client bundles it serves, the calendar answers for today, the Chrome
binary is where the settings say. An unreachable calendar degrades the probe rather than
failing it, because a run falls back to the Mon-Fri rule.

``DryRun`` names what a run of one kind would do now -- the domain's decision for this
moment and the steps of an attempt -- and calls nothing on the Horizon client at all,
so it cannot log in. The settings themselves are validated before either is built: a
probe exists only for a configuration the composition root could read.
"""

# beadloom:domain=application

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from horizon_tracker.domain.calendar import VerdictSource, resolve
from horizon_tracker.domain.ports import (
    Clock,
    HorizonClient,
    HorizonClientError,
    WorkingDayCalendar,
)
from horizon_tracker.domain.schedule import Decision, RetryPolicy, RunKind, Window, decide

_FIRST_ATTEMPT = 1
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
    """Asks the portal, the calendar and the Chrome binary whether a run could go ahead."""

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
            answer = self.client.probe()
        except HorizonClientError as error:
            return Check("portal", CheckStatus.FAILED, f"no answer: {error.reason.value}")
        return Check("portal", CheckStatus.OK, answer)

    def _calendar(self) -> Check:
        today = self.clock.now().date()
        answer = self.calendar.is_working_day(today)
        if answer is None:
            detail = f"isdayoff.ru did not answer for {today}; runs fall back to the Mon-Fri rule"
            return Check("calendar", CheckStatus.DEGRADED, detail)
        day = "a working day" if answer else "a day off"
        return Check("calendar", CheckStatus.OK, f"isdayoff.ru: {today} is {day}")

    def _chrome(self) -> Check:
        if self.file_exists(self.chrome_path):
            return Check("chrome", CheckStatus.OK, f"found at {self.chrome_path}")
        return Check("chrome", CheckStatus.FAILED, f"not found at {self.chrome_path}")


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


@dataclass(frozen=True)
class DryRun:
    """Plans a run in one window without touching the portal; ``hold`` is the check-in's."""

    calendar: WorkingDayCalendar
    clock: Clock
    window: Window
    policy: RetryPolicy
    desktop: str
    hold: timedelta

    def plan(self, kind: RunKind, *, force: bool = False) -> RunPlan:
        """Decide as a run would now, and name the steps of its attempt; logs nothing in."""
        now = self.clock.now()
        if force:
            decision, source = Decision.RUN, None
        else:
            verdict = resolve(self.calendar.is_working_day(now.date()), now.date())
            decision = decide(now, self.window, verdict, _FIRST_ATTEMPT, self.policy)
            source = verdict.source
        return RunPlan(kind, now, force, decision, source, self._steps(kind))

    def _steps(self, kind: RunKind) -> tuple[str, ...]:
        attempt = _checkin_steps(self) if kind is RunKind.CHECKIN else _checkout_steps(self)
        return (
            *attempt,
            f"retry a failed attempt, up to {self.policy.max_attempts} attempts "
            f"{_seconds(self.policy.backoff)} s apart, while the window allows",
            "send one report to Telegram",
        )


def _checkin_steps(plan: DryRun) -> tuple[str, ...]:
    return (
        "log in to the Horizon portal",
        f"open desktop {plan.desktop!r} and wait for the Blast connection and a drawn desktop",
        f"hold the desktop open for {_seconds(plan.hold)} s so the Windows logon completes",
        "read the session state, then disconnect (the Windows session keeps running)",
        "log in again and confirm the session is DISCONNECTED",
    )


def _checkout_steps(plan: DryRun) -> tuple[str, ...]:
    return (
        "log in to the Horizon portal",
        f"read the session state of desktop {plan.desktop!r}; stop if there is no session",
        "log off from the tile menu and confirm the dialog",
        "confirm the session is gone (NO_SESSION)",
    )


def _seconds(span: timedelta) -> str:
    return f"{span.total_seconds():g}"
