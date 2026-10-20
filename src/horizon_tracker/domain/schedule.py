"""Decides whether a run attempt may go ahead now: run, retry, or skip, given its window.

A run has a window of local wall time (07:55-08:00 for the check-in, 17:00-17:05 for
the check-out). Both ends belong to the window. An attempt outside it is skipped and
never performed late; inside it, the first attempt runs and later ones retry until the
policy's attempts are spent. A non-working day is skipped whatever the time.

Time is an argument: the domain never reads a clock. ``now`` is read as wall time in
the window's zone, which is the zone the ``Clock`` port hands out (Europe/Moscow).
"""
# beadloom:domain=domain

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum

from horizon_tracker.domain.calendar import WorkingDayVerdict

# Attempts are counted from one. Public, so the run loop counts from this value, not a copy.
FIRST_ATTEMPT = 1


class RunKind(StrEnum):
    """Which of the two daily runs: named after the CLI commands."""

    CHECKIN = "checkin"
    CHECKOUT = "checkout"


class Decision(StrEnum):
    """What a run attempt should do now."""

    RUN = "run"
    RETRY = "retry"
    SKIP_EARLY = "skip_early"
    SKIP_LATE = "skip_late"
    SKIP_NON_WORKING_DAY = "skip_non_working_day"
    GIVE_UP = "give_up"


@dataclass(frozen=True)
class Window:
    """A span of local wall time in which a run may start; both ends included."""

    start: time
    end: time

    def __post_init__(self) -> None:
        if self.start >= self.end:
            msg = f"window start {self.start} must be before its end {self.end}"
            raise ValueError(msg)

    def contains(self, moment: time) -> bool:
        """Return whether ``moment`` falls inside the window, ends included."""
        return self.start <= moment <= self.end


@dataclass(frozen=True)
class RetryPolicy:
    """How many attempts a run gets, and how long to wait between them."""

    max_attempts: int
    backoff: timedelta

    def __post_init__(self) -> None:
        if self.max_attempts < FIRST_ATTEMPT:
            msg = f"max_attempts must be at least {FIRST_ATTEMPT}, got {self.max_attempts}"
            raise ValueError(msg)
        if self.backoff < timedelta(0):
            msg = f"backoff must not be negative, got {self.backoff}"
            raise ValueError(msg)


def decide(
    now: datetime,
    window: Window,
    verdict: WorkingDayVerdict,
    attempt: int,
    policy: RetryPolicy,
) -> Decision:
    """Decide what attempt number ``attempt`` (counted from 1) should do at ``now``.

    Precedence: a non-working day skips; spent attempts give up; outside the window
    skips as early or late; otherwise the first attempt runs and later ones retry.
    """
    if attempt < FIRST_ATTEMPT:
        msg = f"attempt is counted from {FIRST_ATTEMPT}, got {attempt}"
        raise ValueError(msg)
    if not verdict.is_working:
        return Decision.SKIP_NON_WORKING_DAY
    if attempt > policy.max_attempts:
        return Decision.GIVE_UP
    wall_time = now.time()
    if wall_time < window.start:
        return Decision.SKIP_EARLY
    if not window.contains(wall_time):
        return Decision.SKIP_LATE
    if attempt == FIRST_ATTEMPT:
        return Decision.RUN
    return Decision.RETRY
