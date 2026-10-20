"""Drives one daily run through its window: decide each attempt, retry failures, send one report.

Both use cases share this loop and differ only in what one attempt does. The loop asks
the calendar once, lets the domain's ``decide`` rule on every attempt, waits the
policy's backoff through the ``Clock`` port, and sends exactly one report whatever
the run came to.

A failed attempt is retried while the window and the policy allow; once they do not,
the run reports the last failure rather than a skip, because the attempt was made. A
``--force`` run treats the day as a working day and the whole day as its window.
"""

# beadloom:domain=application

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

from horizon_tracker.domain.calendar import VerdictSource, WorkingDayVerdict, resolve
from horizon_tracker.domain.ports import Clock, HorizonClientError, Notifier, WorkingDayCalendar
from horizon_tracker.domain.report import Outcome, Reason, RunReport
from horizon_tracker.domain.schedule import Decision, RetryPolicy, RunKind, Window, decide

logger = logging.getLogger(__name__)

_PERFORM = frozenset({Decision.RUN, Decision.RETRY})
_SKIP_REASON = {
    Decision.SKIP_NON_WORKING_DAY: Reason.NON_WORKING_DAY,
    Decision.SKIP_EARLY: Reason.WINDOW_MISSED,
    Decision.SKIP_LATE: Reason.WINDOW_MISSED,
}
_FIRST_ATTEMPT = 1

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
class WindowedRun:
    """The run loop shared by both use cases, over the calendar, the clock and the notifier."""

    calendar: WorkingDayCalendar
    clock: Clock
    notifier: Notifier
    window: Window
    policy: RetryPolicy

    def run(self, kind: RunKind, attempt: Attempt, *, force: bool = False) -> RunReport:
        """Make the run's attempts as the window allows and send its one report."""
        verdict = None if force else self._verdict()
        result = self._attempts(kind, attempt, verdict)
        report = RunReport(
            kind=kind,
            outcome=result.outcome,
            at=result.at,
            verdict_source=None if verdict is None else verdict.source,
            reason=result.reason,
            screenshot=result.screenshot,
        )
        logger.info("%s run %s (%s)", kind, report.outcome, report.reason)
        self.notifier.send(report)
        return report

    def _verdict(self) -> WorkingDayVerdict:
        today = self.clock.now().date()
        return resolve(self.calendar.is_working_day(today), today)

    def _decide(self, attempt: int, verdict: WorkingDayVerdict | None) -> Decision:
        if verdict is None:
            return decide(self.clock.now(), _WHOLE_DAY, _FORCED_WORKING_DAY, attempt, self.policy)
        return decide(self.clock.now(), self.window, verdict, attempt, self.policy)

    def _attempts(
        self, kind: RunKind, attempt: Attempt, verdict: WorkingDayVerdict | None
    ) -> AttemptResult:
        number = _FIRST_ATTEMPT
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
