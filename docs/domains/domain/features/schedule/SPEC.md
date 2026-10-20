# Schedule

Decides whether a run attempt may go ahead now: run, retry or skip, given its window,
the working-day verdict and the retry policy.

## Source

`src/horizon_tracker/domain/schedule.py`

## Specification

### Purpose

Each daily run has a window of local wall time: 07:55-08:00 for the check-in and
17:00-17:05 for the check-out. This module holds the one rule that says what attempt
number N should do at a given moment, so the run loop never decides by itself and the
rule is tested without a clock, a browser or a network.

### How it works

`decide(now, window, verdict, attempt, policy)` applies a fixed precedence:

1. a non-working day skips (`SKIP_NON_WORKING_DAY`), whatever the time;
2. an attempt number above `policy.max_attempts` gives up (`GIVE_UP`);
3. a wall time before `window.start` skips as early (`SKIP_EARLY`);
4. a wall time after `window.end` skips as late (`SKIP_LATE`);
5. otherwise the first attempt runs (`RUN`) and every later one retries (`RETRY`).

`now` is read as wall time (`now.time()`) in the zone the `Clock` port hands out, which
is Europe/Moscow in production. The domain never reads a clock: time is an argument.

`FIRST_ATTEMPT` (1) is public, so the run loop in `application/windowed_run.py` counts
attempts from this constant rather than from a copy of it.

## Invariants

- Both ends of a `Window` belong to it: `contains()` is `start <= moment <= end`.
- A `Window` whose start is not before its end raises `ValueError` at construction.
- A `RetryPolicy` with fewer than one attempt or a negative backoff raises `ValueError`.
- An attempt number below `FIRST_ATTEMPT` raises `ValueError`.
- An attempt outside the window is skipped and never performed late.
- A non-working day takes precedence over every other rule.

## API

Module `src/horizon_tracker/domain/schedule.py`:

- `FIRST_ATTEMPT` — `1`, the number attempts are counted from.
- `RunKind` — `StrEnum`: `CHECKIN`, `CHECKOUT`, named after the CLI commands.
- `Decision` — `StrEnum`: `RUN`, `RETRY`, `SKIP_EARLY`, `SKIP_LATE`,
  `SKIP_NON_WORKING_DAY`, `GIVE_UP`.
- `Window(start: time, end: time)` — frozen; `contains(moment: time) -> bool`.
- `RetryPolicy(max_attempts: int, backoff: timedelta)` — frozen.
- `decide(now, window, verdict, attempt, policy) -> Decision` — the rule above;
  `verdict` is a `WorkingDayVerdict` from `calendar.py`.

## Testing

Tests: `tests/unit/domain/test_schedule.py`. The module is inside the mutation gate
(`scripts/mutation.sh`, `[tool.mutmut]` in `pyproject.toml`).

Scenarios (`tests/acceptance/features/window_and_retries.feature`):

- `A failed attempt is retried inside the window`
- `A run that starts after its window is skipped and reported`

## Dependencies

Derived from the imports on reindex.

- Depends on: `working-day-calendar`
- Used by: `artifact-store`, `cli`, `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `ports`, `probe`, `run-report`, `settings`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
