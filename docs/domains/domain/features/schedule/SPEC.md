# Schedule

Draws each day's check-in and check-out moments, builds a run's window from its moment,
and decides whether a run attempt may go ahead now: run, retry or skip, given its
window, the working-day verdict and the retry policy.

## Source

`src/horizon_tracker/domain/schedule.py`

## Specification

### Purpose

Each working day has its own check-in and check-out moment, drawn from configured
ranges of local wall time, so the runs do not happen at the same minute every day. A
run's window opens at its moment and closes after a grace. This module holds the draw,
the window built from a moment, and the one rule that says what attempt number N should
do at a given moment. The run loop never decides by itself, and every part is tested
without a clock, a browser or a network.

### The daily draw

`draw_moments(day, seed, checkin_range, session_length, extra_max, checkout_range)`
computes `hmac-sha256(seed, day.isoformat())` and reads two 32-bit words of the digest:

1. the check-in is `checkin_range.start` plus `word1 % (range minutes + 1)` minutes, so
   any minute of the range, both ends included, can be drawn;
2. the extra minutes are `word2 % (extra_max minutes + 1)`;
3. the check-out is the check-in plus `session_length` plus the extra minutes, raised to
   `checkout_range.start` if it falls before it and lowered to `checkout_range.end` if it
   falls after it.

The draw is a pure function of the date and the seed. The morning and the evening run,
the probe and a dry run of the same date therefore name the same pair without sharing
any state. With the deployed defaults (check-in 07:30-08:10, session 540 minutes, up to
10 extra minutes, check-out 16:30-17:10) the check-out falls 540 to 550 minutes after
the check-in, and it is clipped to 17:10 when the sum would pass the end of the range.

`window_from(moment, grace)` is the window of a run due at `moment`: it opens at the
moment and closes `grace` later.

### How an attempt is decided

`decide(now, window, verdict, attempt, policy)` applies a fixed precedence:

1. a non-working day skips (`SKIP_NON_WORKING_DAY`), whatever the time;
2. an attempt number above `policy.max_attempts` gives up (`GIVE_UP`);
3. a wall time before `window.start` skips as early (`SKIP_EARLY`);
4. a wall time after `window.end` skips as late (`SKIP_LATE`);
5. otherwise the first attempt runs (`RUN`) and every later one retries (`RETRY`).

`now` is read as wall time (`now.time()`) in the zone the `Clock` port hands out, which
is the zone configured by `HT_TIMEZONE`. The domain never reads a clock: time is an
argument.

`FIRST_ATTEMPT` (1) is public, so the run loop in `application/windowed_run.py` counts
attempts from this constant rather than from a copy of it.

## Invariants

- Both ends of a `Window` belong to it: `contains()` is `start <= moment <= end`.
- A `Window` whose start is not before its end raises `ValueError` at construction.
- A `RetryPolicy` with fewer than one attempt or a negative backoff raises `ValueError`.
- An attempt number below `FIRST_ATTEMPT` raises `ValueError`.
- An attempt outside the window is skipped and never performed late.
- A non-working day takes precedence over every other rule.
- The same date and seed always draw the same `DailyMoments`.
- A drawn check-in lies inside `checkin_range` and a drawn check-out inside
  `checkout_range`, both ends included.
- The check-out is at least `session_length` after the check-in whenever the end of
  `checkout_range` allows it.
- Both drawn moments and both ends of a `TimeRange` are whole minutes.
- The draw refuses a check-out range that does not start after the check-in range ends.
- A refusal a configured value can reach is a `ScheduleError`: a range out of order, a
  check-out range that does not follow the check-in one, a session or a grace that is
  not positive, a window past midnight. Its `reason` is a `Message` (`schedule.*` keys,
  see the `messages` SPEC), so a reader gets it in their language; `str(error)` is the
  English text. A refusal only code can reach (an empty seed, a duration with seconds, a
  negative extra, a range end with seconds) stays a plain `ValueError`.

## API

Module `src/horizon_tracker/domain/schedule.py`:

- `FIRST_ATTEMPT` — `1`, the number attempts are counted from.
- `ScheduleError(reason: Message)` — a `ValueError` whose `reason` is the refusal as a
  message; `str()` is `reason` in English.
- `RunKind` — `StrEnum`: `CHECKIN`, `CHECKOUT`, named after the CLI commands.
- `Decision` — `StrEnum`: `RUN`, `RETRY`, `SKIP_EARLY`, `SKIP_LATE`,
  `SKIP_NON_WORKING_DAY`, `GIVE_UP`.
- `Window(start: time, end: time)` — frozen; `contains(moment: time) -> bool`.
- `RetryPolicy(max_attempts: int, backoff: timedelta)` — frozen.
- `decide(now, window, verdict, attempt, policy) -> Decision` — the rule above;
  `verdict` is a `WorkingDayVerdict` from `calendar.py`.
- `TimeRange(start: time, end: time)` — frozen; the span a moment is drawn from, both
  ends included; refuses `start >= end` (`ScheduleError`, `schedule.range_order`) and
  ends that are not whole minutes (`ValueError`).
- `DailyMoments(check_in: time, check_out: time)` — frozen; the day's drawn pair.
- `draw_moments(day: date, seed: bytes, checkin_range: TimeRange, session_length:
  timedelta, extra_max: timedelta, checkout_range: TimeRange) -> DailyMoments` — a pure
  function of `day` and `seed`: `digest = hmac-sha256(seed, day.isoformat())`; the
  check-in is `checkin_range.start` plus `digest[0:4]` (big-endian) modulo the range's
  minutes + 1; the check-out is the check-in plus `session_length` plus `digest[4:8]`
  modulo `extra_max`'s minutes + 1, clipped into `checkout_range`. Both moments are whole
  minutes. The check-out is never less than `session_length` after the check-in when
  that fits the range, and is the range end when it does not. Refuses a
  `session_length` that is not positive (`ScheduleError`,
  `schedule.session_length_not_positive`) and a `checkout_range` that does not start
  after `checkin_range` ends (`ScheduleError`, `schedule.checkout_after_checkin`); refuses
  an empty seed, a negative `extra_max` and either duration not in whole minutes
  (`ValueError`).
- `window_from(moment: time, grace: timedelta) -> Window` — the window of a run due at
  `moment`: `Window(moment, moment + grace)`; refuses a grace that is not positive
  (`schedule.grace_not_positive`) and a window that would cross midnight
  (`schedule.window_crosses_midnight`), both as `ScheduleError`.

## Testing

Tests: `tests/unit/domain/test_schedule.py`, `tests/unit/domain/test_moments.py`. The
module is inside the mutation gate (`scripts/mutation.sh`, `[tool.mutmut]` in
`pyproject.toml`).

Scenarios:

- `tests/acceptance/features/window_and_retries.feature`:
  - `A failed attempt is retried inside the window`
  - `A run that starts after its window is skipped and reported`
- `tests/acceptance/features/randomised_moments.feature`:
  - `The check-in moment of a working day lies inside the check-in range`
  - `Two different days draw different check-in moments`
  - `The check-out moment is nine hours plus up to ten minutes after the check-in`
  - `A check-out past the end of its range is clipped to the end`
  - `The same date gives the same drawn moments in two separate runs`

## Dependencies

Derived from the imports on reindex.

- Depends on: `working-day-calendar`
- Used by: `artifact-store`, `cli`, `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `ports`, `probe`, `run-report`, `settings`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
