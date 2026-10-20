# Windowed run

The run loop both use cases share: asks the calendar once, decides each attempt,
retries failures inside the window and sends exactly one report.

## Source

`src/horizon_tracker/application/windowed_run.py`

## Specification

### Purpose

The check-in and the check-out differ only in what one attempt does. Everything around
the attempt is the same: whether today is a working day, whether the window allows an
attempt now, how failures are retried, and the single report at the end. `WindowedRun`
holds that shared part once. The dry run reads it rather than copying it.

### How it works

`run(kind, attempt, *, force=False)`:

1. Asks the `WorkingDayCalendar` once for today (the date of `Clock.now()`) and turns
   the answer into a verdict with `resolve()`. A forced run asks no calendar.
2. Asks `decide()` what attempt 1 should do. While the decision is `RUN` or `RETRY`,
   it calls `attempt()`:
   - `SUCCEEDED` or `SKIPPED` ends the run with that result;
   - `FAILED` is kept as the last failure. The next attempt number is decided; if it
     may go ahead, the loop waits `policy.backoff` through `Clock.sleep` and decides
     again, because the window may have closed during the wait.
3. When the loop stops, the result is the last failure if an attempt was made, and
   otherwise a `SKIPPED` result whose reason maps the decision: `SKIP_NON_WORKING_DAY`
   → `NON_WORKING_DAY`, `SKIP_EARLY` → `TOO_EARLY`, `SKIP_LATE` → `WINDOW_MISSED`.
4. Builds one `RunReport`, logs its outcome, sends it through the `Notifier` and
   returns it.

A failed attempt is retried while the window and the policy allow. Once they do not,
the run reports the last failure rather than a skip, because the attempt was made. The
window bounds the start of an attempt, not its end: an attempt started at 07:59:45 may
finish after 08:00.

An attempt that raises `HorizonClientError` becomes a `FAILED` result with the error's
reason and screenshot. Any other exception becomes a `FAILED` result with
`Reason.UNEXPECTED`. This is the only broad handler in the code, so that an error no
port names still ends in the run's one report. It logs the exception's type and
traceback frames and leaves the message out, because an adapter's exception text may
quote what it typed.

A `--force` run treats the day as a working day and the whole day (`00:00` to
`23:59:59.999999`) as its window. Its report names no calendar source
(`verdict_source` is `None`). There the attempt count is the bound.

`first_decision(*, force=False)` returns the decision `run` would take on its first
attempt now, with the time and the calendar source. It makes no attempt and sends
nothing, but it does ask the calendar unless the run is forced. `steps()` names what the
loop adds around the attempts, in the owner's words. The dry run in `probe.py` prints
both.

## Invariants

- Exactly one report is sent per `run()`, whatever the run came to.
- The calendar is asked at most once per run, and never for a forced run.
- No attempt starts outside the window: every attempt, including a retry after the
  backoff, is decided by `decide()` immediately before it is made.
- Attempts are counted from `domain.schedule.FIRST_ATTEMPT`; the loop holds no copy.
- `first_decision()` and the first decision of `run()` agree for the same world.
- A log line written by the loop never contains an exception message.

## API

Module `src/horizon_tracker/application/windowed_run.py`:

- `AttemptResult(outcome: Outcome, at: datetime, reason: Reason | None = None,
  screenshot: Path | None = None)` — frozen; what one attempt observed.
- `Attempt` — `Callable[[], AttemptResult]`.
- `FirstDecision(at: datetime, decision: Decision, verdict_source: VerdictSource |
  None)` — frozen.
- `WindowedRun(calendar, clock, notifier, window, policy)` — frozen:
  - `run(kind: RunKind, attempt: Attempt, *, force: bool = False) -> RunReport`;
  - `first_decision(*, force: bool = False) -> FirstDecision`;
  - `steps() -> tuple[str, ...]`.
- `in_seconds(span: timedelta) -> str` — a span as a bare number of seconds (`120`,
  `0.5`); `checkin.py` uses it in its step list as well.

The CLI builds one `WindowedRun` per command with `RETRY_POLICY` (3 attempts, 30 s
apart) and the window of the run kind.

## Testing

Tests: `tests/unit/application/test_windowed_run.py`, including
`test_the_first_decision_is_the_one_the_run_then_takes`.

Scenarios:

- `tests/acceptance/features/window_and_retries.feature`:
  - `A failed attempt is retried inside the window`
  - `A run that starts after its window is skipped and reported`
- `tests/acceptance/features/production_calendar.feature`:
  - `A day the calendar marks as a holiday is skipped with a notice`
  - `When the calendar is unreachable the weekday rule decides and says so`
- `tests/acceptance/features/notifications.feature`:
  - `A failed run sends the reason and a screenshot`

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `working-day-calendar`
- Used by: `evening-checkout`, `morning-checkin`, `probe`, `cli` (through the `application` package)

## Parent

`application` — [application README](../../README.md)
