"""Decides when a run may go ahead: today's drawn moment, its window, and run, retry or skip.

Each working day draws one check-in moment from its range (07:30-08:10 as deployed) and
one check-out moment from its own (16:30-17:10), at least a session length apart when that
fits. The draw is a pure function of the date and a seed (hmac-sha256), so the morning
and the evening runs agree on the pair without sharing any state. A run's window opens
at its moment and closes after a grace. Both ends belong to the window. An attempt
outside it is skipped and never performed late; inside it, the first attempt runs and
later ones retry until the policy's attempts are spent. A non-working day is skipped
whatever the time.

Time is an argument: the domain never reads a clock. ``now`` is read as wall time in
the window's zone, which is the zone the ``Clock`` port hands out (Europe/Moscow).

A refusal a configured value can reach is a ``ScheduleError``: its reason is a message,
so whoever shows it reads it in their language; its ``str`` stays English.
"""
# beadloom:domain=domain

import hmac
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from horizon_tracker.domain.calendar import WorkingDayVerdict
from horizon_tracker.domain.messages import Language, Message

# Attempts are counted from one. Public, so the run loop counts from this value, not a copy.
FIRST_ATTEMPT = 1

_MINUTE = timedelta(minutes=1)
# The draw reads two 32-bit words of the digest: the check-in offset, then the extra minutes.
_WORD = 4
_DIGEST = "sha256"
# Any date serves for arithmetic on wall times: a drawn moment or a window never leaves it.
_REFERENCE_DAY = date(2000, 1, 1)


class ScheduleError(ValueError):
    """A value the schedule refuses, with the reason as a message a person reads.

    Raised for the refusals a configured value can reach: a range out of order, a
    check-out range before the check-in one, a session or a grace that is not positive,
    a window past midnight. A refusal only code can reach (an empty seed, a duration in
    seconds, a negative extra) stays a plain ``ValueError``.
    """

    def __init__(self, reason: Message) -> None:
        self.reason = reason
        super().__init__(reason.in_language(Language.EN))


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


@dataclass(frozen=True)
class TimeRange:
    """A span of local wall time a moment is drawn from, in whole minutes; both ends included."""

    start: time
    end: time

    def __post_init__(self) -> None:
        if not (_is_whole_minute(self.start) and _is_whole_minute(self.end)):
            msg = f"range ends must be whole minutes, got {self.start}-{self.end}"
            raise ValueError(msg)
        if self.start >= self.end:
            reason = Message("schedule.range_order", {"start": self.start, "end": self.end})
            raise ScheduleError(reason)


@dataclass(frozen=True)
class DailyMoments:
    """The day's drawn pair: when the check-in and the check-out run, in local wall time."""

    check_in: time
    check_out: time


def draw_moments(
    day: date,
    seed: bytes,
    checkin_range: TimeRange,
    session_length: timedelta,
    extra_max: timedelta,
    checkout_range: TimeRange,
) -> DailyMoments:
    """Draw ``day``'s check-in and check-out moments from ``seed``, to the minute.

    The check-in falls anywhere in its range. The check-out is the check-in plus the
    session plus 0 to ``extra_max``, clipped into its range: never shorter than the
    session when that fits, and the end of the range when it does not.
    """
    _check_draw_parameters(seed, checkin_range, session_length, extra_max, checkout_range)
    digest = hmac.new(seed, day.isoformat().encode(), _DIGEST).digest()
    check_in = _at(checkin_range.start) + _pick(digest[:_WORD], _span(checkin_range))
    extra = _pick(digest[_WORD : 2 * _WORD], extra_max)
    check_out = min(
        max(check_in + session_length + extra, _at(checkout_range.start)),
        _at(checkout_range.end),
    )
    return DailyMoments(check_in=check_in.time(), check_out=check_out.time())


def window_from(moment: time, grace: timedelta) -> Window:
    """The window of a run due at ``moment``: it opens then and closes ``grace`` later."""
    if grace <= timedelta(0):
        raise ScheduleError(Message("schedule.grace_not_positive", {"grace": grace}))
    end = _at(moment) + grace
    if end.date() != _REFERENCE_DAY:
        reason = Message("schedule.window_crosses_midnight", {"moment": moment, "grace": grace})
        raise ScheduleError(reason)
    return Window(start=moment, end=end.time())


def _check_draw_parameters(
    seed: bytes,
    checkin_range: TimeRange,
    session_length: timedelta,
    extra_max: timedelta,
    checkout_range: TimeRange,
) -> None:
    if not seed:
        raise ValueError("the draw needs a non-empty seed")
    if session_length <= timedelta(0):
        reason = Message("schedule.session_length_not_positive", {"session_length": session_length})
        raise ScheduleError(reason)
    if extra_max < timedelta(0):
        msg = f"extra_max must not be negative, got {extra_max}"
        raise ValueError(msg)
    for name, duration in (("session_length", session_length), ("extra_max", extra_max)):
        if duration % _MINUTE:
            msg = f"{name} must be whole minutes, got {duration}"
            raise ValueError(msg)
    if checkout_range.start <= checkin_range.end:
        reason = Message(
            "schedule.checkout_after_checkin",
            {"checkout_start": checkout_range.start, "checkin_end": checkin_range.end},
        )
        raise ScheduleError(reason)


def _is_whole_minute(moment: time) -> bool:
    return moment.second == 0 and moment.microsecond == 0


def _at(moment: time) -> datetime:
    return datetime.combine(_REFERENCE_DAY, moment)


def _span(time_range: TimeRange) -> timedelta:
    return _at(time_range.end) - _at(time_range.start)


def _pick(word: bytes, span: timedelta) -> timedelta:
    """A whole number of minutes from 0 to ``span``, both included, chosen by ``word``."""
    return _MINUTE * (int.from_bytes(word, "big") % (span // _MINUTE + 1))
