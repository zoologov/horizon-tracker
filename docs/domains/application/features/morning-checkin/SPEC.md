# Morning check-in

Opens the desktop over Blast, holds it until Windows logs on, disconnects without
logging off and confirms the session runs on.

## Source

`src/horizon_tracker/application/checkin.py`

## Specification

### Purpose

At the day's drawn check-in moment (inside `HT_CHECKIN_RANGE`, default 07:30-08:10) the
accounting system must see a Windows logon on the VM. A portal login is not enough: the desktop has to be opened over Blast and drawn. Then
the client lets go and leaves the Windows session running until the evening check-out.

### How it works

`MorningCheckin.run(force=...)` hands one attempt to `WindowedRun.run(RunKind.CHECKIN,
...)`. The run loop waits for the drawn moment and decides each attempt (see the
[windowed run](../windowed-run/SPEC.md)). One attempt:

1. `client.login()`;
2. `client.open_desktop(desktop)`, which returns once Blast is connected and the
   desktop is drawn, answering with the path of its screenshot of the opened desktop
   or `None`; the time is recorded as the moment the desktop opened;
3. `clock.sleep(hold)`, so the Windows logon completes, then reads the session state
   while the desktop is open;
4. `client.disconnect()`, called in a `finally` block, so the client lets go even when
   the hold or the read fails;
5. `client.login()` again, because the disconnect closed the client, and reads the
   state the disconnect left.

The attempt succeeds when `checkin_succeeded(while_open, after_disconnect)` holds, that
is the transition `CONNECTED` -> `DISCONNECTED`. The report then carries the moment the
desktop opened and, as `screenshot`, the path `open_desktop` answered with, so the
notifier sends the opened desktop as a photo with the text as its caption; with `None`
the report goes out as text. Any other pair of states is `FAILED` with
`Reason.DESKTOP_DID_NOT_OPEN` and no screenshot: the photo of an opened desktop is not
evidence for a check-in the broker did not confirm. A `HorizonClientError` from any
step is turned into a failed attempt by the run loop and retried while the window
allows.

`steps()` lists the five steps in the owner's words; `horizon checkin --dry-run` prints
them, followed by the loop's steps.

## Invariants

- The check-in never logs off; it only disconnects.
- The disconnect happens whenever the desktop was opened, even if the hold or the state
  read failed.
- Success is decided by the domain rule on session states, never by the portal login.
- A successful report carries the time the desktop opened, not the time the attempt
  ended.
- Only a successful report carries the success screenshot; a failed attempt reports the
  screenshot of its `HorizonClientError`, if any, as before. A forced run behaves the
  same.

## API

Module `src/horizon_tracker/application/checkin.py`:

- `MorningCheckin(client: HorizonClient, clock: Clock, runner: WindowedRun, desktop:
  str, hold: timedelta)` — frozen:
  - `kind -> RunKind` — property, `RunKind.CHECKIN`;
  - `run(*, force: bool = False) -> RunReport`;
  - `steps() -> tuple[str, ...]`.

The CLI builds it with `HORIZON_DESKTOP` and `HT_HOLD_SECONDS` (120 by default).

## Testing

Tests: `tests/unit/application/test_checkin.py`, `tests/unit/test_cli.py`.

Scenarios (`tests/acceptance/features/morning_checkin.feature`):

- `Morning check-in opens the desktop and disconnects`
- `Morning check-in reports success with the recorded time`

The retry and calendar scenarios in `window_and_retries.feature` and
`production_calendar.feature`, and the drawn-moment scenarios in
`randomised_moments.feature`, run the check-in as well.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `session-state`, `windowed-run`
- Used by: `cli` (through the `application` package)

## Parent

`application` — [application README](../../README.md)
