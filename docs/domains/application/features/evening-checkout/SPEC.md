# Evening check-out

Logs the desktop's Windows session off from the tile menu and confirms it ended. A
desktop with no session is reported as already logged off.

## Source

`src/horizon_tracker/application/checkout.py`

## Specification

### Purpose

At 17:00 Moscow time the accounting system must see the Windows logoff on the VM. The
check-out ends the session that the morning check-in left running, and confirms the
end by the session state rather than by the click.

### How it works

`EveningCheckout.run(force=...)` creates one `_CheckoutAttempt` for the run and hands
it to `WindowedRun.run(RunKind.CHECKOUT, ...)`. One attempt:

1. `client.login()`, then reads the desktop's session state;
2. on the run's first attempt, keeps that state as the state the run first saw;
3. if a session exists, `client.log_off(desktop)` and reads the state again.

The result:

- `checkout_succeeded(before, after)` holds → `SUCCEEDED`;
- the run first saw no session → `SKIPPED` with `Reason.ALREADY_LOGGED_OFF`. A skip
  ends the run: there is nothing to log off and nothing to retry;
- otherwise → `FAILED` with `Reason.LOGOFF_NOT_CONFIRMED`, retried while the window
  allows.

The state the run first saw is kept across its attempts. If a log off went through but
its confirmation was lost, the retry finds no session and counts the run as the
check-out it was, not as "already logged off".

`steps()` lists the four steps in the owner's words; `horizon checkout --dry-run`
prints them, followed by the loop's steps.

## Invariants

- A desktop that had no session when the run first looked is never reported as logged
  off by this run.
- `log_off` is called only when a session exists.
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

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `session-state`, `windowed-run`
- Used by: `cli` (through the `application` package)

## Parent

`application` — [application README](../../README.md)
