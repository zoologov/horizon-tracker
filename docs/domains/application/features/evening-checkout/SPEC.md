# Evening check-out

Logs the desktop's Windows session off from the tile menu and confirms it ended. A
desktop with no session is reported as already logged off.

## Source

`src/horizon_tracker/application/checkout.py`

## Specification

### Purpose

At the day's drawn check-out moment (the check-in plus `HT_SESSION_LENGTH_MINUTES` and
up to `HT_SESSION_EXTRA_MAX_MINUTES`, clipped into `HT_CHECKOUT_RANGE`, default
16:30-17:10) the accounting system must see the Windows logoff on the VM. The check-out ends the session that the morning check-in left running, and confirms the
end by the session state rather than by the click.

### How it works

`EveningCheckout.run(force=...)` creates one `_CheckoutAttempt` for the run and hands
it to `WindowedRun.run(RunKind.CHECKOUT, ...)`. The run loop waits for the drawn moment
and decides each attempt (see the [windowed run](../windowed-run/SPEC.md)). One attempt:

1. `client.login()`, then reads the desktop's session state;
2. on the run's first attempt, keeps that state as the state the run first saw;
3. if a session exists, `client.log_off(desktop)`, which answers with the path of its
   screenshot of the launch list without the session or `None`, and reads the state
   again.

The result:

- `checkout_succeeded(before, after)` holds → `SUCCEEDED`, the report carrying the
  path `log_off` answered with as `screenshot`, so the notifier sends the launch list
  as a photo with the text as its caption; with `None` it goes out as text;
- the run first saw no session → `SKIPPED` with `Reason.ALREADY_LOGGED_OFF`. A skip
  ends the run: there is nothing to log off and nothing to retry;
- otherwise → `FAILED` with `Reason.LOGOFF_NOT_CONFIRMED` and no screenshot, retried
  while the window allows.

The state the run first saw is kept across its attempts. If a log off went through but
its confirmation was lost, the retry finds no session and counts the run as the
check-out it was, not as "already logged off". That retry calls no `log_off`, so its
report carries no screenshot; the photo of the lost attempt is not kept across attempts.

`steps()` lists the four steps in the owner's words; `horizon checkout --dry-run`
prints them, followed by the loop's steps.

## Invariants

- A desktop that had no session when the run first looked is never reported as logged
  off by this run.
- `log_off` is called only when a session exists.
- Only a successful report carries the success screenshot, and only the one taken in
  the attempt that succeeded; a failed attempt reports the screenshot of its
  `HorizonClientError`, if any, as before. A forced run behaves the same.
- The memory of the first-seen state lives for one run; the next run starts fresh.

## API

Module `src/horizon_tracker/application/checkout.py`:

- `EveningCheckout(client: HorizonClient, clock: Clock, runner: WindowedRun, desktop:
  str)` — frozen:
  - `kind -> RunKind` — property, `RunKind.CHECKOUT`;
  - `run(*, force: bool = False) -> RunReport`;
  - `steps() -> tuple[str, ...]`.

`_CheckoutAttempt` is internal: the attempt callable that remembers the first-seen state.

## Testing

Tests: `tests/unit/application/test_checkout.py`, `tests/unit/test_cli.py`.

Scenarios (`tests/acceptance/features/evening_checkout.feature`):

- `Evening check-out logs the desktop off`
- `Evening check-out on an already logged-off desktop reports it and stops`

The drawn-moment scenarios in `randomised_moments.feature` run the check-out as well.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `session-state`, `windowed-run`
- Used by: `cli` (through the `application` package)

## Parent

`application` — [application README](../../README.md)
