"""Drives one daily run through its window: decide each attempt, retry failures, send one report.

Both use cases share this loop and differ only in what one attempt does. The loop asks
the calendar once, lets the domain's ``decide`` rule on every attempt, waits the
policy's backoff through the ``Clock`` port, and sends exactly one report whatever
the run came to.

A scheduled run is due at the day's drawn ``moment`` and its window opens there. Its
timer fires at ``range_start``, so a run started between the two waits for the moment
in one ``Clock.sleep`` before its first attempt; a run started before ``range_start``
is skipped as too early and waits for nothing. Its report names the moment as
``planned_at``. A run built without a moment keeps its fixed window and never waits.

A failed attempt is retried while the window and the policy allow; once they do not,
the run reports the last failure rather than a skip, because the attempt was made. A
``--force`` run treats the day as a working day and the whole day as its window, and
waits for no moment.

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
from horizon_tracker.domain.messages import Message
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
    """The decision a run's first attempt would take, asked at ``at``, and its calendar source.

    ``verdict_source`` is ``None`` for a forced run, which asks no calendar. ``waits_until``
    is the drawn moment a run started at ``at`` would sleep until first, and the decision
    is the one taken then; ``None`` when the run would not wait.
    """

    at: datetime
    decision: Decision
    verdict_source: VerdictSource | None
    waits_until: datetime | None = None


@dataclass(frozen=True)
class WindowedRun:
    """The run loop shared by both use cases, over the calendar, the clock and the notifier.

    ``moment`` and ``range_start`` come together: a scheduled run waits from
    ``range_start`` until ``moment``, where ``window`` opens (build it with
    ``window_from``). Without them the run keeps its fixed ``window`` and never waits.
    """

    calendar: WorkingDayCalendar
    clock: Clock
    notifier: Notifier
    window: Window
    policy: RetryPolicy
    moment: time | None = None
    range_start: time | None = None

    def __post_init__(self) -> None:
        if (self.moment is None) != (self.range_start is None):
            raise ValueError("moment and range_start come together, or neither is given")
        if self.moment is None or self.range_start is None:
            return
        if self.window.start != self.moment:
            msg = (
                f"the window must open at the moment {self.moment}, "
                f"not at {self.window.start}: build it with window_from"
            )
            raise ValueError(msg)
        if self.range_start > self.moment:
            msg = f"range_start {self.range_start} is after the moment {self.moment}"
            raise ValueError(msg)

    def run(self, kind: RunKind, attempt: Attempt, *, force: bool = False) -> RunReport:
        """Wait for the drawn moment, make the attempts the window allows, send one report."""
        verdict = self._verdict(force)
        now = self.clock.now()
        waits_until = self._waits_until(now, verdict)
        if waits_until is not None:
            self.clock.sleep((waits_until - now).total_seconds())
        result = self._attempts(kind, attempt, verdict)
        report = RunReport(
            kind=kind,
            outcome=result.outcome,
            at=result.at,
            verdict_source=_source(verdict),
            reason=result.reason,
            screenshot=result.screenshot,
            planned_at=None if force else self.moment,
        )
        logger.info("%s run %s (%s)", kind, report.outcome, report.reason)
        self.notifier.send(report)
        return report

    def first_decision(self, *, force: bool = False) -> FirstDecision:
        """What ``run`` would decide on its first attempt; waits for nothing, sends nothing."""
        verdict = self._verdict(force)
        now = self.clock.now()
        waits_until = self._waits_until(now, verdict)
        decided_at = now if waits_until is None else waits_until
        decision = self._decide_at(decided_at, FIRST_ATTEMPT, verdict)
        return FirstDecision(now, decision, _source(verdict), waits_until)

    def steps(self) -> tuple[Message, ...]:
        """What the loop adds around the attempts, as messages for the dry run."""
        retries = (
            Message(
                "plan.step.retry",
                {
                    "attempts": self.policy.max_attempts,
                    "seconds": in_seconds(self.policy.backoff),
                },
            ),
            Message("plan.step.report"),
        )
        if self.moment is None or self.range_start is None:
            return retries
        wait = Message(
            "plan.step.wait",
            {"moment": f"{self.moment:%H:%M}", "start": f"{self.range_start:%H:%M}"},
        )
        return (wait, *retries)

    def _verdict(self, force: bool) -> WorkingDayVerdict | None:
        """Today's calendar verdict; ``None`` for a forced run, which asks no calendar."""
        if force:
            return None
        today = self.clock.now().date()
        return resolve(self.calendar.is_working_day(today), today)

    def _waits_until(self, now: datetime, verdict: WorkingDayVerdict | None) -> datetime | None:
        """The drawn moment a run started at ``now`` sleeps until first, or ``None``.

        Only a scheduled run on a working day, started from ``range_start`` and before
        the moment, waits; a forced run (no verdict) never does.
        """
        if verdict is None or not verdict.is_working:
            return None
        if self.moment is None or self.range_start is None:
            return None
        if not self.range_start <= now.time() < self.moment:
            return None
        return datetime.combine(now.date(), self.moment, tzinfo=now.tzinfo)

    def _decide(self, attempt: int, verdict: WorkingDayVerdict | None) -> Decision:
        return self._decide_at(self.clock.now(), attempt, verdict)

    def _decide_at(
        self, now: datetime, attempt: int, verdict: WorkingDayVerdict | None
    ) -> Decision:
        if verdict is None:
            return decide(now, _WHOLE_DAY, _FORCED_WORKING_DAY, attempt, self.policy)
        return decide(now, self.window, verdict, attempt, self.policy)

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
