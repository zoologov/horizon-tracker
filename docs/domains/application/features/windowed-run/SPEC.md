# Windowed run

The run loop both use cases share: skips a day an absence covers before the calendar is
asked, asks the calendar once, waits for the day's drawn moment, decides each attempt,
retries failures inside the window and builds exactly one report, which it sends unless
it is a day-level skip of a run told to keep those silent.

## Source

`src/horizon_tracker/application/windowed_run.py`

## Specification

### Purpose

The check-in and the check-out differ only in what one attempt does. Everything around
the attempt is the same: whether the owner entered an absence for today, whether today is
a working day, the wait for the drawn moment, whether the window allows an attempt now, how failures are retried, and the
single report at the end. `WindowedRun`
holds that shared part once. The dry run reads it rather than copying it.

### How it works

`run(kind, attempt, *, force=False)`:

0. Reads the `AbsenceStore` once. When an absence covers today (`domain.absence.covering`
   over the book, the date of `Clock.now()`), the run ends at once: a `SKIPPED` report
   with `reason=absence_reason(absence.kind)` (`ON_VACATION`, `ON_SICK_LEAVE`,
   `ON_DAY_OFF`), `absence` set, `verdict_source=None` and the drawn `planned_at`. The
   calendar is not asked, nothing is attempted and nothing is waited for; step 5 then
   reports it. A store that raises `AbsenceStoreError` is logged as `absences could not
   be read (AbsenceStoreError); the run goes on as if none were entered` (the type only:
   `horizon probe` names the cause) and read as empty. A forced run reads no absence.
1. Asks the `WorkingDayCalendar` once for today (the date of `Clock.now()`) and turns
   the answer into a verdict with `resolve()`. A forced run asks no calendar.
2. Waits for the drawn moment. The systemd timer fires at `range_start`, the start of
   the range the moment was drawn from. On a working day, a run started at
   `range_start <= now < moment` sleeps once through `Clock.sleep` until `moment`, where
   its window opens. A run started before `range_start` or at or after `moment`, a
   non-working day and a forced run do not wait.
3. Asks `decide()` what attempt 1 should do. While the decision is `RUN` or `RETRY`,
   it calls `attempt()`:
   - `SUCCEEDED` or `SKIPPED` ends the run with that result;
   - `FAILED` is kept as the last failure. The next attempt number is decided; if it
     may go ahead, the loop waits `policy.backoff` through `Clock.sleep` and decides
     again, because the window may have closed during the wait.
4. When the loop stops, the result is the last failure if an attempt was made, and
   otherwise a `SKIPPED` result whose reason maps the decision: `SKIP_NON_WORKING_DAY`
   → `NON_WORKING_DAY`, `SKIP_EARLY` → `TOO_EARLY`, `SKIP_LATE` → `WINDOW_MISSED`.
5. Builds one `RunReport`, logs its outcome, sends it through the `Notifier` and
   returns it. Under `notify_day_skips=False` a day-level skip
   (`RunReport.is_day_level_skip`: `NON_WORKING_DAY` or an absence reason) is logged
   (`checkout report not sent: the morning run reports a skipped day`) and not sent;
   `TOO_EARLY`, `WINDOW_MISSED` and every run that made an attempt are still sent. The report's `planned_at` is the drawn moment the run was due at, set
   whether or not the run reached its window, and `None` for a forced run. The
   report's `screenshot` is copied from the result the run ended on: the success
   screenshot of a confirmed attempt, the failure screenshot of the last failed one, or
   none for a skip. The screenshots of earlier attempts do not reach the report.

A failed attempt is retried while the window and the policy allow. Once they do not,
the run reports the last failure rather than a skip, because the attempt was made. The
window bounds the start of an attempt, not its end: an attempt started 15 seconds
before the window closes may finish after it has closed. Its retry, due after the
backoff, then falls outside the window and is not made.

An attempt that raises `HorizonClientError` becomes a `FAILED` result with the error's
reason and screenshot. Any other exception becomes a `FAILED` result with
`Reason.UNEXPECTED`. This is the only broad handler in the code, so that an error no
port names still ends in the run's one report. It logs the exception's type and
traceback frames and leaves the message out, because an adapter's exception text may
quote what it typed.

A `--force` run reads no absence, treats the day as a working day and the whole day (`00:00` to
`23:59:59.999999`) as its window, and waits for no moment. Its report names no calendar
source (`verdict_source` is `None`) and no planned moment (`planned_at` is `None`).
There the attempt count is the bound.

`first_decision(*, force=False)` returns the decision `run` would take on its first
attempt, with the time it was asked, the calendar source and the moment the run would
first wait until. When the run would wait, the decision is the one taken at that
moment. On a day an absence covers it is `Decision.SKIP_ABSENT` with no calendar source
and no wait, and the calendar is not asked. It never sleeps, makes no attempt and sends
nothing, but it reads the absences and asks the calendar unless the run is forced.
`steps()` names what the loop adds around the attempts, as `Message`s (catalogue keys
`plan.step.absences`, `plan.step.wait`, `plan.step.retry`, and `plan.step.report` or,
under `notify_day_skips=False`, `plan.step.report.no_day_skip`). The dry run in `probe.py` plans both and the CLI
prints them in the configured language.

## Invariants

- Exactly one report is built per `run()`, whatever the run came to; it is sent unless it
  is a day-level skip under `notify_day_skips=False`.
- A day an absence covers asks no calendar and makes no attempt; the store is read at
  most once per run, and never for a forced run.
- A run sleeps for its moment at most once, before its first attempt. A forced run and a
  non-working day never wait.
- The calendar is asked at most once per run, and never for a forced run.
- No attempt starts outside the window: every attempt, including a retry after the
  backoff, is decided by `decide()` immediately before it is made.
- Attempts are counted from `domain.schedule.FIRST_ATTEMPT`; the loop holds no copy.
- `first_decision()` and the first decision of `run()` agree for the same world.
- A log line written by the loop never contains an exception message.

## API

Module `src/horizon_tracker/application/windowed_run.py`:

- `AttemptResult(outcome: Outcome, at: datetime, reason: Reason | None = None,
  screenshot: Path | None = None)` — frozen; what one attempt observed. `screenshot`
  is the success screenshot of a `SUCCEEDED` result or the failure screenshot of a
  `FAILED` one.
- `Attempt` — `Callable[[], AttemptResult]`.
- `FirstDecision(at: datetime, decision: Decision, verdict_source: VerdictSource |
  None, waits_until: datetime | None = None)` — frozen. `waits_until` is the drawn
  moment a run started at `at` would sleep until first, and `decision` is the one taken
  then; `None` when the run would not wait.
- `WindowedRun(calendar, clock, notifier, window, policy, moment: time | None = None,
  range_start: time | None = None, *, absences: AbsenceStore, notify_day_skips: bool =
  True)` — frozen; `absences` and `notify_day_skips` are keyword-only. `moment` and `range_start` come together
  or not at all; given, `window` must open at `moment` (build it with
  `domain.schedule.window_from(moment, grace)`) and `range_start` must not be after
  `moment`, otherwise `ValueError`. Without them the run keeps its fixed window and
  never waits.
  - `run(kind: RunKind, attempt: Attempt, *, force: bool = False) -> RunReport` — on a
    working day, a scheduled run started at `range_start <= now < moment` first calls
    `Clock.sleep((moment - now).total_seconds())` once; before `range_start` it waits
    for nothing and `decide()` skips it as `SKIP_EARLY`; at or after `moment` it does not
    wait. A non-working day and a forced run never wait. The report's `planned_at` is
    `moment` for every non-forced run, `None` for a forced one or a run without a moment;
  - `first_decision(*, force: bool = False) -> FirstDecision` — never sleeps;
  - `steps() -> tuple[Message, ...]` — the absence check first, in English `skip the day
    if an absence entered through the bot covers it, before the calendar is asked`; then
    a scheduled loop names its wait, `wait until the drawn moment HH:MM if started from
    HH:MM; earlier is skipped as too early`.
- `in_seconds(span: timedelta) -> str` — a span as a bare number of seconds (`120`,
  `0.5`); `checkin.py` uses it in its step list as well.

The CLI builds one `WindowedRun` per command with `RETRY_POLICY` (3 attempts, 30 s
apart), the day's drawn moment of the run kind, `window=window_from(moment,
settings.window_grace)` and `range_start` set to the start of `HT_CHECKIN_RANGE` or
`HT_CHECKOUT_RANGE`, `absences=adapters.absences` (the JSON store over
`HT_STATE_DIR/absences.json`) and `notify_day_skips=True` for `horizon checkin`, `False`
for `horizon checkout`: the morning reports a skipped day, the evening is silent (the
owner's ruling, HT-012). It always passes the moment, so the mode without a moment is used
only by tests. A `--force` run keeps the drawn moment and is told to ignore it by
`run(force=True)`.

## Testing

Tests: `tests/unit/application/test_windowed_run.py`, including
`test_the_first_decision_is_the_one_the_run_then_takes`, and
`tests/unit/application/test_windowed_run_absences.py` (the absence verdict, the
unreadable store, `notify_day_skips`).

Scenarios:

- `tests/acceptance/features/window_and_retries.feature`:
  - `A failed attempt is retried inside the window`
  - `A run that starts after its window is skipped and reported`
- `tests/acceptance/features/randomised_moments.feature`:
  - `A run started at the range start waits until its drawn moment before the first attempt`
  - `A dry run names the drawn moment of the day`
- `tests/acceptance/features/production_calendar.feature`:
  - `A day the calendar marks as a holiday is skipped with a notice`
  - `When the calendar is unreachable the weekday rule decides and says so`
- `tests/acceptance/features/absences.feature`:
  - `A morning run on a day of vacation is skipped with the kind named`
  - `An evening run on a skipped day sends nothing`
  - `A day after the absence ends is a working day again`
- `tests/acceptance/features/notifications.feature`:
  - `A failed run sends the reason and a screenshot`

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence`, `messages`, `ports`, `run-report`, `schedule`, `working-day-calendar`
- Used by: `evening-checkout`, `morning-checkin`, `probe`, `cli` (through the `application` package)

## Parent

`application` — [application README](../../README.md)
