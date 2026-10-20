"""Drives one daily run through its window: decide each attempt, retry failures, send one report.

Both use cases share this loop and differ only in what one attempt does. The loop asks
the calendar once, lets the domain's ``decide`` rule on every attempt, waits the
policy's backoff through the ``Clock`` port, and sends exactly one report whatever
the run came to.

A failed attempt is retried while the window and the policy allow; once they do not,
the run reports the last failure rather than a skip, because the attempt was made. A
``--force`` run treats the day as a working day and the whole day as its window.

The dry run reads the loop rather than copying it: ``first_decision`` is the decision
``run`` would take on its first attempt now, and ``steps`` names what the loop adds
around the attempts.
"""

# beadloom:domain=application

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from horizon_tracker.domain.calendar import VerdictSource, WorkingDayVerdict, resolve
from horizon_tracker.domain.ports import Clock, HorizonClientError, Notifier, WorkingDayCalendar
from horizon_tracker.domain.report import Outcome, Reason, RunReport
from horizon_tracker.domain.schedule import (
    FIRST_ATTEMPT,
    Decision,
    RetryPolicy,
    RunKind,
    Window,
    decide,
)

logger = logging.getLogger(__name__)

_PERFORM = frozenset({Decision.RUN, Decision.RETRY})
_SKIP_REASON = {
    Decision.SKIP_NON_WORKING_DAY: Reason.NON_WORKING_DAY,
    Decision.SKIP_EARLY: Reason.TOO_EARLY,
    Decision.SKIP_LATE: Reason.WINDOW_MISSED,
}

# A --force run: the whole day is its window and the day counts as working. The
# verdict's source is never reported; a forced report names no source at all.
_WHOLE_DAY = Window(start=time.min, end=time.max)
_FORCED_WORKING_DAY = WorkingDayVerdict(is_working=True, source=VerdictSource.CALENDAR)


@dataclass(frozen=True)
class AttemptResult:
    """What one attempt observed: its outcome, when, and why if it did not succeed.

    ``FAILED`` is retried while the window and the policy allow; ``SUCCEEDED`` and
    ``SKIPPED`` end the run.
    """

    outcome: Outcome
    at: datetime
    reason: Reason | None = None
    screenshot: Path | None = None


Attempt = Callable[[], AttemptResult]


@dataclass(frozen=True)
class FirstDecision:
    """The decision a run's first attempt would take at ``at``, and its calendar source.

    ``verdict_source`` is ``None`` for a forced run, which asks no calendar.
    """

    at: datetime
    decision: Decision
    verdict_source: VerdictSource | None


@dataclass(frozen=True)
class WindowedRun:
    """The run loop shared by both use cases, over the calendar, the clock and the notifier."""

    calendar: WorkingDayCalendar
    clock: Clock
    notifier: Notifier
    window: Window
    policy: RetryPolicy

    def run(self, kind: RunKind, attempt: Attempt, *, force: bool = False) -> RunReport:
        """Make the run's attempts as the window allows and send its one report."""
        verdict = self._verdict(force)
        result = self._attempts(kind, attempt, verdict)
        report = RunReport(
            kind=kind,
            outcome=result.outcome,
            at=result.at,
            verdict_source=_source(verdict),
            reason=result.reason,
            screenshot=result.screenshot,
        )
        logger.info("%s run %s (%s)", kind, report.outcome, report.reason)
        self.notifier.send(report)
        return report

    def first_decision(self, *, force: bool = False) -> FirstDecision:
        """What ``run`` would decide on its first attempt now; makes no attempt, sends nothing."""
        verdict = self._verdict(force)
        return FirstDecision(
            self.clock.now(), self._decide(FIRST_ATTEMPT, verdict), _source(verdict)
        )

    def steps(self) -> tuple[str, ...]:
        """What the loop adds around the attempts, in the owner's words."""
        return (
            f"retry a failed attempt, up to {self.policy.max_attempts} attempts "
            f"{in_seconds(self.policy.backoff)} s apart, while the window allows",
            "send one report to Telegram",
        )

    def _verdict(self, force: bool) -> WorkingDayVerdict | None:
        """Today's calendar verdict; ``None`` for a forced run, which asks no calendar."""
        if force:
            return None
        today = self.clock.now().date()
        return resolve(self.calendar.is_working_day(today), today)

    def _decide(self, attempt: int, verdict: WorkingDayVerdict | None) -> Decision:
        if verdict is None:
            return decide(self.clock.now(), _WHOLE_DAY, _FORCED_WORKING_DAY, attempt, self.policy)
        return decide(self.clock.now(), self.window, verdict, attempt, self.policy)

    def _attempts(
        self, kind: RunKind, attempt: Attempt, verdict: WorkingDayVerdict | None
    ) -> AttemptResult:
        number = FIRST_ATTEMPT
        decision = self._decide(number, verdict)
        last_failure: AttemptResult | None = None
        while decision in _PERFORM:
            result = self._make(kind, attempt, number)
            if result.outcome is not Outcome.FAILED:
                return result
            last_failure = result
            number += 1
            decision = self._decide(number, verdict)
            if decision in _PERFORM:
                self.clock.sleep(self.policy.backoff.total_seconds())
                decision = self._decide(number, verdict)
        logger.info("%s attempt %d: %s", kind, number, decision)
        if last_failure is not None:
            return last_failure
        return AttemptResult(Outcome.SKIPPED, self.clock.now(), _SKIP_REASON[decision])

    def _make(self, kind: RunKind, attempt: Attempt, number: int) -> AttemptResult:
        try:
            return attempt()
        except HorizonClientError as error:
            logger.warning("%s attempt %d failed: %s", kind, number, error.reason)
            return AttemptResult(Outcome.FAILED, self.clock.now(), error.reason, error.screenshot)
        except Exception as error:
            # Deliberately broad, and the only such handler: an error no port names must
            # still end in the run's one report, as a failed attempt with UNEXPECTED.
            # The message is left out on purpose: an adapter's exception text may quote
            # what it typed. The type and the frames are enough to find the fault.
            frames = "".join(traceback.format_tb(error.__traceback__))
            logger.error(
                "%s attempt %d failed unexpectedly: %s\n%s",
                kind,
                number,
                type(error).__name__,
                frames,
            )
            return AttemptResult(Outcome.FAILED, self.clock.now(), Reason.UNEXPECTED)


def in_seconds(span: timedelta) -> str:
    """A span as a bare number of seconds for the owner to read: ``120``, ``0.5``."""
    return f"{span.total_seconds():g}"


def _source(verdict: WorkingDayVerdict | None) -> VerdictSource | None:
    return None if verdict is None else verdict.source
